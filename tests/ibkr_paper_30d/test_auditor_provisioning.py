from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "AUDITOR_WINDOWS_PROVISIONING_V1.ps1"
PROBE_SCRIPT = ROOT / "auditor_runtime" / "AUDITOR_DENIAL_PROBE_V1.ps1"
PROGRAM_ROOT = Path("C:/ProgramData/CodexAuditorV1")
LIVE_STATE_ROOT = r"C:\AI_VAULT\state\ibkr_paper_30d"
LEGACY_EPHEMERAL_PATHS = {
    rf"{LIVE_STATE_ROOT}\reports\real_codex_invocations.sqlite3",
    rf"{LIVE_STATE_ROOT}\reports\real_codex_invocations.sqlite3-wal",
    rf"{LIVE_STATE_ROOT}\reports\real_codex_invocations.sqlite3-shm",
    rf"{LIVE_STATE_ROOT}\execution.lock",
}
APPROVED_AUDITOR_PATHS = {
    r"C:\ProgramData\CodexAuditorV1\runtime",
    r"C:\ProgramData\CodexAuditorV1\exports",
    r"C:\ProgramData\CodexAuditorV1\reports",
    r"C:\ProgramData\CodexAuditorV1\provisioning",
    r"C:\AI_VAULT\Secrets",
    r"C:\Jts",
    LIVE_STATE_ROOT,
    r"C:\AI_VAULT\ibkr_paper_30d\broker.py",
    r"C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py",
}


@pytest.fixture
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture
def probe_script_text() -> str:
    return PROBE_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def review_result():
    before = PROGRAM_ROOT.exists()
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "Review",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    result.before_program_root = before
    result.after_program_root = PROGRAM_ROOT.exists()
    return result


@pytest.fixture
def review_manifest(review_result) -> dict[str, object]:
    prefix = "MANIFEST_JSON="
    line = next(
        item for item in review_result.stdout.splitlines() if item.startswith(prefix)
    )
    return json.loads(line.removeprefix(prefix))


def test_script_has_no_self_elevation_or_uac_bypass(script_text) -> None:
    forbidden = (
        "-Verb RunAs",
        "ConsentPromptBehaviorAdmin",
        "EnableLUA",
        "EncodedCommand",
        "Start-Process",
    )
    assert not any(token.lower() in script_text.lower() for token in forbidden)


def test_review_mode_is_default_and_nonmutating(review_result) -> None:
    assert review_result.returncode == 0, review_result.stderr
    assert "HUMAN_INFRASTRUCTURE_ACTION_REQUIRED=true" in review_result.stdout
    assert review_result.before_program_root == review_result.after_program_root


def test_manifest_names_only_approved_paths_and_firewall_ports(
    review_manifest,
) -> None:
    assert set(review_manifest["broker_ports"]) == {4001, 4002}
    assert set(review_manifest["paths"]) <= APPROVED_AUDITOR_PATHS
    assert review_manifest["account_name"] == "CodexAuditorV1"


def test_apply_checks_elevation_before_password_or_mutation(script_text) -> None:
    marker = "# ADMIN-CHECK-BEFORE-MUTATION"
    assert marker in script_text
    main = script_text.split(marker, 1)[1]
    guard = main.index("ADMINISTRATOR_REQUIRED")
    password = main.index("Read-Host")
    apply_call = main.index("Invoke-Apply")
    assert guard < password < apply_call


def test_acl_updates_are_additive_and_manifest_owned(script_text) -> None:
    assert "AddAccessRule" in script_text
    assert "RemoveAccessRuleSpecific" in script_text
    assert "SetAccessRuleProtection" not in script_text
    assert "ResetAccessRule" not in script_text
    assert "SetAccessRule" not in script_text
    assert "FileSystemAccessRule" in script_text


def test_firewall_rule_is_sid_scoped_and_manifest_owned(script_text) -> None:
    assert "New-NetFirewallRule" in script_text
    assert "Set-NetFirewallRule" in script_text
    assert "-LocalUser" in script_text
    assert "CodexAuditorV1-Broker-Loopback-Block" in script_text
    assert "Remove-NetFirewallRule" in script_text


def test_static_security_boundaries_exclude_unapproved_surfaces(script_text) -> None:
    lowered = script_text.lower()
    assert "brain" not in lowered
    assert "hive" not in lowered
    assert "set-itemproperty" not in lowered
    assert "new-itemproperty" not in lowered
    assert "smtp" not in lowered
    assert "credential" not in lowered
    assert "get-childitem -recurse" not in lowered
    assert "icacls" not in lowered


def test_powershell_ast_has_no_parse_errors() -> None:
    escaped = str(SCRIPT).replace("'", "''")
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


def test_review_manifest_contains_validation_and_rollback(review_manifest) -> None:
    assert review_manifest["apply_command"].endswith("-Mode Apply")
    assert review_manifest["rollback_command"].endswith(
        "-Mode Rollback -ConfirmRollback"
    )
    assert review_manifest["validation_commands"]
    assert review_manifest["acl_changes"]


def test_partial_apply_firewall_failure_has_recognized_recovery_contract(
    review_manifest,
) -> None:
    recovery = review_manifest["partial_apply_recovery"]
    assert set(recovery["recognized_predecessor_script_sha256"]) == {
        "899d262124bbf24e0dbd4661b8df41f93aeb6993dacfe9a200264ad2e9ed6eb7",
        "ba6ab5e885c6da54141cfaef85a59ae7e9e6cb2102b23607ae91fdaadfbb057c",
    }
    assert recovery["change_manifest_may_be_missing"] is True
    assert recovery["repair_probe_manifest"] is True
    assert recovery["upgrade_runtime_files"] is True


def test_recovery_contract_covers_fresh_both_partial_and_rerun_states(
    review_manifest,
) -> None:
    recovery = review_manifest["partial_apply_recovery"]
    assert set(recovery["recognized_states"]) == {
        "FRESH",
        "FIRST_FIREWALL_FAILURE_PARTIAL",
        "SECOND_REPLACE_FAILURE_PARTIAL",
        "CURRENT_COMPLETE_RERUN",
    }
    assert set(recovery["rollback_supported_states"]) == {
        "FIRST_FIREWALL_FAILURE_PARTIAL",
        "SECOND_REPLACE_FAILURE_PARTIAL",
        "CURRENT_COMPLETE_RERUN",
    }


def test_apply_rerun_repairs_only_recognized_partial_state(script_text) -> None:
    assert "Test-RecognizedLegacyProbeManifest" in script_text
    assert "Test-RecognizedLegacyRuntimeManifest" in script_text
    assert "PARTIAL_STATE_UNRECOGNIZED" in script_text
    assert "Replace-FileAtomically" in script_text


@pytest.mark.parametrize(
    "leaf_name",
    [
        "real_codex_invocations.sqlite3-wal",
        "real_codex_invocations.sqlite3-shm",
        "execution.lock",
    ],
)
def test_missing_ephemeral_leaf_is_not_an_apply_target(
    review_manifest, leaf_name
) -> None:
    protected_denies = {
        change["path"]
        for change in review_manifest["acl_changes"]
        if change["type"] == "Deny" and change["rights"] == "FullControl"
    }
    assert LIVE_STATE_ROOT in protected_denies
    assert not any(path.endswith(leaf_name) for path in protected_denies)


def test_live_state_parent_denial_inherits_to_future_files(review_manifest) -> None:
    parent_change = next(
        change
        for change in review_manifest["acl_changes"]
        if change["path"] == LIVE_STATE_ROOT
    )
    assert parent_change == {
        "path": LIVE_STATE_ROOT,
        "rights": "FullControl",
        "type": "Deny",
        "directory": True,
        "identity": "CodexAuditorV1",
    }
    inheritance = review_manifest["live_state_inheritance"]
    assert inheritance["flags"] == ["ContainerInherit", "ObjectInherit"]
    assert inheritance["propagation"] == "None"
    assert inheritance["preserves_unrelated_aces"] is True


def test_firewall_avoids_unsupported_ipv6_loopback_literal(review_manifest) -> None:
    firewall = review_manifest["firewall_rule"]
    assert firewall["remote_addresses"] == ["Any"]
    assert set(firewall["address_families"]) == {"IPv4", "IPv6"}
    assert "::1" not in firewall["remote_addresses"]


def test_actual_auditor_broker_denial_requires_dual_stack_probe(
    review_manifest, probe_script_text
) -> None:
    required = set(review_manifest["firewall_rule"]["required_probe_endpoints"])
    assert required == {
        "127.0.0.1:4001",
        "127.0.0.1:4002",
        "[::1]:4001",
        "[::1]:4002",
    }
    assert '"127.0.0.1"' in probe_script_text
    assert '"::1"' in probe_script_text
    assert "[Net.IPAddress]::Parse($Address)" in probe_script_text
    assert "TcpClient($IpAddress.AddressFamily)" in probe_script_text
    assert "network_endpoints" in probe_script_text
    assert "NOT_PROVEN" in probe_script_text


def test_acl_remediation_preserves_unrelated_aces(script_text) -> None:
    assert "AddAccessRule" in script_text
    assert "RemoveAccessRuleSpecific" in script_text
    assert "SetAccessRuleProtection" not in script_text
    assert "PurgeAccessRules" not in script_text
    assert "SetAccessRule(" not in script_text


def test_rollback_after_partial_apply_removes_only_subsystem_owned_changes(
    review_manifest, script_text
) -> None:
    legacy_paths = {
        change["path"] for change in review_manifest["legacy_acl_changes"]
    }
    assert legacy_paths == LEGACY_EPHEMERAL_PATHS
    assert "PROVISIONING_MANIFEST_MISSING" not in script_text
    assert "Get-PartialRollbackManifest" in script_text
    assert "RemoveAccessRuleSpecific" in script_text
    assert "Remove-LocalUser -Name $AccountName" in script_text


def run_atomic_replace_case(
    tmp_path: Path, *, destination_exists: bool
) -> subprocess.CompletedProcess[str]:
    root = str(tmp_path).replace("'", "''")
    script = str(SCRIPT).replace("'", "''")
    destination_setup = (
        "[IO.File]::WriteAllText($destination, 'old');"
        if destination_exists
        else ""
    )
    command = (
        "$tokens=$null;$errors=$null;"
        "$ast=[Management.Automation.Language.Parser]::ParseFile("
        f"'{script}',[ref]$tokens,[ref]$errors);"
        "$fn=$ast.Find({param($node) "
        "$node -is [Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -eq 'Replace-FileAtomically'},$true);"
        "Invoke-Expression $fn.Extent.Text;"
        f"$root='{root}';"
        "$source=Join-Path $root 'source.tmp';"
        "$destination=Join-Path $root 'destination.txt';"
        "$script:AtomicDestinationPaths=@($destination);"
        "[IO.File]::WriteAllText($source,'new');"
        f"{destination_setup}"
        "Replace-FileAtomically -SourcePath $source -DestinationPath $destination;"
        "if([IO.File]::ReadAllText($destination) -cne 'new'){throw 'CONTENT_MISMATCH'};"
        "if([IO.File]::ReadAllText($source) -cne 'new'){throw 'SOURCE_CHANGED'};"
        "$debris=@(Get-ChildItem -LiteralPath $root -File | "
        "Where-Object {$_.FullName -ne $source -and "
        "($_.Name -like '*.tmp' -or $_.Name -like '*.bak')});"
        "if($debris.Count){throw 'ATOMIC_REPLACE_DEBRIS'};"
        "Write-Output 'ATOMIC_REPLACE_PASS'"
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_atomic_replace_existing_destination_works_on_windows_powershell_51(
    tmp_path,
) -> None:
    result = run_atomic_replace_case(tmp_path, destination_exists=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ATOMIC_REPLACE_PASS" in result.stdout


def test_atomic_replace_missing_destination_uses_safe_create_path(tmp_path) -> None:
    result = run_atomic_replace_case(tmp_path, destination_exists=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ATOMIC_REPLACE_PASS" in result.stdout


def test_atomic_replace_validates_nonempty_absolute_backup_path(script_text) -> None:
    assert "GetFullPath($BackupPath)" in script_text
    assert "[string]::IsNullOrWhiteSpace($BackupPath)" in script_text
    assert "Test-Path -LiteralPath $DestinationPath -PathType Leaf" in script_text
    assert "[IO.File]::Replace($TemporaryPath, $DestinationPath, $BackupPath, $true)" in script_text


def test_atomic_text_replace_existing_destination_uses_validated_primitive(
    tmp_path,
) -> None:
    root = str(tmp_path).replace("'", "''")
    script = str(SCRIPT).replace("'", "''")
    command = (
        "$tokens=$null;$errors=$null;"
        "$ast=[Management.Automation.Language.Parser]::ParseFile("
        f"'{script}',[ref]$tokens,[ref]$errors);"
        "$names=@('Replace-FileAtomically','Write-TextAtomically');"
        "$functions=$ast.FindAll({param($node) "
        "$node -is [Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -in $names},$true);"
        "$functions | ForEach-Object {Invoke-Expression $_.Extent.Text};"
        f"$root='{root}';"
        "$destination=Join-Path $root 'manifest.json';"
        "$script:AtomicDestinationPaths=@($destination);"
        "[IO.File]::WriteAllText($destination,'old');"
        "Write-TextAtomically -DestinationPath $destination -Text 'new';"
        "if([IO.File]::ReadAllText($destination) -cne 'new'){throw 'CONTENT_MISMATCH'};"
        "$debris=@(Get-ChildItem -LiteralPath $root -File | "
        "Where-Object {$_.Name -like '*.tmp' -or $_.Name -like '*.bak'});"
        "if($debris.Count){throw 'ATOMIC_REPLACE_DEBRIS'};"
        "Write-Output 'ATOMIC_TEXT_REPLACE_PASS'"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ATOMIC_TEXT_REPLACE_PASS" in result.stdout
