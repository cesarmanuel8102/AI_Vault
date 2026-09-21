from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Windows Auditor V2 PowerShell/runtime tests"
)

from ibkr_paper_30d.auditor_runtime_v2 import (
    RUNTIME_MANIFEST_NAME,
    RUNTIME_PAYLOAD_ALLOWLIST,
    assess_runtime_capabilities,
    build_deployment_manifest_v2,
    build_runtime_manifest_v2,
    consolidate_probe_results_v2,
    verify_runtime_fileset_v2,
)
from ibkr_paper_30d.canonical import canonical_bytes


ROOT = Path(__file__).parents[2]
CONSOLIDATED_PROBE = ROOT / "auditor_runtime" / "AUDITOR_GATE_V2_PROBE.ps1"
DEPLOYMENT_SCRIPT = ROOT / "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1"


def current_token_elevated() -> bool:
    if os.name != "nt":
        return False
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$i=[Security.Principal.WindowsIdentity]::GetCurrent();"
            "$p=[Security.Principal.WindowsPrincipal]::new($i);"
            "$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip().lower() == "true"


requires_non_elevated_token = pytest.mark.skipif(
    current_token_elevated(),
    reason="consolidated denial probe requires a non-elevated restricted token",
)


@pytest.fixture
def staged_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name in RUNTIME_PAYLOAD_ALLOWLIST:
        (runtime / name).write_text(f"# {name}\n", encoding="utf-8")
    manifest = build_runtime_manifest_v2(runtime, RUNTIME_PAYLOAD_ALLOWLIST)
    (runtime / RUNTIME_MANIFEST_NAME).write_bytes(canonical_bytes(manifest))
    return runtime


def _deployment(runtime: Path) -> dict[str, object]:
    return build_deployment_manifest_v2(
        runtime / RUNTIME_MANIFEST_NAME,
        [runtime / name for name in RUNTIME_PAYLOAD_ALLOWLIST],
    )


def test_runtime_v2_accepts_exact_hash_bound_fileset(staged_runtime: Path) -> None:
    result = verify_runtime_fileset_v2(staged_runtime, _deployment(staged_runtime))

    assert result.status == "PASS"
    assert result.reason_codes == ()
    assert result.runtime_manifest_sha256
    assert result.deployment_manifest_sha256


@pytest.mark.parametrize(
    "mutation",
    ["EXTRA", "MISSING", "PAYLOAD_HASH", "RUNTIME_MANIFEST_HASH"],
)
def test_runtime_v2_blocks_every_fileset_or_hash_mutation(
    staged_runtime: Path, mutation: str
) -> None:
    deployment = _deployment(staged_runtime)
    if mutation == "EXTRA":
        (staged_runtime / "extra.ps1").write_text("# extra", encoding="utf-8")
    elif mutation == "MISSING":
        (staged_runtime / RUNTIME_PAYLOAD_ALLOWLIST[0]).unlink()
    elif mutation == "PAYLOAD_HASH":
        (staged_runtime / RUNTIME_PAYLOAD_ALLOWLIST[0]).write_text(
            "# changed", encoding="utf-8"
        )
    else:
        (staged_runtime / RUNTIME_MANIFEST_NAME).write_text(
            "{}", encoding="utf-8"
        )

    result = verify_runtime_fileset_v2(staged_runtime, deployment)

    assert result.status == "BLOCK"
    assert result.reason_codes


@pytest.mark.parametrize(
    "mutation",
    ["SCHEMA", "MALFORMED_HASH", "CASE_COLLISION", "PATH_SEPARATOR"],
)
def test_runtime_v2_rejects_untrusted_deployment_manifest(
    staged_runtime: Path, mutation: str
) -> None:
    deployment = deepcopy(_deployment(staged_runtime))
    if mutation == "SCHEMA":
        deployment["schema"] = "FOREIGN"
    elif mutation == "MALFORMED_HASH":
        deployment["files"][RUNTIME_PAYLOAD_ALLOWLIST[0]] = "bad"
    elif mutation == "CASE_COLLISION":
        deployment["files"][RUNTIME_PAYLOAD_ALLOWLIST[0].lower()] = "0" * 64
    else:
        deployment["files"]["nested/evil.ps1"] = "0" * 64

    result = verify_runtime_fileset_v2(staged_runtime, deployment)

    assert result.status == "BLOCK"


def test_runtime_v2_rejects_non_file_runtime_entry(staged_runtime: Path) -> None:
    (staged_runtime / "directory").mkdir()

    result = verify_runtime_fileset_v2(staged_runtime, _deployment(staged_runtime))

    assert result.status == "BLOCK"
    assert "RUNTIME_FILESET_MISMATCH" in result.reason_codes


def _inject_into_probe(runtime: Path, payload: str) -> None:
    target = runtime / "AUDITOR_GATE_V2_PROBE.ps1"
    target.write_text(target.read_text(encoding="utf-8") + payload + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("payload", "predicate"),
    [
        ("Import-Module ibapi", "BROKER_MODULE_AVAILABLE"),
        ("placeOrder", "ORDER_WRITE_SYMBOL_AVAILABLE"),
        ("'ibkr_paper_30d.broker'", "EXECUTION_ADAPTER_AVAILABLE"),
        ("Acquire-ExecutionLock", "EXECUTION_LOCK_CLIENT_AVAILABLE"),
        (
            "New-Object IO.Pipes.NamedPipeClientStream",
            "TRADER_IPC_CLIENT_AVAILABLE",
        ),
        ("$env:IBKR_PASSWORD", "BROKER_CREDENTIAL_SOURCE_AVAILABLE"),
    ],
)
def test_capability_scanner_fails_closed_on_forbidden_runtime_surface(
    staged_runtime: Path, payload: str, predicate: str
) -> None:
    _inject_into_probe(staged_runtime, payload)

    result = assess_runtime_capabilities(staged_runtime)

    assert result.status == "BLOCK"
    assert result.predicates[predicate] is True
    if predicate in {
        "BROKER_MODULE_AVAILABLE",
        "ORDER_WRITE_SYMBOL_AVAILABLE",
        "EXECUTION_ADAPTER_AVAILABLE",
    }:
        assert result.predicates["ORDER_WRITE_MODULE_AVAILABLE"] is True


@pytest.mark.parametrize(
    "payload",
    [
        "cancelOrder",
        "modifyOrder",
        "reqGlobalCancel",
        "New-Object IBApi.EClientSocket",
        "Start-Process python.exe",
        "Invoke-Expression 'Get-Date'",
        "Add-Type -TypeDefinition 'public class X {}'",
        "powershell.exe -File arbitrary.ps1",
        "python.exe arbitrary.py",
        "New-Object Net.Sockets.Socket",
        "Import-Module C:\\broad\\execution.psm1",
    ],
)
def test_capability_scanner_blocks_order_protocol_process_and_network_helpers(
    staged_runtime: Path, payload: str
) -> None:
    _inject_into_probe(staged_runtime, payload)

    result = assess_runtime_capabilities(staged_runtime)

    assert result.status == "BLOCK"
    assert result.reason_codes


def test_capability_scanner_accepts_minimal_runtime_and_derives_order_aggregate(
    staged_runtime: Path,
) -> None:
    result = assess_runtime_capabilities(staged_runtime)

    assert result.status == "PASS"
    assert all(value is False for value in result.predicates.values())


def test_capability_scanner_allows_only_narrow_loopback_tcp_classifier(
    staged_runtime: Path,
) -> None:
    denial_probe = staged_runtime / "AUDITOR_DENIAL_PROBE_V1.ps1"
    denial_probe.write_text(
        """
function Test-TcpEndpoint {
    param([ValidateSet('127.0.0.1','::1')][string]$Address, [ValidateRange(1,65535)][int]$Port)
    $client = New-Object Net.Sockets.TcpClient
}
Test-TcpEndpoint -Address '127.0.0.1' -Port 4002
""".strip(),
        encoding="utf-8",
    )

    result = assess_runtime_capabilities(staged_runtime)

    assert result.status == "PASS"


def _fake_consolidated_inputs() -> dict[str, object]:
    run_id = "run-v2-test"
    outcomes = {
        "SECRETS_READ": "DENIED",
        "IBKR_SECRET_READ": "DENIED",
        "SMTP_SECRET_READ": "DENIED",
        "EXECUTION_LOCK_ACCESS": "DENIED",
        "LIVE_DATABASE_MUTATION": "DENIED",
        "BROKER_WRITE_PATH_ACCESS": "ALLOWED",
        "TRADER_CONTEXT_ACCESS": "DENIED",
        "AUDIT_INPUT_MUTATION": "DENIED",
        "IMMUTABLE_EXPORT_READ": "ALLOWED",
        "AUDITOR_REPORT_WRITE": "ALLOWED",
    }
    return {
        "run_id": run_id,
        "started_at": datetime(2026, 9, 20, 15, 58, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 9, 20, 15, 59, tzinfo=timezone.utc),
        "identity": {
            "effective_sid": "S-1-5-21-214160970-1890373857-4055601883-1012",
            "token_elevated": False,
            "separate_process": True,
        },
        "runtime": {
            "status": "PASS",
            "runtime_manifest_sha256": "a" * 64,
            "deployment_manifest_sha256": "b" * 64,
            "probe_sha256": "c" * 64,
            "probe_manifest_sha256": "d" * 64,
            "exact_fileset": True,
            "verified_at_utc": "2026-09-20T15:57:30Z",
            "predicates": {
                "BROKER_MODULE_AVAILABLE": False,
                "ORDER_WRITE_SYMBOL_AVAILABLE": False,
                "EXECUTION_ADAPTER_AVAILABLE": False,
                "EXECUTION_LOCK_CLIENT_AVAILABLE": False,
                "TRADER_IPC_CLIENT_AVAILABLE": False,
                "BROKER_CREDENTIAL_SOURCE_AVAILABLE": False,
                "ORDER_WRITE_MODULE_AVAILABLE": False,
            },
        },
        "denial": {
            "status": "COMPLETE",
            "run_id": run_id,
            "target_validation_matrix": [
                {"run_id": run_id, "probe": name, "valid": True}
                for name in outcomes
            ],
            "results": outcomes,
            "network_endpoints": {
                "127.0.0.1:4001": "DENIED",
                "127.0.0.1:4002": "DENIED",
                "[::1]:4001": "DENIED",
                "[::1]:4002": "DENIED",
            },
        },
        "functional": {
            "run_id": run_id,
            "status": "PASS",
            "bundle_id": "e" * 64,
            "manifest_sha256": "f" * 64,
        },
        "paper": {
            "run_id": run_id,
            "expected_account_identity_hash": "1" * 64,
            "identity_receipt_sha256": "2" * 64,
            "environment_reference": "PAPER:gateway:4002",
            "broker_session_environment_reference": "PAPER:session:4002",
            "verified_at_utc": "2026-09-20T15:57:00Z",
            "paper_identity_gate": "PASS",
            "readonly_identity_gate": "PASS",
            "broker_reconciliation_gate": "PASS",
            "paper_only": True,
            "live_allowed": False,
            "real_money_allowed": False,
        },
        "output": {
            "run_id": run_id,
            "report_path": r"C:\ProgramData\CodexAuditorV1\reports\functional.json",
            "created": True,
            "report_sha256": "3" * 64,
            "evidence_origin": "REAL_RESTRICTED_TOKEN",
        },
    }


def test_consolidated_probe_builds_one_complete_single_run_receipt() -> None:
    inputs = _fake_consolidated_inputs()

    receipt = consolidate_probe_results_v2(**inputs)

    assert receipt["schema"] == "AUDITOR_GATE_V2_RECEIPT_V1"
    assert receipt["run_id"] == "run-v2-test"
    assert len(receipt["target_validation_matrix"]) == 10
    assert len(receipt["capability_outcomes"]) == 10
    assert receipt["network_facts"] == {
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": False,
        "AUDITOR_NETWORK_ISOLATION_REQUIRED": True,
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": False,
        "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
        "endpoints": {
            "127.0.0.1:4001": "DENIED",
            "127.0.0.1:4002": "DENIED",
            "[::1]:4001": "DENIED",
            "[::1]:4002": "DENIED",
        },
    }


@pytest.mark.parametrize("child", ["denial", "functional", "runtime"])
def test_consolidated_probe_fails_closed_on_any_child_failure(child: str) -> None:
    inputs = _fake_consolidated_inputs()
    inputs[child]["status"] = "BLOCK"

    with pytest.raises(ValueError, match="CONSOLIDATED_CHILD_FAILURE"):
        consolidate_probe_results_v2(**inputs)


def test_consolidated_probe_and_deployment_scripts_have_safe_fixed_surfaces() -> None:
    assert CONSOLIDATED_PROBE.is_file()
    assert DEPLOYMENT_SCRIPT.is_file()
    probe_source = CONSOLIDATED_PROBE.read_text(encoding="utf-8")
    deployment_source = DEPLOYMENT_SCRIPT.read_text(encoding="utf-8")
    forbidden_parameters = ("ScriptPath", "ExecutablePath", "DestinationPath")
    assert all(name not in probe_source.split(")", 1)[0] for name in forbidden_parameters)
    assert '"AUDITOR_DENIAL_PROBE_V1.ps1"' in probe_source
    assert '"CODEX_DECISION_AUDITOR_V1.ps1"' in probe_source
    assert "[IO.FileMode]::CreateNew" in probe_source
    assert '[ValidateSet("Review", "Install", "Remove")]' in deployment_source
    assert "INSTALLATION_PERFORMED" in deployment_source

    command = (
        "$errors=$null;$tokens=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:CODEX_PS_FILE,[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    for path in (CONSOLIDATED_PROBE, DEPLOYMENT_SCRIPT):
        environment = dict(**__import__("os").environ, CODEX_PS_FILE=str(path))
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout


def test_consolidated_probe_deployment_review_is_nonmutating_json() -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(DEPLOYMENT_SCRIPT),
            "-Mode",
            "Review",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["MODE"] == "Review"
    assert payload["INSTALLATION_PERFORMED"] is False
    assert payload["NEW_ADMIN_ACTION_REQUIRED"] in {True, False}
    assert "-Mode Install" in payload["INSTALL_COMMAND"]
    assert "-Mode Remove" in payload["REMOVE_COMMAND"]


def test_consolidated_probe_strict_json_scopes_duplicate_keys_per_object(
    tmp_path: Path,
) -> None:
    source = CONSOLIDATED_PROBE.read_text(encoding="utf-8")
    function_source = source[
        source.index("function Read-StrictJson") : source.index(
            "function Read-ResultLine"
        )
    ]
    harness = tmp_path / "strict-json-harness.ps1"
    harness.write_text(
        function_source
        + "\ntry { Read-StrictJson -LiteralPath $env:CODEX_JSON_PATH | Out-Null; "
        + "Write-Output 'VALID' } catch { Write-Output $_.Exception.Message; exit 1 }\n",
        encoding="utf-8",
    )

    valid = tmp_path / "valid.json"
    valid.write_text('{"a":{"status":"PASS"},"b":{"status":"PASS"}}')
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":{"Status":"PASS","status":"BLOCK"}}')

    def run(path: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(**__import__("os").environ, CODEX_JSON_PATH=str(path))
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(harness)],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

    valid_result = run(valid)
    duplicate_result = run(duplicate)
    assert valid_result.returncode == 0, valid_result.stderr + valid_result.stdout
    assert valid_result.stdout.strip() == "VALID"
    assert duplicate_result.returncode != 0
    assert "DUPLICATE_JSON_KEY" in duplicate_result.stdout


def test_consolidated_probe_predicate_labels_are_not_runtime_capabilities(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "runtime"
    staged.mkdir()
    for name in RUNTIME_PAYLOAD_ALLOWLIST:
        (staged / name).write_bytes((ROOT / "auditor_runtime" / name).read_bytes())

    result = assess_runtime_capabilities(staged)

    assert result.status == "PASS"
    assert all(value is False for value in result.predicates.values())


def _result_payload(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.startswith("RESULT_JSON=")]
    assert len(lines) == 1
    return json.loads(lines[0].split("=", 1)[1])


def _current_sid() -> str:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@requires_non_elevated_token
def test_consolidated_probe_children_accept_exact_v2_runtime_manifest(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name in RUNTIME_PAYLOAD_ALLOWLIST:
        (runtime / name).write_bytes((ROOT / "auditor_runtime" / name).read_bytes())
    manifest = build_runtime_manifest_v2(runtime, RUNTIME_PAYLOAD_ALLOWLIST)
    manifest_path = runtime / RUNTIME_MANIFEST_NAME
    manifest_path.write_bytes(canonical_bytes(manifest))
    reports = tmp_path / "reports"
    invalid_targets = tmp_path / "targets.json"
    invalid_targets.write_bytes(
        canonical_bytes(
            {
                "schema": "AUDITOR_PROBE_TARGET_MANIFEST_V1",
                "expected_sid": _current_sid(),
                "approved_roots": [],
                "targets": {},
            }
        )
    )

    functional = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(runtime / "CODEX_DECISION_AUDITOR_V1.ps1"),
            "-BundlePath",
            str(tmp_path / "missing-bundle"),
            "-ReportDirectory",
            str(reports),
            "-RuntimeManifestPath",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    denial = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(runtime / "AUDITOR_DENIAL_PROBE_V1.ps1"),
            "-TargetManifestPath",
            str(invalid_targets),
            "-ReportDirectory",
            str(reports),
            "-RuntimeManifestPath",
            str(manifest_path),
            "-ExpectedSid",
            _current_sid(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert _result_payload(functional.stdout)["status"] == "MANIFEST_INVALID"
    assert _result_payload(denial.stdout)["status"] == "TARGET_SET_MISMATCH"
