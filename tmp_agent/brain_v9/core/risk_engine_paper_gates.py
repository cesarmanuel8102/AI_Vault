"""Deterministic paper-only loss, exposure, and market failure gates for R12.2.

The module creates immutable risk evidence only. It never connects to a broker,
submits an order, imports a financial runtime, or performs a network action.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


_BPS = 10_000
_THRESHOLDS = {
    "daily_loss_bps": 200,
    "weekly_drawdown_bps": 600,
    "gross_exposure_bps": 7000,
}
_FORBIDDEN_EFFECTS = frozenset(
    {
        "broker_connect",
        "broker_order",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "configuration_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class PaperRiskGateDecision:
    approved: bool
    paper_only: bool
    denial_reasons: tuple[str, ...]
    thresholds: dict[str, int]
    decision_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def _validate_bps(value: int, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _BPS:
        raise ValueError(f"invalid_{field}")


def _validate_bool(value: bool, field: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"invalid_{field}")


def evaluate_paper_risk_gates(
    *,
    daily_loss_bps: int,
    weekly_drawdown_bps: int,
    gross_exposure_bps: int,
    kill_switch_active: bool,
    market_data_stale: bool,
    broker_connected: bool,
    duplicate_order_detected: bool,
    reconciliation_ok: bool,
) -> PaperRiskGateDecision:
    """Evaluate fixed paper-only gates without any external financial effect."""
    _validate_bps(daily_loss_bps, "daily_loss_bps")
    _validate_bps(weekly_drawdown_bps, "weekly_drawdown_bps")
    _validate_bps(gross_exposure_bps, "gross_exposure_bps")
    _validate_bool(kill_switch_active, "kill_switch_active")
    _validate_bool(market_data_stale, "market_data_stale")
    _validate_bool(broker_connected, "broker_connected")
    _validate_bool(duplicate_order_detected, "duplicate_order_detected")
    _validate_bool(reconciliation_ok, "reconciliation_ok")

    reasons: list[str] = []
    if not broker_connected:
        reasons.append("broker_disconnected")
    if daily_loss_bps >= _THRESHOLDS["daily_loss_bps"]:
        reasons.append("daily_loss_limit_reached")
    if duplicate_order_detected:
        reasons.append("duplicate_order_detected")
    if gross_exposure_bps > _THRESHOLDS["gross_exposure_bps"]:
        reasons.append("gross_exposure_limit_exceeded")
    if kill_switch_active:
        reasons.append("kill_switch_active")
    if market_data_stale:
        reasons.append("market_data_stale")
    if not reconciliation_ok:
        reasons.append("reconciliation_failure")
    if weekly_drawdown_bps >= _THRESHOLDS["weekly_drawdown_bps"]:
        reasons.append("weekly_drawdown_limit_reached")

    denial_reasons = tuple(sorted(reasons))
    decision_payload = {
        "approved": not denial_reasons,
        "denial_reasons": denial_reasons,
        "gross_exposure_bps": gross_exposure_bps,
        "paper_only": True,
        "thresholds": _THRESHOLDS,
        "weekly_drawdown_bps": weekly_drawdown_bps,
        "daily_loss_bps": daily_loss_bps,
        "kill_switch_active": kill_switch_active,
        "market_data_stale": market_data_stale,
        "broker_connected": broker_connected,
        "duplicate_order_detected": duplicate_order_detected,
        "reconciliation_ok": reconciliation_ok,
    }
    return PaperRiskGateDecision(
        approved=not denial_reasons,
        paper_only=True,
        denial_reasons=denial_reasons,
        thresholds=dict(_THRESHOLDS),
        decision_sha256=_canonical_sha256(decision_payload),
    )


def reject_paper_risk_gate_effect(operation: str) -> None:
    """Fail closed for every operation outside the paper-only gate contract."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("paper_only_risk_engine_no_effects")
    raise ValueError("unsupported_paper_only_risk_engine_operation")
