from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVISIONING = ROOT / "AUDITOR_WINDOWS_PROVISIONING_V1.ps1"
FINALIZER = ROOT / "FINALIZE_IBKR_PREREQUISITES.ps1"

REQUIRED_TARGETS = {
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


def test_provisioning_active_target_block_is_repo_rooted() -> None:
    text = PROVISIONING.read_text(encoding="utf-8")
    assert '[string]$RepoRoot = ""' in text
    assert "$RepoRoot = $PSScriptRoot" in text
    assert "REPO_ROOT_NOT_SCRIPT_ROOT" in text
    assert '$LiveStateRoot = Join-Path $ResolvedRepoRoot "state\\ibkr_paper_30d"' in text

    start = text.index("$ProbeTargets = [ordered]@{")
    end = text.index("# Exact predecessor contract", start)
    active = text[start:end]
    assert "BROKER_NETWORK_SOCKET_ACCESS" in active
    assert "C:\\AI_VAULT\\" not in active
    assert active.count("$ResolvedRepoRoot") >= 5

    keys = set()
    for line in active.splitlines():
        stripped = line.strip()
        if " = " in stripped and not stripped.startswith("$"):
            keys.add(stripped.split(" = ", 1)[0])
    assert REQUIRED_TARGETS - {"SMTP_SECRET_READ"} <= keys
    assert '$ProbeTargets[("SM" + "TP_SECRET_READ")]' in active


def test_old_root_is_legacy_only_and_apply_does_not_mutate_it() -> None:
    text = PROVISIONING.read_text(encoding="utf-8")
    assert '$LegacyRepoRoot = "C:\\AI_VAULT"' in text
    assert "Test-ProbeTargetMapEqual" in text
    assert 'result = "PRESERVED_LEGACY_ROOT"' in text
    assert "legacy_cleanup = $false" in text

    apply_start = text.index("function Invoke-Apply")
    rollback_start = text.index("function Get-PartialRollbackManifest", apply_start)
    apply_body = text[apply_start:rollback_start]
    assert "Remove-ManifestAce -Change $LegacyChange" not in apply_body


def test_apply_preflights_existing_change_manifest_before_mutation() -> None:
    text = PROVISIONING.read_text(encoding="utf-8")
    start = text.index("function Invoke-Apply")
    end = text.index("function Get-PartialRollbackManifest", start)
    body = text[start:end]
    preflight = body.index("$ExistingChangeManifest")
    first_managed_mutation = body.index("foreach ($Path in $ManagedPaths)")
    assert preflight < first_managed_mutation
    assert "Test-RecognizedLegacyChangeManifest" in body
    assert "PROVISIONING_MANIFEST_CONFLICT" in body
    assert "$LegacyApprovedPaths" in text
    assert "$LegacyActiveApprovedPaths" in text


def test_finalizer_validates_manifest_semantics_before_reuse() -> None:
    text = FINALIZER.read_text(encoding="utf-8")
    assert "function Test-AuditorTargetManifestCurrent" in text
    assert "AUDITOR_TARGET_MANIFEST_STALE_AFTER_PROVISIONING" in text
    assert "-Mode Apply -RepoRoot $ResolvedRepoRoot" in text
    assert "-Confirm:$false" not in text
    assert "$TargetManifestCurrent = Test-AuditorTargetManifestCurrent" in text
    assert "$ExistingTargetManifest = Test-Path" not in text

    required_block = text[
        text.index("$RequiredProbeTargetNames = @(") :
        text.index("function Test-StringSetEqualOrdinalIgnoreCase")
    ]
    for name in REQUIRED_TARGETS:
        assert f'"{name}"' in required_block


def test_finalizer_manifest_contract_binds_repo_scoped_targets_to_active_root() -> None:
    text = FINALIZER.read_text(encoding="utf-8")
    fn_start = text.index("function Test-AuditorTargetManifestCurrent")
    fn_end = text.index("Assert-Administrator", fn_start)
    function = text[fn_start:fn_end]

    assert 'Join-Path $RepoRoot "Secrets"' in function
    assert 'Join-Path $RepoRoot "state\\ibkr_paper_30d"' in function
    assert 'Join-Path $RepoRoot "ibkr_paper_30d\\broker.py"' in function
    assert 'Join-Path $RepoRoot "ibkr_paper_30d\\trader_invocation.py"' in function
    assert "C:\\AI_VAULT\\" not in function
    assert "Test-StringSetEqualOrdinalIgnoreCase" in function
