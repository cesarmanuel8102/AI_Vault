from decimal import Decimal

from ibkr_paper_30d.autonomous_research import AutonomousTradeProposal, ProposalLeg
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.trader_invocation import TraderInputBundle


def bundle(positions=None, equity="5000.00"):
    return TraderInputBundle(
        decision_cycle_id="cycle-structure-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": equity},
        broker_account_snapshot={"declared_options_level": 4},
        positions_snapshot=positions or [],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
        experiment_clock={"remaining_days": 20},
    )


def base(**updates):
    values = dict(
        thesis="test",
        catalyst="test",
        symbol="XYZ",
        sec_type="OPT",
        direction="SHORT_VOL",
        action="SELL",
        quantity="1",
        order_type="LMT",
        limit_price="1.00",
        expiry="20261016",
        strike="40",
        right="P",
        legs=[],
        capital_required="1000",
        maximum_loss="3900",
        loss_is_bounded=True,
        probability_profit="0.7",
        probability_loss="0.3",
        expected_gain="100",
        expected_loss="300",
        expected_value="-20",
        expected_reward_risk="0.33",
        expected_holding_period="1-5 days",
        entry_condition="test",
        invalidation_condition="test",
        exit_plan="test",
        why_now="test",
        alternatives_considered=["cash"],
        evidence_used=["option chain"],
        disconfirming_evidence=[],
        confidence="0.6",
    )
    values.update(updates)
    return AutonomousTradeProposal(**values)


def test_short_put_has_finite_deterministic_loss_floor():
    proposal = base(strike="40", limit_price="1.00", maximum_loss="3900")

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle())

    assert reason is None
    assert floor == Decimal("3900.00")


def test_naked_short_call_is_rejected():
    proposal = base(right="C", strike="40", maximum_loss="1000")

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle())

    assert floor is None
    assert reason == "UNCOVERED_SHORT_CALL"


def test_covered_call_is_bounded_by_isolated_long_shares():
    proposal = base(right="C", strike="40", maximum_loss="0", capital_required="0")
    covered = bundle([
        {
            "contract_id": 77,
            "symbol": "XYZ",
            "sec_type": "STK",
            "quantity": "100",
            "mark": "35",
            "market_value": "3500",
        }
    ])

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, covered)

    assert reason is None
    assert floor == Decimal("0")


def test_vertical_credit_spread_loss_is_calculated_from_payoff():
    proposal = base(
        action="SELL",
        limit_price="1.00",
        strike=None,
        right=None,
        capital_required="400",
        maximum_loss="400",
        legs=[
            ProposalLeg(
                symbol="XYZ", sec_type="OPT", action="SELL", ratio=1,
                expiry="20261016", strike="40", right="P",
            ),
            ProposalLeg(
                symbol="XYZ", sec_type="OPT", action="BUY", ratio=1,
                expiry="20261016", strike="35", right="P",
            ),
        ],
    )

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle())

    assert reason is None
    assert floor == Decimal("400.00")


def test_unbounded_call_ratio_spread_is_rejected():
    proposal = base(
        action="SELL",
        limit_price="1.00",
        strike=None,
        right=None,
        maximum_loss="500",
        legs=[
            ProposalLeg(
                symbol="XYZ", sec_type="OPT", action="BUY", ratio=1,
                expiry="20261016", strike="40", right="C",
            ),
            ProposalLeg(
                symbol="XYZ", sec_type="OPT", action="SELL", ratio=2,
                expiry="20261016", strike="45", right="C",
            ),
        ],
    )

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle())

    assert floor is None
    assert reason == "UNBOUNDED_UPSIDE_LIABILITY"


def test_long_option_loss_floor_comes_from_limit_debit_not_model_capital_estimate():
    proposal = base(
        action="BUY",
        direction="LONG",
        limit_price="1.00",
        capital_required="900.00",
        maximum_loss="100.00",
        right="C",
    )

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle(equity="500.00"))

    assert reason is None
    assert floor == Decimal("100.00")


def test_long_option_market_order_is_blocked_when_maximum_spend_cannot_be_proven():
    proposal = base(
        action="BUY",
        direction="LONG",
        order_type="MKT",
        limit_price=None,
        capital_required="100.00",
        maximum_loss="100.00",
        right="C",
    )

    floor, reason = IBKRResearchToolbox._structure_loss_floor(proposal, bundle(equity="500.00"))

    assert floor is None
    assert reason == "LONG_OPTION_COST_NOT_PRETRADE_BOUNDED"


def test_ibkr_whatif_margin_over_isolated_equity_blocks_even_if_model_estimate_is_low(monkeypatch):
    proposal = base(
        action="BUY",
        direction="LONG",
        limit_price="1.00",
        capital_required="100.00",
        maximum_loss="100.00",
        right="C",
    )
    toolbox = IBKRResearchToolbox(declared_options_level=4)
    monkeypatch.setattr(
        toolbox,
        "_broker_feasibility",
        lambda _proposal: {
            "success": True,
            "warningText": "",
            "initMarginChange": "600.00",
            "maintMarginChange": "600.00",
            "commission": "1.00",
            "maxCommission": "1.00",
        },
    )

    result = toolbox.validate_proposal(proposal, bundle(equity="500.00"))

    assert result.passed is False
    assert result.reason_codes == ("BROKER_MARGIN_EXCEEDS_EXPERIMENT_EQUITY",)
