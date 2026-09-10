"""Pure R18.3 product operations acceptance and accessibility validation."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ProductOperationsAcceptanceReceipt:
    decision: str
    runtime_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_product_operations_acceptance_accessibility(
    *,
    operator_workflow_accepted: bool,
    accessibility_verified: bool,
    responsive_behavior_verified: bool,
    incident_ui_verified: bool,
    hidden_operational_dependency: bool,
    unaudited_release: bool,
    runtime_start_requested: bool,
    network_call: bool,
    scheduler_activation: bool,
    canonical_local_sync: bool,
    live_trading: bool,
    real_money: bool,
    auto_merge: bool,
) -> ProductOperationsAcceptanceReceipt:
    """Assess static acceptance evidence; this contract never permits runtime effects."""
    values = {
        "operator_workflow_accepted": operator_workflow_accepted,
        "accessibility_verified": accessibility_verified,
        "responsive_behavior_verified": responsive_behavior_verified,
        "incident_ui_verified": incident_ui_verified,
        "hidden_operational_dependency": hidden_operational_dependency,
        "unaudited_release": unaudited_release,
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
        (not operator_workflow_accepted, "operator_workflow_acceptance_required"),
        (not accessibility_verified, "accessibility_verification_required"),
        (not responsive_behavior_verified, "responsive_behavior_required"),
        (not incident_ui_verified, "incident_ui_verification_required"),
        (hidden_operational_dependency, "hidden_operational_dependency_forbidden"),
        (unaudited_release, "unaudited_release_forbidden"),
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
    decision = "ACCEPTANCE_VERIFIED" if not denial_reasons else "REJECT"
    return ProductOperationsAcceptanceReceipt(
        decision=decision,
        runtime_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(
            {"decision": decision, "runtime_permitted": False, "denial_reasons": denial_reasons, "values": values}
        ),
    )
