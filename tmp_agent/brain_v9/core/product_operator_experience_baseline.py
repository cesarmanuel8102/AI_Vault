"""Pure R18.1 product and operator experience baseline with no runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ProductOperatorExperienceReceipt:
    decision: str
    runtime_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_product_operator_experience_baseline(
    *,
    chat_dashboard_visible: bool,
    trace_console_visible: bool,
    notifications_visible: bool,
    operator_inbox_visible: bool,
    responsive_accessibility_verified: bool,
    approval_visibility_verified: bool,
    incident_visibility_verified: bool,
    private_reasoning_exposed: bool,
    runtime_start_requested: bool,
    network_call: bool,
    scheduler_activation: bool,
    canonical_local_sync: bool,
    live_trading: bool,
    real_money: bool,
    auto_merge: bool,
) -> ProductOperatorExperienceReceipt:
    """Assess static UX requirements; never start or alter a runtime."""
    values = {
        "chat_dashboard_visible": chat_dashboard_visible,
        "trace_console_visible": trace_console_visible,
        "notifications_visible": notifications_visible,
        "operator_inbox_visible": operator_inbox_visible,
        "responsive_accessibility_verified": responsive_accessibility_verified,
        "approval_visibility_verified": approval_visibility_verified,
        "incident_visibility_verified": incident_visibility_verified,
        "private_reasoning_exposed": private_reasoning_exposed,
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
        (not chat_dashboard_visible, "chat_dashboard_required"),
        (not trace_console_visible, "trace_console_required"),
        (not notifications_visible, "notifications_required"),
        (not operator_inbox_visible, "operator_inbox_required"),
        (not responsive_accessibility_verified, "responsive_accessibility_required"),
        (not approval_visibility_verified, "approval_visibility_required"),
        (not incident_visibility_verified, "incident_visibility_required"),
        (private_reasoning_exposed, "private_reasoning_forbidden"),
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
    decision = "BASELINE_VERIFIED" if not denial_reasons else "REJECT"
    return ProductOperatorExperienceReceipt(
        decision=decision,
        runtime_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(
            {"decision": decision, "runtime_permitted": False, "denial_reasons": denial_reasons, "values": values}
        ),
    )
