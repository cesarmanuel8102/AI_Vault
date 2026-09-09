"""Deterministic paper-only portfolio regime and attribution validation for R12.3."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from tmp_agent.brain_v9.core.risk_engine_paper_gates import PaperRiskGateDecision


_BPS = 10_000
_MAX_GROSS_EXPOSURE_BPS = 7_000
_REGIMES = frozenset({"risk_on", "neutral", "risk_off"})
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
class PaperPortfolioRegimeValidation:
    approved: bool
    paper_only: bool
    regime: str
    rebalance_delta_bps: int
    denial_reasons: tuple[str, ...]
    attribution: dict[str, int]
    validation_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def _validate_bps(value: int, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _BPS:
        raise ValueError(f"invalid_{field}")


def validate_paper_only_portfolio_regime(
    *,
    regime: str,
    current_gross_exposure_bps: int,
    target_gross_exposure_bps: int,
    risk_gate_decision: PaperRiskGateDecision,
    var_bps: int,
    cvar_bps: int,
    liquidity_bps: int,
    slippage_bps: int,
    fees_bps: int,
    gap_bps: int,
) -> PaperPortfolioRegimeValidation:
    """Produce paper-only regime validation evidence; never rebalance a portfolio."""
    if regime not in _REGIMES:
        raise ValueError("invalid_regime")
    for field, value in {
        "current_gross_exposure_bps": current_gross_exposure_bps,
        "target_gross_exposure_bps": target_gross_exposure_bps,
        "var_bps": var_bps,
        "cvar_bps": cvar_bps,
        "liquidity_bps": liquidity_bps,
        "slippage_bps": slippage_bps,
        "fees_bps": fees_bps,
        "gap_bps": gap_bps,
    }.items():
        _validate_bps(value, field)
    if not isinstance(risk_gate_decision, PaperRiskGateDecision):
        raise ValueError("invalid_risk_gate_decision")

    reasons: list[str] = []
    if not risk_gate_decision.approved:
        reasons.append("risk_gate_denied")
    if target_gross_exposure_bps > _MAX_GROSS_EXPOSURE_BPS:
        reasons.append("gross_exposure_limit_exceeded")
    if regime == "risk_off" and target_gross_exposure_bps > current_gross_exposure_bps:
        reasons.append("risk_off_exposure_increase_denied")
    if cvar_bps < var_bps:
        reasons.append("cvar_below_var")

    denial_reasons = tuple(sorted(reasons))
    attribution = {
        "cvar_bps": cvar_bps,
        "fees_bps": fees_bps,
        "gap_bps": gap_bps,
        "liquidity_bps": liquidity_bps,
        "slippage_bps": slippage_bps,
        "var_bps": var_bps,
    }
    payload = {
        "attribution": attribution,
        "denial_reasons": denial_reasons,
        "paper_only": True,
        "regime": regime,
        "risk_gate_decision_sha256": risk_gate_decision.decision_sha256,
        "current_gross_exposure_bps": current_gross_exposure_bps,
        "target_gross_exposure_bps": target_gross_exposure_bps,
    }
    return PaperPortfolioRegimeValidation(
        approved=not denial_reasons,
        paper_only=True,
        regime=regime,
        rebalance_delta_bps=target_gross_exposure_bps - current_gross_exposure_bps,
        denial_reasons=denial_reasons,
        attribution=attribution,
        validation_sha256=_canonical_sha256(payload),
    )


def reject_portfolio_regime_validation_effect(operation: str) -> None:
    """Fail closed for every operation outside paper-only validation."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("paper_only_portfolio_regime_validation_no_effects")
    raise ValueError("unsupported_paper_only_portfolio_regime_validation_operation")
