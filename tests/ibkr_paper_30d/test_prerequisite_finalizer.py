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
DAY1_RUNNER = ROOT / "RUN_IBKR_DAY1_SERVICE.ps1"
DENIAL_PROBE = ROOT / "auditor_runtime" / "AUDITOR_DENIAL_PROBE_V1.ps1"


def test_prerequisite_scripts_exist_and_never_arm_trading():
    for path in (FINALIZER, MARKET_RUNNER, DAY1_RUNNER):
        text = path.read_text(encoding="utf-8")
        assert "IBKR_AUTONOMOUS_PAPER_ARMED=true" not in text
        assert "placeOrder" not in text
        assert "create_order_instruction" not in text
        assert "--port 4001" not in text

    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1" in finalizer
    assert "AUDITOR_GATE_V2_PROBE.ps1" in finalizer
    assert "market_data_task_registered" in finalizer
    assert "Enable-LocalUser -Name $AuditorUser" in finalizer
    assert "Disable-LocalUser -Name $AuditorUser" in finalizer
    assert "UNSAFE_ARGUMENT_VALUE" in finalizer
    assert "[char]36" in finalizer  # $ interpolation
    assert "[char]96" in finalizer  # PowerShell escape/backtick
    assert "[char]59" in finalizer  # command separator
    assert "[char]38" in finalizer  # invocation/control operator
    assert "[char]124" in finalizer  # pipeline
    assert "RemotePort 4001,4002" in finalizer
    assert "RemoteAddress Any" in finalizer
    assert "RemoteAddress 127.0.0.1,::1" not in finalizer
    assert 'if ($ProbeAddresses -notcontains "Any") {' in finalizer
    assert "-Program $WindowsPowerShell" not in finalizer
    assert "AUDITOR_PROBE_FIREWALL_SCOPE_INVALID" in finalizer

    market = MARKET_RUNNER.read_text(encoding="utf-8")
    assert '"330"' in market
    assert "AddMinutes(31)" in market
    assert "freeze-market-policy" in market
    assert "validate-real-market-data" in market
    assert "Archive-CollectionEvidence" in market


@pytest.mark.skipif(os.name != "nt", reason="PowerShell 5.1 parser validation is Windows-only")
@pytest.mark.parametrize("path", [FINALIZER, MARKET_RUNNER, DAY1_RUNNER])
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
        "$t1=New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 "
        "-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:35AM;"
        "$t2=New-ScheduledTaskTrigger -AtLogOn -User ($env:USERDOMAIN+'\\'+$env:USERNAME);"
        "$p=New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN+'\\'+$env:USERNAME) "
        "-LogonType Interactive -RunLevel Highest;"
        "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew "
        "-ExecutionTimeLimit (New-TimeSpan -Days 31) -RestartCount 3 "
        "-RestartInterval (New-TimeSpan -Minutes 5);"
        "if($null -eq $a -or $null -eq $t1 -or $null -eq $t2 -or $null -eq $p -or $null -eq $s){exit 1}"
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


def test_external_provisioning_invocation_does_not_pass_switch_false_as_string():
    text = FINALIZER.read_text(encoding="utf-8")
    assert "-Mode Apply -RepoRoot $ResolvedRepoRoot" in text
    assert "-Confirm:$false" not in text


def test_market_runner_python_wrapper_captures_native_stderr_before_failing():
    text = MARKET_RUNNER.read_text(encoding="utf-8")
    start = text.index("function Invoke-PythonJson")
    end = text.index("function Get-EasternNow")
    block = text[start:end]

    assert '$PriorErrorActionPreference = $ErrorActionPreference' in block
    assert '$ErrorActionPreference = "Continue"' in block
    assert "$PythonExitCode = $LASTEXITCODE" in block
    assert "$ErrorActionPreference = $PriorErrorActionPreference" in block
    assert "PYTHON_COMMAND_FAILED:" in block


def test_python_json_wrapper_captures_native_stderr_before_failing():
    text = FINALIZER.read_text(encoding="utf-8")
    start = text.index("function Invoke-PythonJson")
    end = text.index("function New-RandomSecurePassword")
    block = text[start:end]

    assert '$PriorErrorActionPreference = $ErrorActionPreference' in block
    assert '$ErrorActionPreference = "Continue"' in block
    assert "$PythonExitCode = $LASTEXITCODE" in block
    assert "$ErrorActionPreference = $PriorErrorActionPreference" in block
    assert "PYTHON_COMMAND_FAILED:" in block


def test_finalizer_owns_explicit_authorization_and_fresh_attempt_binding():
    text = FINALIZER.read_text(encoding="utf-8")

    assert "[string]$OwnerAuthorization" in text
    assert "[string]$LaunchAttemptId" in text
    assert '"AUTHORIZE 30-DAY PAPER EXPERIMENT"' in text
    assert '"ibkr_paper_30d.owner_authorization", "create"' in text
    assert '"ibkr_paper_30d.owner_authorization", "validate"' in text
    assert "OWNER_AUTHORIZATION_MISSING" in text
    assert "LAUNCH_ATTEMPT_ID_REQUIRED" in text
    assert '"bind-launch-attempt"' in text

    readonly_index = text.index('"inspect-ibkr-readonly"')
    authorization_index = text.index(
        '"ibkr_paper_30d.owner_authorization", "validate"'
    )
    auditor_index = text.index("$AuditorEvaluation = Invoke-PythonJson")
    binding_index = text.index('"bind-launch-attempt"')
    assert authorization_index < readonly_index < auditor_index < binding_index


def test_scheduled_finalizer_cannot_create_owner_authorization():
    text = FINALIZER.read_text(encoding="utf-8")
    guard = text.index("if ($SkipTaskRegistration)")
    create = text.index('"ibkr_paper_30d.owner_authorization", "create"')
    validate = text.index('"ibkr_paper_30d.owner_authorization", "validate"')

    assert guard < create
    assert validate < create


@pytest.mark.skipif(os.name != "nt", reason="PowerShell execution is Windows-only")
def test_day1_handoff_validate_only_reports_foreground_commands():
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DAY1_RUNNER),
            "-RepoRoot",
            str(ROOT),
            "-ValidateOnly",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "-SkipTaskRegistration" in payload["finalizer_arguments"]
    assert payload["python_arguments"][:3] == [
        "-m",
        "ibkr_paper_30d.day1_launch",
        "--repo-root",
    ]
    assert payload["launch_attempt_id"] in payload["finalizer_arguments"]
    assert payload["launch_attempt_id"] in payload["python_arguments"]
    assert payload["foreground"] is True
    assert payload["broker_write_calls"] == 0


@pytest.mark.skipif(os.name != "nt", reason="PowerShell execution is Windows-only")
def test_nonzero_finalizer_prevents_launcher_invocation(tmp_path: Path):
    fake_finalizer = tmp_path / "fake-finalizer.cmd"
    fake_launcher = tmp_path / "fake-launcher.cmd"
    launcher_marker = tmp_path / "launcher-called.txt"
    fake_finalizer.write_text("@exit /b 42\n", encoding="ascii")
    fake_launcher.write_text(
        f'@echo called>"{launcher_marker}"\n@exit /b 0\n', encoding="ascii"
    )
    launch_root = ROOT / "state" / "ibkr_paper_30d" / "launch"
    before = set(launch_root.glob("day1-*-pid*.log")) if launch_root.exists() else set()
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(DAY1_RUNNER),
                "-RepoRoot",
                str(ROOT),
                "-PowerShellExe",
                str(fake_finalizer),
                "-PythonExe",
                str(fake_launcher),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert not launcher_marker.exists()
    finally:
        if launch_root.exists():
            for path in set(launch_root.glob("day1-*-pid*.log")) - before:
                path.unlink(missing_ok=True)


def test_market_runner_hands_both_scheduled_pass_paths_to_foreground_service():
    text = MARKET_RUNNER.read_text(encoding="utf-8")
    assert "function Invoke-Day1ForegroundService" in text
    assert text.count("Invoke-Day1ForegroundService") >= 3
    assert "RUN_IBKR_DAY1_SERVICE.ps1" in text
    assert "Unregister-ScheduledTask" not in text


def test_finalizer_registers_one_persistent_task_with_two_triggers():
    text = FINALIZER.read_text(encoding="utf-8")
    assert "-ExecutionTimeLimit (New-TimeSpan -Days 31)" in text
    assert "-MultipleInstances IgnoreNew" in text
    assert "-RestartCount 3" in text
    assert "-RestartInterval (New-TimeSpan -Minutes 5)" in text
    assert "New-ScheduledTaskTrigger -AtLogOn -User $OwnerPrincipal" in text
    assert "$Triggers = @(" in text
    assert "-Trigger $Triggers" in text


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



def test_auditor_probe_launch_uses_clean_explicit_environment():
    """The restricted auditor child must boot with an explicit minimal
    environment instead of Start-Process -UseNewEnvironment, which passes a
    NULL environment block for -Credential launches (missing SystemRoot
    triggers Windows PowerShell error 8009001d) and silently drops
    -Environment values."""
    text = FINALIZER.read_text(encoding="utf-8")

    assert "System.Diagnostics.ProcessStartInfo" in text
    assert "$ProbeStartInfo.UserName" in text
    assert "$ProbeStartInfo.Domain" in text
    assert "$ProbeStartInfo.Password" in text
    assert "$ProbeStartInfo.UseShellExecute = $false" in text
    assert "$ProbeEnvironment.Clear()" in text
    assert "-UseNewEnvironment" not in text

    assert '$ProbeEnvironment["SystemRoot"]' in text
    assert '$ProbeEnvironment["WINDIR"]' in text
    assert '$ProbeEnvironment["ComSpec"]' in text
    assert "[EnvironmentVariableTarget]::Machine" in text
    assert "AUDITOR_PROBE_CLEAN_ENVIRONMENT_INJECTION_UNSUPPORTED" in text


def test_auditor_probe_environment_allowlist_is_minimal():
    """Only Windows bootstrap values may be forwarded to the auditor child."""
    text = FINALIZER.read_text(encoding="utf-8")

    start = text.index("$ProbeEnvironment.Clear()")
    end = text.index("$Process.StartInfo = $ProbeStartInfo")
    allowlist_block = text[start:end]

    assigned_keys = set()
    for line in allowlist_block.splitlines():
        stripped = line.strip()
        if "$ProbeEnvironment[" in stripped and "]" in stripped:
            assigned_keys.add(stripped.split("[")[1].split("]")[0].strip('"'))

    assert assigned_keys, "no environment keys assigned to probe child"
    assert assigned_keys <= {"SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT"}, (
        f"unexpected environment keys forwarded to auditor child: {assigned_keys}"
    )
    assert "SystemRoot" in assigned_keys

    for forbidden in (
        "OPENAI",
        "ANTHROPIC",
        "GEMINI",
        "BRAIN_API_KEY",
        "API_KEY",
        "PASSWORD",
        "SECRET",
        "IBKR_AUTONOMOUS_PAPER_ARMED",
        "GetEnvironmentVariables()",
    ):
        assert forbidden not in allowlist_block, forbidden


@pytest.mark.skipif(os.name != "nt", reason="PowerShell path validation is Windows-only")
def test_clean_environment_probe_child_boots_windows_powershell():
    """Mechanism proof for explicit clean child environment."""
    probe_script = Path(os.environ.get("TEMP", ".")) / "glm_probe_child_env_probe.ps1"
    probe_script.write_text(
        'Write-Output ("SR=" + $env:SystemRoot)\n'
        'Write-Output ("MARKER=" + [string]$env:GLM_TEST_PARENT_MARKER)\n',
        encoding="utf-8",
    )
    try:
        command = (
            "$env:GLM_TEST_PARENT_MARKER='leak';"
            "$psi=New-Object System.Diagnostics.ProcessStartInfo;"
            "$psi.FileName='powershell.exe';"
            f"$psi.Arguments='-NoProfile -ExecutionPolicy Bypass -File '+[char]34+'{probe_script}'+[char]34;"
            "$psi.UseShellExecute=$false;"
            "$psi.RedirectStandardOutput=$true;"
            "$psi.RedirectStandardError=$true;"
            "$env0=$psi.EnvironmentVariables;"
            "$env0.Clear();"
            "$env0['SystemRoot']=$env:SystemRoot;"
            "$env0['WINDIR']=$env:WINDIR;"
            "$env0['ComSpec']=$env:ComSpec;"
            "$env0['PATH']=[Environment]::GetEnvironmentVariable('PATH','Machine');"
            "$env0['PATHEXT']=[Environment]::GetEnvironmentVariable('PATHEXT','Machine');"
            "$p=[System.Diagnostics.Process]::Start($psi);"
            "$out=$p.StandardOutput.ReadToEnd();"
            "$p.WaitForExit();"
            "Write-Output $out;"
            "if($p.ExitCode -ne 0){exit 1}"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SR=C:\\Windows" in result.stdout, result.stdout + result.stderr
        assert "MARKER=" in result.stdout
        assert "MARKER=leak" not in result.stdout
    finally:
        probe_script.unlink(missing_ok=True)
