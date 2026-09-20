from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ibkr_paper_30d.auditor_runtime_v2 import (
    RUNTIME_MANIFEST_NAME,
    RUNTIME_PAYLOAD_ALLOWLIST,
    assess_runtime_capabilities,
    build_deployment_manifest_v2,
    build_runtime_manifest_v2,
    verify_runtime_fileset_v2,
)
from ibkr_paper_30d.canonical import canonical_bytes


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
