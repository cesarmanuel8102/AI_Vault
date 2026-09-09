"""R12.2 contract: deterministic paper-only risk gates with no runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _evaluate(**overrides):
    from tmp_agent.brain_v9.core.risk_engine_paper_gates import evaluate_paper_risk_gates

    values = {
        "daily_loss_bps": 0,
        "weekly_drawdown_bps": 0,
        "gross_exposure_bps": 0,
        "kill_switch_active": False,
        "market_data_stale": False,
        "broker_connected": True,
        "duplicate_order_detected": False,
        "reconciliation_ok": True,
    }
    values.update(overrides)
    return evaluate_paper_risk_gates(**values)


def test_safe_paper_input_produces_an_immutable_deterministic_approval():
    first = _evaluate()
    second = _evaluate()

    assert first == second
    assert first.approved is True
    assert first.paper_only is True
    assert first.denial_reasons == ()
    assert first.thresholds == {
        "daily_loss_bps": 200,
        "weekly_drawdown_bps": 600,
        "gross_exposure_bps": 7000,
    }
    assert len(first.decision_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.approved = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"daily_loss_bps": 200}, "daily_loss_limit_reached"),
        ({"weekly_drawdown_bps": 600}, "weekly_drawdown_limit_reached"),
        ({"gross_exposure_bps": 7001}, "gross_exposure_limit_exceeded"),
        ({"kill_switch_active": True}, "kill_switch_active"),
        ({"market_data_stale": True}, "market_data_stale"),
        ({"broker_connected": False}, "broker_disconnected"),
        ({"duplicate_order_detected": True}, "duplicate_order_detected"),
        ({"reconciliation_ok": False}, "reconciliation_failure"),
    ],
)
def test_each_loss_exposure_or_market_failure_gate_denies_paper_action(overrides, reason):
    result = _evaluate(**overrides)

    assert result.approved is False
    assert result.paper_only is True
    assert result.denial_reasons == (reason,)


def test_multiple_failures_are_deterministic_and_sorted():
    result = _evaluate(
        daily_loss_bps=250,
        broker_connected=False,
        duplicate_order_detected=True,
    )

    assert result.approved is False
    assert result.denial_reasons == (
        "broker_disconnected",
        "daily_loss_limit_reached",
        "duplicate_order_detected",
    )


@pytest.mark.parametrize(
    "operation",
    (
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
    ),
)
def test_risk_gates_reject_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.risk_engine_paper_gates import reject_paper_risk_gate_effect

    with pytest.raises(ValueError, match="paper_only_risk_engine_no_effects"):
        reject_paper_risk_gate_effect(operation)


def test_evidence_and_module_are_paper_only_and_external_effect_free():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R12_2_RISK_ENGINE_LOSS_EXPOSURE_MARKET_FAILURE_GATES.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R12.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["risk_gate_contract"]["paper_only"] is True
    assert evidence["risk_gate_contract"]["thresholds_bps"] == {
        "daily_loss": 200,
        "weekly_drawdown": 600,
        "gross_exposure": 7000,
    }
    assert all(value is False for value in evidence["runtime_actions"].values())

    source = (ROOT / "tmp_agent/brain_v9/core/risk_engine_paper_gates.py").read_text(
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


def test_closeout_records_merged_r12_2_evidence_and_only_authorizes_r12_3():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R12_2_RISK_ENGINE_LOSS_EXPOSURE_MARKET_FAILURE_GATES_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert closeout["roadmap_item"] == "R12.2"
    assert closeout["implementation_merge_commit"] == "8196245e533622455a6cb3c93b9db56b799ddc18"
    assert closeout["successor"] == {
        "roadmap_item": "R12.3",
        "front_id": "BRAIN-101-R12-3-PORTFOLIO-REGIME-REBALANCE-RISK-ATTRIBUTION-VALIDATION-01",
        "deployment_mode": "NO_DEPLOY",
    }
    assert all(value is False for value in closeout["runtime_actions"].values())

    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    active = [
        item_id
        for item_id, item in manifest["roadmap_items"].items()
        if item["status"] == "AUTHORIZED_ACTIVE"
    ]
    assert manifest["roadmap_items"]["R12.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert active == ["R12.3"]
    binding = manifest["roadmap_items"]["R12.3"]["automation"]
    assert binding["front_id"] == closeout["successor"]["front_id"]
    assert binding["work_branch"] == (
        "control-plane/r12-3-portfolio-regime-rebalance-risk-attribution-validation"
    )
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["allowed_paths"] == [
        "tmp_agent/brain_v9/core/portfolio_regime_paper_validation.py",
        "docs/roadmap/evidence/"
        "BRAIN_101_R12_3_PORTFOLIO_REGIME_REBALANCE_RISK_ATTRIBUTION_VALIDATION.json",
        "tests/contract/test_r12_3_portfolio_regime_rebalance_risk_attribution_validation.py",
    ]
