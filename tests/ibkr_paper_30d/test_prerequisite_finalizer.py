from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.prerequisite_tools import create_audit_export

ROOT = Path(__file__).resolve().parents[2]
FINALIZER = ROOT / "FINALIZE_IBKR_PREREQUISITES.ps1"
MARKET_RUNNER = ROOT / "RUN_IBKR_MARKET_DATA_GATE.ps1"
DENIAL_PROBE = ROOT / "auditor_runtime" / "AUDITOR_DENIAL_PROBE_V1.ps1"


def test_prerequisite_scripts_exist_and_never_arm_trading():
    for path in (FINALIZER, MARKET_RUNNER):
        text = path.read_text(encoding="utf-8")
        assert "IBKR_AUTONOMOUS_PAPER_ARMED=true" not in text
        assert "placeOrder" not in text
        assert "create_order_instruction" not in text

    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1" in finalizer
    assert "AUDITOR_GATE_V2_PROBE.ps1" in finalizer
    assert "market_data_task_registered" in finalizer
    assert "Enable-LocalUser -Name $AuditorUser" in finalizer
    assert "Disable-LocalUser -Name $AuditorUser" in finalizer
    assert "UNSAFE_ARGUMENT_VALUE" in finalizer
    assert "RemotePort 4001,4002" in finalizer
    assert "RemoteAddress 127.0.0.1,::1" in finalizer
    assert "-Program $WindowsPowerShell" not in finalizer
    assert "AUDITOR_PROBE_FIREWALL_SCOPE_INVALID" in finalizer

    market = MARKET_RUNNER.read_text(encoding="utf-8")
    assert '"330"' in market
    assert "AddMinutes(31)" in market
    assert "freeze-market-policy" in market
    assert "validate-real-market-data" in market
    assert "Archive-CollectionEvidence" in market


@pytest.mark.skipif(os.name != "nt", reason="PowerShell 5.1 parser validation is Windows-only")
@pytest.mark.parametrize("path", [FINALIZER, MARKET_RUNNER])
def test_powershell_51_ast_has_no_parse_errors(path: Path):
    escaped = str(path).replace("'", "''")
    command = (
        "$tokens=$null;$errors=$null;"
        f"[void][Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$tokens,[ref]$errors);"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="ScheduledTasks module validation is Windows-only")
def test_scheduled_task_objects_can_be_constructed_without_registration():
    command = (
        "$a=New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument '-NoProfile';"
        "$t=New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 "
        "-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:35AM;"
        "$p=New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN+'\\'+$env:USERNAME) "
        "-LogonType Interactive -RunLevel Highest;"
        "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3);"
        "if($null -eq $a -or $null -eq $t -or $null -eq $p -or $null -eq $s){exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_create_audit_export_preserves_identity_receipt_bytes(tmp_path: Path):
    readonly = tmp_path / "readonly.json"
    payload = {
        "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "PASS",
        "paper_account_identity_gate": "PASS",
        "real_ibkr_read_only_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "expected_account_identity_hash": "a" * 64,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    readonly.write_bytes(raw)

    result = create_audit_export(readonly, tmp_path / "exports")

    assert Path(result["bundle_path"]).is_dir()
    identity_copy = Path(result["paper_identity_receipt_path"])
    assert identity_copy.read_bytes() == raw


def test_denial_probe_classifies_acl_errors_explicitly():
    text = DENIAL_PROBE.read_text(encoding="utf-8")
    assert "Test-Path -LiteralPath $Target -ErrorAction Stop" in text
    assert "catch [UnauthorizedAccessException] { return \"DENIED\" }" in text
    assert "catch [Security.SecurityException] { return \"DENIED\" }" in text


def test_auditor_account_enablement_is_inside_cleanup_guard():
    text = FINALIZER.read_text(encoding="utf-8")
    assert text.count("Enable-LocalUser -Name $AuditorUser") == 1

    preflight_disable = text.index("if ($User.Enabled)")
    trust_anchor = text.index("AUDITOR_TRUST_ANCHOR_HASH_MISMATCH")
    assert preflight_disable < trust_anchor

    marker = text.index("# Keep the account disabled until the bounded probe window starts.")
    try_index = text.index("try {", marker)
    enable_index = text.index("Enable-LocalUser -Name $AuditorUser", marker)
    finally_index = text.index("finally {", enable_index)
    cleanup_disable = text.index(
        "Disable-LocalUser -Name $AuditorUser -ErrorAction Stop", finally_index
    )

    assert marker < try_index < enable_index < finally_index < cleanup_disable
    assert "$AuditorEnabledForProbe = $true" in text[enable_index:finally_index]
    assert "$ProbeFirewallInstalled = $true" in text[enable_index:finally_index]
