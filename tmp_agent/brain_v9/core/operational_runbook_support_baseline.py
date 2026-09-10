"""Pure R18.2 operational runbook and support-surface baseline."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class OperationalRunbookSupportReceipt:
    decision: str
    runtime_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_operational_runbook_support_baseline(
    *,
    install_runbook_documented: bool,
    upgrade_runbook_documented: bool,
    backup_runbook_documented: bool,
    restore_rollback_documented: bool,
    release_notes_documented: bool,
    health_version_visible: bool,
    support_bundle_redacted: bool,
    actionable_errors_documented: bool,
    destructive_restore_requested: bool,
    secret_in_support_bundle: bool,
    runtime_start_requested: bool,
    network_call: bool,
    scheduler_activation: bool,
    canonical_local_sync: bool,
    live_trading: bool,
    real_money: bool,
    auto_merge: bool,
) -> OperationalRunbookSupportReceipt:
    """Assess static support requirements; this baseline never permits runtime effects."""
    values = {
        "install_runbook_documented": install_runbook_documented,
        "upgrade_runbook_documented": upgrade_runbook_documented,
        "backup_runbook_documented": backup_runbook_documented,
        "restore_rollback_documented": restore_rollback_documented,
        "release_notes_documented": release_notes_documented,
        "health_version_visible": health_version_visible,
        "support_bundle_redacted": support_bundle_redacted,
        "actionable_errors_documented": actionable_errors_documented,
        "destructive_restore_requested": destructive_restore_requested,
        "secret_in_support_bundle": secret_in_support_bundle,
        "runtime_start_requested": runtime_start_requested,
        "network_call": network_call,
        "scheduler_activation": scheduler_activation,
        "canonical_local_sync": canonical_local_sync,
        "live_trading": live_trading,
        "real_money": real_money,
        "auto_merge": auto_merge,
    }
    reasons = [f"invalid_{name}" for name, value in values.items() if not isinstance(value, bool)]
    checks = (
        (not install_runbook_documented, "install_runbook_required"),
        (not upgrade_runbook_documented, "upgrade_runbook_required"),
        (not backup_runbook_documented, "backup_runbook_required"),
        (not restore_rollback_documented, "restore_rollback_runbook_required"),
        (not release_notes_documented, "release_notes_required"),
        (not health_version_visible, "health_version_visibility_required"),
        (not support_bundle_redacted, "support_bundle_redaction_required"),
        (not actionable_errors_documented, "actionable_errors_required"),
        (destructive_restore_requested, "destructive_restore_forbidden"),
        (secret_in_support_bundle, "secret_in_support_bundle_forbidden"),
        (runtime_start_requested, "runtime_start_forbidden"),
        (network_call, "network_call_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
        (canonical_local_sync, "canonical_local_sync_forbidden"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
        (auto_merge, "auto_merge_forbidden"),
    )
    reasons.extend(reason for invalid, reason in checks if invalid)
    denial_reasons = tuple(sorted(set(reasons)))
    decision = "SUPPORT_SURFACE_VERIFIED" if not denial_reasons else "REJECT"
    return OperationalRunbookSupportReceipt(
        decision=decision,
        runtime_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(
            {"decision": decision, "runtime_permitted": False, "denial_reasons": denial_reasons, "values": values}
        ),
    )
