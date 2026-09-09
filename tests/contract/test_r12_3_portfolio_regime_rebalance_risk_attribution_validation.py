"""R12.3 contract: deterministic paper-only portfolio regime validation."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _approved_risk_decision():
    from tmp_agent.brain_v9.core.risk_engine_paper_gates import evaluate_paper_risk_gates

    return evaluate_paper_risk_gates(
        daily_loss_bps=0,
        weekly_drawdown_bps=0,
        gross_exposure_bps=0,
        kill_switch_active=False,
        market_data_stale=False,
        broker_connected=True,
        duplicate_order_detected=False,
        reconciliation_ok=True,
    )


def _validate(**overrides):
    from tmp_agent.brain_v9.core.portfolio_regime_paper_validation import (
        validate_paper_only_portfolio_regime,
    )

    values = {
        "regime": "neutral",
        "current_gross_exposure_bps": 4_000,
        "target_gross_exposure_bps": 4_500,
        "risk_gate_decision": _approved_risk_decision(),
        "var_bps": 120,
        "cvar_bps": 180,
        "liquidity_bps": 80,
        "slippage_bps": 12,
        "fees_bps": 3,
        "gap_bps": 25,
    }
    values.update(overrides)
    return validate_paper_only_portfolio_regime(**values)


def test_paper_regime_validation_is_immutable_deterministic_and_records_attribution():
    first = _validate()
    second = _validate()

    assert first == second
    assert first.approved is True
    assert first.paper_only is True
    assert first.regime == "neutral"
    assert first.rebalance_delta_bps == 500
    assert first.attribution == {
        "cvar_bps": 180,
        "fees_bps": 3,
        "gap_bps": 25,
        "liquidity_bps": 80,
        "slippage_bps": 12,
        "var_bps": 120,
    }
    assert len(first.validation_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.approved = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"risk_gate_decision": _approved_risk_decision().__class__(False, True, ("market_data_stale",), {"daily_loss_bps": 200, "weekly_drawdown_bps": 600, "gross_exposure_bps": 7000}, "0" * 64)}, "risk_gate_denied"),
        ({"target_gross_exposure_bps": 7001}, "gross_exposure_limit_exceeded"),
        ({"regime": "risk_off", "target_gross_exposure_bps": 4500}, "risk_off_exposure_increase_denied"),
        ({"cvar_bps": 119}, "cvar_below_var"),
    ],
)
def test_regime_validation_fails_closed_for_risk_or_attribution_inconsistency(overrides, reason):
    result = _validate(**overrides)

    assert result.approved is False
    assert result.denial_reasons == (reason,)


@pytest.mark.parametrize(
    "operation",
    ("broker_connect", "broker_order", "order_submit", "provider_call", "network_fetch", "scheduler_mutation", "canonical_local_sync", "live_trading", "real_money", "auto_merge"),
)
def test_regime_validation_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.portfolio_regime_paper_validation import (
        reject_portfolio_regime_validation_effect,
    )

    with pytest.raises(ValueError, match="paper_only_portfolio_regime_validation_no_effects"):
        reject_portfolio_regime_validation_effect(operation)


def test_evidence_and_module_are_paper_only_and_external_effect_free():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R12_3_PORTFOLIO_REGIME_REBALANCE_RISK_ATTRIBUTION_VALIDATION.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R12.3"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["portfolio_validation_contract"]["paper_only"] is True
    assert evidence["portfolio_validation_contract"]["risk_gate_receipt_required"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())

    source = (ROOT / "tmp_agent/brain_v9/core/portfolio_regime_paper_validation.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "import financial_autonomy",
        "from financial_autonomy",
        "subprocess",
        "requests",
        "httpx",
        "socket",
        "import trading",
        "from trading",
    ):
        assert forbidden not in source
