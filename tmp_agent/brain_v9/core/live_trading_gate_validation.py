"""Pure R16.2 validation of a disabled LiveTradingGate and paper rollback evidence."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


_EFFECTFUL_OPERATIONS = frozenset(
    {
        "broker_connect",
        "broker_order",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class DisabledStatePaperRollbackReceipt:
    validation_passed: bool
    disabled_state_verified: bool
    unauthorized_live_attempt_denied: bool
    paper_rollback_verified: bool
    kill_switch_receipt: bool
    execution_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def validate_disabled_state_paper_rollback(
    *,
    human_final_authority: bool,
    paper_only: bool,
    live_trading_enabled: bool,
    real_money_enabled: bool,
    unauthorized_live_attempt: bool,
    paper_rollback_requested: bool,
    kill_switch_engaged: bool,
    broker_action: bool,
    provider_call: bool,
    network_call: bool,
    runtime_execution: bool,
    scheduler_activation: bool,
) -> DisabledStatePaperRollbackReceipt:
    """Create validation evidence only; this function cannot perform an external effect."""
    values = {
        "human_final_authority": human_final_authority,
        "paper_only": paper_only,
        "live_trading_enabled": live_trading_enabled,
        "real_money_enabled": real_money_enabled,
        "unauthorized_live_attempt": unauthorized_live_attempt,
        "paper_rollback_requested": paper_rollback_requested,
        "kill_switch_engaged": kill_switch_engaged,
        "broker_action": broker_action,
        "provider_call": provider_call,
        "network_call": network_call,
        "runtime_execution": runtime_execution,
        "scheduler_activation": scheduler_activation,
    }
    reasons: list[str] = [
        f"invalid_{name}" for name, value in values.items() if not isinstance(value, bool)
    ]
    checks = (
        (not human_final_authority, "human_final_authority_required"),
        (not paper_only, "paper_only_required"),
        (live_trading_enabled, "live_trading_must_remain_disabled"),
        (real_money_enabled, "real_money_must_remain_disabled"),
        (not unauthorized_live_attempt, "live_attempt_denial_evidence_required"),
        (not paper_rollback_requested, "paper_rollback_required"),
        (not kill_switch_engaged, "kill_switch_receipt_required"),
        (broker_action, "broker_action_forbidden"),
        (provider_call, "provider_call_forbidden"),
        (network_call, "network_call_forbidden"),
        (runtime_execution, "runtime_execution_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
    )
    reasons.extend(reason for invalid, reason in checks if invalid)
    validation_passed = not reasons
    if unauthorized_live_attempt:
        reasons.append("unauthorized_live_attempt_denied")
    denial_reasons = tuple(sorted(set(reasons)))
    disabled_state_verified = (
        not live_trading_enabled
        and not real_money_enabled
        and not broker_action
        and not provider_call
        and not network_call
        and not runtime_execution
        and not scheduler_activation
    )
    paper_rollback_verified = (
        validation_passed and paper_only and paper_rollback_requested and kill_switch_engaged
    )
    identity = {
        "denial_reasons": denial_reasons,
        "disabled_state_verified": disabled_state_verified,
        "paper_rollback_verified": paper_rollback_verified,
        "values": values,
        "validation_passed": validation_passed,
    }
    return DisabledStatePaperRollbackReceipt(
        validation_passed=validation_passed,
        disabled_state_verified=disabled_state_verified,
        unauthorized_live_attempt_denied=(
            unauthorized_live_attempt and not live_trading_enabled
        ),
        paper_rollback_verified=paper_rollback_verified,
        kill_switch_receipt=kill_switch_engaged,
        execution_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(identity),
    )


def reject_disabled_state_effect(operation: str) -> None:
    """Fail closed for every operation outside disabled-state validation."""
    if operation in _EFFECTFUL_OPERATIONS:
        raise ValueError("disabled_state_validation_no_effects")
    raise ValueError("unsupported_disabled_state_validation_operation")
