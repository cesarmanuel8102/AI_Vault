"""R12.1 contract: deterministic paper-only portfolio allocation and ledger baseline."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipts(*items):
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        PaperEligibleStrategyValidationReceipt,
    )

    return tuple(PaperEligibleStrategyValidationReceipt(**item) for item in items)


def _receipt(
    receipt_id: str,
    strategy_id: str,
    asset_bucket: str,
    correlation_group: str,
    expected_attribution_bps: int,
):
    return {
        "receipt_id": receipt_id,
        "strategy_id": strategy_id,
        "eligibility": "PAPER_ELIGIBLE",
        "asset_bucket": asset_bucket,
        "correlation_group": correlation_group,
        "expected_attribution_bps": expected_attribution_bps,
    }


def _build(receipts, **overrides):
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        build_paper_only_portfolio_baseline,
    )

    kwargs = {
        "portfolio_id": "r12_1_portfolio_001",
        "total_capital_cents": 100_000_00,
        "receipts": receipts,
        "cash_reserve_bps": 1_000,
        "max_strategy_weight_bps": 4_500,
        "max_asset_weight_bps": 5_000,
        "max_correlation_group_weight_bps": 5_000,
    }
    kwargs.update(overrides)
    return build_paper_only_portfolio_baseline(**kwargs)


def test_paper_eligible_receipts_produce_immutable_deterministic_allocation_and_ledger():
    receipts = _receipts(
        _receipt("receipt_a_001", "strategy_a", "equities", "growth", 120),
        _receipt("receipt_b_001", "strategy_b", "rates", "defensive", 80),
    )

    first = _build(receipts)
    second = _build(receipts)

    assert first == second
    assert first.portfolio.portfolio_id == "r12_1_portfolio_001"
    assert first.portfolio.paper_only is True
    assert first.portfolio.cash_reserve_bps == 1_000
    assert [entry.target_weight_bps for entry in first.ledger.entries] == [4_500, 4_500]
    assert first.ledger.total_allocated_bps == 9_000
    assert first.ledger.cash_reserve_bps == 1_000
    assert first.risk_summary.max_strategy_weight_bps_observed == 4_500
    assert first.risk_summary.asset_exposure_bps == {"equities": 4_500, "rates": 4_500}
    assert first.risk_summary.correlation_group_exposure_bps == {"defensive": 4_500, "growth": 4_500}
    assert first.attribution.expected_attribution_bps == 90
    assert len(first.portfolio.portfolio_sha256) == 64
    assert len(first.ledger.ledger_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.ledger.entries[0].target_weight_bps = 0


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("insufficient_strategy_capacity", "insufficient_strategy_capacity"),
        ("asset_exposure_limit_exceeded", "asset_exposure_limit_exceeded"),
        ("correlation_group_limit_exceeded", "correlation_group_limit_exceeded"),
        ("duplicate_receipt_id", "duplicate_receipt_id"),
    ],
)
def test_portfolio_baseline_fails_closed_when_receipts_or_risk_limits_are_invalid(
    case, error
):
    if case == "insufficient_strategy_capacity":
        receipts = _receipts(_receipt("receipt_a_001", "strategy_a", "equities", "growth", 120))
    elif case == "asset_exposure_limit_exceeded":
        receipts = _receipts(
            _receipt("receipt_a_001", "strategy_a", "equities", "growth", 120),
            _receipt("receipt_b_001", "strategy_b", "equities", "defensive", 80),
        )
    elif case == "correlation_group_limit_exceeded":
        receipts = _receipts(
            _receipt("receipt_a_001", "strategy_a", "equities", "growth", 120),
            _receipt("receipt_b_001", "strategy_b", "rates", "growth", 80),
        )
    else:
        receipts = _receipts(
            _receipt("receipt_a_001", "strategy_a", "equities", "growth", 120),
            _receipt("receipt_a_001", "strategy_b", "rates", "defensive", 80),
        )

    with pytest.raises(ValueError, match=error):
        _build(receipts)


def test_non_paper_eligible_receipt_is_rejected_before_allocation():
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        PaperEligibleStrategyValidationReceipt,
    )

    receipt = PaperEligibleStrategyValidationReceipt(
        receipt_id="receipt_a_001",
        strategy_id="strategy_a",
        eligibility="REJECTED",
        asset_bucket="equities",
        correlation_group="growth",
        expected_attribution_bps=120,
    )

    with pytest.raises(ValueError, match="receipt_not_paper_eligible"):
        _build((receipt, receipt))


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
def test_portfolio_baseline_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        reject_portfolio_baseline_effect,
    )

    with pytest.raises(ValueError, match="paper_only_portfolio_baseline_no_effects"):
        reject_portfolio_baseline_effect(operation)


def test_evidence_and_module_are_paper_only_and_external_effect_free():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R12_1_PORTFOLIO_MANAGER_ALLOCATION_LEDGER_BASELINE.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R12.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["portfolio_contract"]["paper_only"] is True
    assert evidence["portfolio_contract"]["consumes"] == "StrategyValidationReceipt/PAPER_ELIGIBLE"
    assert evidence["portfolio_contract"]["raw_strategies_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())

    source = (
        ROOT / "tmp_agent/brain_v9/core/portfolio_manager_paper_baseline.py"
    ).read_text(encoding="utf-8")
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


def test_closeout_records_merged_r12_1_evidence_and_only_authorizes_r12_2():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R12_1_PORTFOLIO_MANAGER_ALLOCATION_LEDGER_BASELINE_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert closeout["roadmap_item"] == "R12.1"
    assert closeout["implementation_merge_commit"] == "abcb61c67988b4d3db5c6f42d736a7ca2aa55b52"
    assert closeout["successor"] == {
        "roadmap_item": "R12.2",
        "front_id": "BRAIN-101-R12-2-RISK-ENGINE-LOSS-EXPOSURE-MARKET-FAILURE-GATES-01",
        "deployment_mode": "NO_DEPLOY",
    }
    assert all(value is False for value in closeout["runtime_actions"].values())

    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["roadmap_items"]["R12.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert manifest["roadmap_items"]["R12.2"]["status"] in {
        "AUTHORIZED_ACTIVE",
        "CLOSED_RUNTIME_VERIFIED",
    }
    binding = manifest["roadmap_items"]["R12.2"]["automation"]
    assert binding["front_id"] == closeout["successor"]["front_id"]
    assert binding["deployment_mode"] == "NO_DEPLOY"
