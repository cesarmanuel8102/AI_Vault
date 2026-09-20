from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "AUDITOR_WINDOWS_PROVISIONING_V1.ps1"
PROGRAM_ROOT = Path("C:/ProgramData/CodexAuditorV1")
APPROVED_AUDITOR_PATHS = {
    r"C:\ProgramData\CodexAuditorV1\runtime",
    r"C:\ProgramData\CodexAuditorV1\exports",
    r"C:\ProgramData\CodexAuditorV1\reports",
    r"C:\ProgramData\CodexAuditorV1\provisioning",
    r"C:\AI_VAULT\Secrets",
    r"C:\Jts",
    r"C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3",
    r"C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3-wal",
    r"C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3-shm",
    r"C:\AI_VAULT\state\ibkr_paper_30d\execution.lock",
    r"C:\AI_VAULT\ibkr_paper_30d\broker.py",
    r"C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py",
}


@pytest.fixture
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


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
