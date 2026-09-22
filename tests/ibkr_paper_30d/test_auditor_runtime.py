from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Windows PowerShell auditor runtime tests"
)

from ibkr_paper_30d.auditor_export import AuditExporter

ROOT = Path(__file__).parents[2]
RUNTIME_SOURCE = ROOT / "auditor_runtime"
AUDITOR_NAME = "CODEX_DECISION_AUDITOR_V1.ps1"
PROBE_NAME = "AUDITOR_DENIAL_PROBE_V1.ps1"


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
    reason="test requires the same non-elevated token contract as CodexAuditorV1",
)


def compact_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def stage_runtime(tmp_path: Path) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    for name in (AUDITOR_NAME, PROBE_NAME):
        shutil.copy2(RUNTIME_SOURCE / name, runtime / name)
    manifest = {
        "schema": "AUDITOR_RUNTIME_MANIFEST_V1",
        "runtime_root": str(runtime.resolve()),
        "files": {
            name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
            for name in (AUDITOR_NAME, PROBE_NAME)
        },
    }
    manifest_path = runtime / "AUDITOR_RUNTIME_MANIFEST_V1.json"
    manifest_path.write_text(compact_json(manifest), encoding="utf-8")
    return runtime, manifest_path


def run_script(script: Path, arguments: list[str]):
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    line = next(
        (
            item
            for item in result.stdout.splitlines()
            if item.startswith("RESULT_JSON=")
        ),
        None,
    )
    payload = json.loads(line.removeprefix("RESULT_JSON=")) if line else None
    return result, payload


def run_auditor(tmp_path: Path, bundle: Path, *, report_name: str | None = None):
    runtime, runtime_manifest = stage_runtime(tmp_path)
    reports = tmp_path / "reports"
    arguments = [
        "-BundlePath",
        str(bundle),
        "-ReportDirectory",
        str(reports),
        "-RuntimeManifestPath",
        str(runtime_manifest),
    ]
    if report_name:
        arguments.extend(("-ReportFileName", report_name))
    return run_script(runtime / AUDITOR_NAME, arguments)


@pytest.fixture
def export_bundle(tmp_path) -> Path:
    receipt = AuditExporter(tmp_path / "exports").publish(
        {
            "decision.json": {"decision_id": "d-1", "result": "NO_TRADE"},
            "risk.json": {"status": "PASS"},
        }
    )
    return receipt.path


def test_runtime_contains_no_repo_broker_or_trader_imports() -> None:
    runtime_text = (RUNTIME_SOURCE / AUDITOR_NAME).read_text(encoding="utf-8")

    assert not any(
        token in runtime_text
        for token in ("ibapi", "broker.py", "trader_invocation", "execution_lock")
    )


def test_provisioning_review_hash_binds_runtime_and_probe_targets() -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "AUDITOR_WINDOWS_PROVISIONING_V1.ps1"),
            "-Mode",
            "Review",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    line = next(
        item for item in result.stdout.splitlines() if item.startswith("MANIFEST_JSON=")
    )
    manifest = json.loads(line.removeprefix("MANIFEST_JSON="))
    runtime_files = {item["name"]: item["sha256"] for item in manifest["runtime_files"]}
    assert set(runtime_files) == {AUDITOR_NAME, PROBE_NAME}
    assert all(len(digest) == 64 for digest in runtime_files.values())
    assert set(manifest["probe_targets"]) == {
        "SECRETS_READ",
        "IBKR_SECRET_READ",
        "SMTP_SECRET_READ",
        "EXECUTION_LOCK_ACCESS",
        "LIVE_DATABASE_MUTATION",
        "BROKER_WRITE_PATH_ACCESS",
        "BROKER_NETWORK_SOCKET_ACCESS",
        "TRADER_CONTEXT_ACCESS",
        "AUDIT_INPUT_MUTATION",
        "IMMUTABLE_EXPORT_READ",
        "AUDITOR_REPORT_WRITE",
    }


def test_runtime_accepts_exact_hash_bound_bundle(tmp_path, export_bundle) -> None:
    result, payload = run_auditor(tmp_path / "run", export_bundle)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["status"] == "PASS"
    assert payload["verified_file_count"] == 2
    assert payload["token_elevated"] is current_token_elevated()
    assert Path(payload["report_path"]).is_file()


@pytest.mark.parametrize("mutation", ["MODIFIED", "EXTRA", "TRAVERSAL"])
def test_runtime_rejects_modified_extra_and_traversing_bundle_files(
    tmp_path, export_bundle, mutation
) -> None:
    if mutation == "MODIFIED":
        target = export_bundle / "decision.json"
        target.chmod(stat.S_IREAD | stat.S_IWRITE)
        target.write_text('{"modified":true}', encoding="utf-8")
    elif mutation == "EXTRA":
        (export_bundle / "extra.json").write_text("{}", encoding="utf-8")
    else:
        manifest_path = export_bundle / "manifest.json"
        manifest_path.chmod(stat.S_IREAD | stat.S_IWRITE)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["../escape.json"] = "0" * 64
        manifest_path.write_text(compact_json(manifest), encoding="utf-8")

    result, payload = run_auditor(tmp_path / "run", export_bundle)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["status"] in {
        "HASH_MISMATCH",
        "FILE_SET_MISMATCH",
        "UNSAFE_MANIFEST_PATH",
    }


def test_runtime_rejects_malformed_duplicate_and_case_colliding_manifest(
    tmp_path, export_bundle
) -> None:
    manifest_path = export_bundle / "manifest.json"
    manifest_path.chmod(stat.S_IREAD | stat.S_IWRITE)
    manifest_path.write_text(
        '{"schema":"AUDIT_EXPORT_MANIFEST_V1","schema":"DUPLICATE"}',
        encoding="utf-8",
    )
    _, duplicate = run_auditor(tmp_path / "duplicate", export_bundle)
    assert duplicate["status"] == "MANIFEST_INVALID"

    manifest_path.write_text(
        compact_json(
            {
                "schema": "AUDIT_EXPORT_MANIFEST_V1",
                "bundle_id": "audit-invalid",
                "bundle_sha256": "0" * 64,
                "files": {"decision.json": "0" * 64, "DECISION.JSON": "0" * 64},
            }
        ),
        encoding="utf-8",
    )
    _, collision = run_auditor(tmp_path / "collision", export_bundle)
    assert collision["status"] == "CASE_COLLISION"


def test_runtime_manifest_mismatch_fails_closed(tmp_path, export_bundle) -> None:
    runtime, runtime_manifest = stage_runtime(tmp_path / "run")
    (runtime / PROBE_NAME).write_text("# modified", encoding="utf-8")

    result, payload = run_script(
        runtime / AUDITOR_NAME,
        [
            "-BundlePath",
            str(export_bundle),
            "-ReportDirectory",
            str(tmp_path / "reports"),
            "-RuntimeManifestPath",
            str(runtime_manifest),
        ],
    )

    assert result.returncode != 0
    assert payload["status"] == "RUNTIME_HASH_MISMATCH"


def test_runtime_rejects_reparse_point_file(tmp_path, export_bundle) -> None:
    runtime, _ = stage_runtime(tmp_path / "real")
    junction = tmp_path / "runtime-junction"
    creation = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction}' -Target '{runtime}' | Out-Null",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if creation.returncode != 0:
        pytest.skip(f"junction creation unavailable: {creation.stderr}")
    runtime_manifest = junction / "AUDITOR_RUNTIME_MANIFEST_V1.json"
    manifest = json.loads(runtime_manifest.read_text(encoding="utf-8"))
    manifest["runtime_root"] = str(junction.absolute())
    runtime_manifest.write_text(compact_json(manifest), encoding="utf-8")

    result, payload = run_script(
        junction / AUDITOR_NAME,
        [
            "-BundlePath",
            str(export_bundle),
            "-ReportDirectory",
            str(tmp_path / "reports"),
            "-RuntimeManifestPath",
            str(runtime_manifest),
        ],
    )
    junction.rmdir()

    assert result.returncode != 0
    assert payload["status"] == "RUNTIME_PATH_REDIRECTED"


def test_report_overwrite_is_rejected(tmp_path, export_bundle) -> None:
    runtime, runtime_manifest = stage_runtime(tmp_path / "run")
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "fixed.json").write_text("existing", encoding="utf-8")

    result, payload = run_script(
        runtime / AUDITOR_NAME,
        [
            "-BundlePath",
            str(export_bundle),
            "-ReportDirectory",
            str(reports),
            "-RuntimeManifestPath",
            str(runtime_manifest),
            "-ReportFileName",
            "fixed.json",
        ],
    )

    assert result.returncode != 0
    assert payload["status"] == "REPORT_EXISTS"
    assert (reports / "fixed.json").read_text(encoding="utf-8") == "existing"


def current_sid() -> str:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def target_manifest(expected_sid: str, approved_root: Path, reports: Path) -> dict:
    targets = {
        "SECRETS_READ": str(approved_root / "secrets"),
        "IBKR_SECRET_READ": str(approved_root / "jts"),
        "SMTP_SECRET_READ": str(approved_root / "secrets" / "email_alerts.env"),
        "EXECUTION_LOCK_ACCESS": str(approved_root / "state" / "execution.lock"),
        "LIVE_DATABASE_MUTATION": str(approved_root / "state" / "live.sqlite3"),
        "BROKER_WRITE_PATH_ACCESS": str(approved_root / "broker.py"),
        "BROKER_NETWORK_SOCKET_ACCESS": str(approved_root / "broker.py"),
        "TRADER_CONTEXT_ACCESS": str(approved_root / "trader_invocation.py"),
        "AUDIT_INPUT_MUTATION": str(approved_root / "exports"),
        "IMMUTABLE_EXPORT_READ": str(approved_root / "exports"),
        "AUDITOR_REPORT_WRITE": str(reports),
    }
    return {
        "schema": "AUDITOR_PROBE_TARGET_MANIFEST_V1",
        "expected_sid": expected_sid,
        "approved_roots": [str(approved_root.resolve()), str(reports.resolve())],
        "targets": targets,
    }


def run_target_validation(tmp_path: Path, manifest: dict):
    runtime, runtime_manifest = stage_runtime(tmp_path / "staged")
    target_path = tmp_path / "targets.json"
    target_path.write_text(compact_json(manifest), encoding="utf-8")
    return run_script(
        runtime / PROBE_NAME,
        [
            "-TargetManifestPath",
            str(target_path),
            "-ReportDirectory",
            str(tmp_path / "reports"),
            "-RuntimeManifestPath",
            str(runtime_manifest),
            "-ExpectedSid",
            current_sid(),
            "-ValidateTargetsOnly",
        ],
    )


@requires_non_elevated_token
def test_target_validation_accepts_all_approved_paths(tmp_path) -> None:
    root = tmp_path / "approved"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()
    manifest = target_manifest(current_sid(), root, reports)

    result, payload = run_target_validation(tmp_path, manifest)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["status"] == "TARGET_VALIDATION_COMPLETE"
    assert len(payload["target_validation_matrix"]) == 11
    assert all(row["valid"] for row in payload["target_validation_matrix"])


def test_target_validation_reports_access_denied_path_without_calling_it_unsafe(
    tmp_path,
) -> None:
    (tmp_path / "approved" / "secrets").mkdir(parents=True)
    probe = str(RUNTIME_SOURCE / PROBE_NAME).replace("'", "''")
    target = str(tmp_path / "approved" / "secrets").replace("'", "''")
    root = str(tmp_path / "approved").replace("'", "''")
    command = rf"""
$tokens=$null
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('{probe}',[ref]$tokens,[ref]$errors)
$function=$ast.Find({{param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-PathValidation'}},$true)
Invoke-Expression $function.Extent.Text
$script:DeniedTarget='{target}'
function Get-Item {{
    param([string]$LiteralPath,[switch]$Force,[object]$ErrorAction)
    if ($LiteralPath -ieq $script:DeniedTarget) {{ throw [UnauthorizedAccessException]::new('simulated ACL denial') }}
    Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
}}
Get-PathValidation -Target $script:DeniedTarget -ApprovedRoots @('{root}') | ConvertTo-Json -Depth 8 -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    payload = json.loads(result.stdout.strip())

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["valid"] is False
    assert payload["reason"] == "TARGET_PATH_CHAIN_NOT_FULLY_INSPECTABLE"


@requires_non_elevated_token
def test_target_validation_rejects_outside_root_and_reparse_path(tmp_path) -> None:
    root = tmp_path / "approved"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()
    manifest = target_manifest(current_sid(), root, reports)
    manifest["targets"]["SECRETS_READ"] = str(tmp_path / "outside")

    outside_result, outside = run_target_validation(tmp_path / "outside-run", manifest)

    assert outside_result.returncode == 23
    outside_row = next(
        item
        for item in outside["target_validation_matrix"]
        if item["probe"] == "SECRETS_READ"
    )
    assert outside_row["reason"] == "TARGET_OUTSIDE_APPROVED_ROOT"

    real = root / "real"
    real.mkdir()
    junction = root / "redirected"
    creation = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction}' -Target '{real}' | Out-Null",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if creation.returncode != 0:
        pytest.skip(f"junction creation unavailable: {creation.stderr}")
    manifest["targets"]["SECRETS_READ"] = str(junction)

    reparse_result, reparse = run_target_validation(tmp_path / "reparse-run", manifest)

    junction.rmdir()
    assert reparse_result.returncode == 23
    reparse_row = next(
        item
        for item in reparse["target_validation_matrix"]
        if item["probe"] == "SECRETS_READ"
    )
    assert reparse_row["reason"] == "TARGET_REPARSE_POINT"


def test_gate_records_socket_reachability_as_residual_risk_without_hard_denial() -> None:
    source = (RUNTIME_SOURCE / "AUDITOR_GATE_V2_PROBE.ps1").read_text(
        encoding="utf-8"
    )

    assert "BROKER_NETWORK_SOCKET_NOT_DENIED" not in source
    assert "PAPER_BROKER_LOOPBACK_NOT_DENIED" not in source
    assert "BROKER_NETWORK_ENDPOINT_UNSAFE" not in source
    assert "BROKER_NETWORK_ENDPOINT_UNCERTAIN" in source
    assert "AUDITOR_NETWORK_ISOLATION_REQUIRED = $false" in source
    assert (
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY = $TechnicalSocketReachability"
        in source
    )
    assert (
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE = "
        "$UnauthorizedRawApiPathPossible"
        in source
    )


def test_endpoint_classifier_has_truthful_four_state_contract() -> None:
    source = (RUNTIME_SOURCE / PROBE_NAME).read_text(encoding="utf-8")

    assert '"CONNECTED"' in source
    assert '"NO_LISTENER"' in source
    assert '"DENIED"' in source
    assert '"OTHER"' in source
    assert 'SocketError]::ConnectionRefused' in source
    assert 'SocketError]::AccessDenied' in source
    assert 'WaitOne(500)' not in source
    assert 'WaitOne(5000)) { return "OTHER" }' in source


@requires_non_elevated_token
def test_active_dual_stack_listener_is_classified_connected(tmp_path) -> None:
    listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    listener.bind(("::", 0))
    listener.listen()
    port = listener.getsockname()[1]
    runtime, runtime_manifest = stage_runtime(tmp_path / "staged")
    root = tmp_path / "approved"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()
    manifest = target_manifest(current_sid(), root, reports)
    target_path = tmp_path / "targets.json"
    target_path.write_text(compact_json(manifest), encoding="utf-8")

    try:
        result, payload = run_script(
            runtime / PROBE_NAME,
            [
                "-TargetManifestPath",
                str(target_path),
                "-ReportDirectory",
                str(reports),
                "-RuntimeManifestPath",
                str(runtime_manifest),
                "-ExpectedSid",
                current_sid(),
                "-ClassifyEndpointsOnly",
                "-BrokerPorts",
                str(port),
            ],
        )
    finally:
        listener.close()

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["network_endpoints"][f"127.0.0.1:{port}"] == "CONNECTED"
    assert payload["network_endpoints"][f"[::1]:{port}"] == "CONNECTED"


@requires_non_elevated_token
def test_closed_dual_stack_port_is_classified_no_listener(tmp_path) -> None:
    reservation = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    reservation.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    reservation.bind(("::", 0))
    port = reservation.getsockname()[1]
    reservation.close()
    runtime, runtime_manifest = stage_runtime(tmp_path / "staged")
    root = tmp_path / "approved"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()
    manifest = target_manifest(current_sid(), root, reports)
    target_path = tmp_path / "targets.json"
    target_path.write_text(compact_json(manifest), encoding="utf-8")

    result, payload = run_script(
        runtime / PROBE_NAME,
        [
            "-TargetManifestPath",
            str(target_path),
            "-ReportDirectory",
            str(reports),
            "-RuntimeManifestPath",
            str(runtime_manifest),
            "-ExpectedSid",
            current_sid(),
            "-ClassifyEndpointsOnly",
            "-BrokerPorts",
            str(port),
        ],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["network_endpoints"][f"127.0.0.1:{port}"] == "NO_LISTENER"
    assert payload["network_endpoints"][f"[::1]:{port}"] == "NO_LISTENER"


@requires_non_elevated_token
def test_probe_report_binds_effective_sid_and_elevation_state(tmp_path) -> None:
    runtime, runtime_manifest = stage_runtime(tmp_path)
    reports = tmp_path / "reports"
    targets = {
        "schema": "AUDITOR_PROBE_TARGET_MANIFEST_V1",
        "expected_sid": current_sid(),
        "approved_roots": [str(tmp_path.resolve())],
        "targets": {
            "SECRETS_READ": str(tmp_path / "missing-secret"),
            "IBKR_SECRET_READ": str(tmp_path / "missing-ibkr"),
            "SMTP_SECRET_READ": str(tmp_path / "missing-mail"),
            "EXECUTION_LOCK_ACCESS": str(tmp_path / "missing-lock"),
            "LIVE_DATABASE_MUTATION": str(tmp_path / "missing.sqlite3"),
            "BROKER_WRITE_PATH_ACCESS": str(tmp_path / "missing-broker"),
            "TRADER_CONTEXT_ACCESS": str(tmp_path / "missing-context"),
            "AUDIT_INPUT_MUTATION": str(tmp_path / "missing-export"),
            "IMMUTABLE_EXPORT_READ": str(tmp_path / "missing-readable"),
            "AUDITOR_REPORT_WRITE": str(reports),
        },
    }
    target_manifest = tmp_path / "targets.json"
    target_manifest.write_text(compact_json(targets), encoding="utf-8")

    result, payload = run_script(
        runtime / PROBE_NAME,
        [
            "-TargetManifestPath",
            str(target_manifest),
            "-ReportDirectory",
            str(reports),
            "-RuntimeManifestPath",
            str(runtime_manifest),
            "-ExpectedSid",
            current_sid(),
        ],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["effective_sid"] == current_sid()
    assert payload["token_elevated"] is False
    assert set(payload["results"]) == set(targets["targets"])


@requires_non_elevated_token
def test_probe_rejects_wrong_sid_before_operations(tmp_path) -> None:
    runtime, runtime_manifest = stage_runtime(tmp_path)
    target_manifest = tmp_path / "targets.json"
    target_manifest.write_text(
        compact_json(
            {
                "schema": "AUDITOR_PROBE_TARGET_MANIFEST_V1",
                "expected_sid": "S-1-5-21-0-0-0-9999",
                "approved_roots": [str(tmp_path.resolve())],
                "targets": {},
            }
        ),
        encoding="utf-8",
    )

    result, payload = run_script(
        runtime / PROBE_NAME,
        [
            "-TargetManifestPath",
            str(target_manifest),
            "-ReportDirectory",
            str(tmp_path / "reports"),
            "-RuntimeManifestPath",
            str(runtime_manifest),
            "-ExpectedSid",
            "S-1-5-21-0-0-0-9999",
        ],
    )

    assert result.returncode != 0
    assert payload["status"] == "IDENTITY_INVALID"


def test_probe_source_rejects_elevated_tokens() -> None:
    source = (RUNTIME_SOURCE / PROBE_NAME).read_text(encoding="utf-8")

    assert "if ($Identity.User.Value -ne $ExpectedSid -or $Elevated)" in source
    assert '"TOKEN_ELEVATED"' in source


@pytest.mark.parametrize("name", [AUDITOR_NAME, PROBE_NAME])
def test_runtime_powershell_ast_has_no_parse_errors(name) -> None:
    script = RUNTIME_SOURCE / name
    escaped = str(script).replace("'", "''")
    command = (
        "$tokens=$null;$errors=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{escaped}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
