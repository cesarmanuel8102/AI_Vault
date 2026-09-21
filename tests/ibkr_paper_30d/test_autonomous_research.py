from __future__ import annotations

from decimal import Decimal

from ibkr_paper_30d.autonomous_research import (
    AutonomousPositionAction,
    AutonomousResearchLoop,
    AutonomousTradeProposal,
    AutonomousTurn,
    AutonomousTurnMode,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderDecision, TraderInputBundle


class SequenceProvider:
    def __init__(self, turns):
        self.turns = list(turns)
        self.histories = []

    def next_turn(self, request, bundle, history, toolbox_manifest):
        self.histories.append(list(history))
        return self.turns.pop(0)


class FakeToolbox:
    def __init__(self, *, validation=True):
        self.requests = []
        self.validation = validation

    def manifest(self):
        return [{"tool": item.value} for item in ResearchTool]

    def execute(self, request, bundle):
        self.requests.append(request)
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data={"discovered_symbol": "NVDA", "source": "fake-broker"},
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(
            passed=self.validation,
            reason_codes=() if self.validation else ("BROKER_FEASIBILITY_FAILED",),
            broker_evidence={"what_if": "PASS" if self.validation else "BLOCK"},
        )

    def validate_position_action(self, action, bundle, decision):
        return ProposalValidation(
            passed=self.validation,
            reason_codes=() if self.validation else ("POSITION_ACTION_BLOCKED",),
            broker_evidence={"position_action": decision.value},
        )


def bundle(equity="500.00"):
    return TraderInputBundle(
        decision_cycle_id="cycle-autonomous-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": equity},
        broker_account_snapshot={"buying_power": equity},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[{"symbol": "SPY"}],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )


def request(value):
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="inv-autonomous-1",
        utc_timestamp="2026-09-20T20:00:01Z",
        requested_model="gpt-5.5",
        actual_model="gpt-5.5",
        model_configuration={"mode": "autonomous_research"},
        reasoning_effort="high",
        input_bundle_sha256=value.sha256,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id="paper-30d",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=60,
    )


def proposal(maximum_loss="500.00", symbol="NVDA"):
    return AutonomousTradeProposal(
        thesis="Autonomously discovered asymmetric opportunity",
        catalyst="Market-specific catalyst discovered during research",
        symbol=symbol,
        sec_type="OPT",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="LMT",
        limit_price="4.50",
        expiry="20261016",
        strike="200",
        right="C",
        legs=[],
        capital_required="450.00",
        maximum_loss=maximum_loss,
        loss_is_bounded=True,
        probability_profit="0.55",
        probability_loss="0.45",
        expected_gain="650.00",
        expected_loss="500.00",
        expected_value="132.50",
        expected_reward_risk="1.30",
        expected_holding_period="1-5 days",
        entry_condition="Liquidity and price remain acceptable",
        invalidation_condition="Catalyst or price thesis invalidates",
        exit_plan="Dynamic exit based on thesis and payoff",
        why_now="Current opportunity set is favorable",
        alternatives_considered=["cash", "shares", "vertical spread"],
        evidence_used=["scanner", "quote", "option chain"],
        disconfirming_evidence=["event risk"],
        confidence="0.72",
    )


def test_codex_can_research_then_trade_symbol_outside_frozen_candidates():
    value = bundle()
    research = AutonomousTurn(
        mode=AutonomousTurnMode.RESEARCH,
        research_requests=[ResearchRequest(
            request_id="r1",
            tool=ResearchTool.MARKET_SCANNER,
            arguments={"scan_code": "TOP_PERC_GAIN"},
            purpose="Discover opportunities without a predefined symbol universe",
        )],
        decision=None,
        proposal=None,
        confidence="0.5",
        reasoning_summary="Need market-wide discovery first",
        reason_codes=["NEED_DISCOVERY"],
    )
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=proposal(symbol="NVDA"),
        confidence="0.72",
        reasoning_summary="NVDA was discovered by research and passes the opportunity test",
        reason_codes=["AUTONOMOUS_DISCOVERY"],
    )
    provider = SequenceProvider([research, final])
    toolbox = FakeToolbox()

    outcome = AutonomousResearchLoop(provider, toolbox).run(request(value), value)

    assert outcome.accepted is True
    assert outcome.decision == TraderDecision.PROPOSE_TRADE
    assert outcome.proposal.symbol == "NVDA"
    assert value.candidate_screen_results == [{"symbol": "SPY"}]
    assert toolbox.requests[0].tool == ResearchTool.MARKET_SCANNER
    assert provider.histories[1][1]["payload"]["data"]["discovered_symbol"] == "NVDA"


def test_full_experimental_equity_may_be_risked():
    value = bundle("500.00")
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=proposal(maximum_loss="500.00"),
        confidence="0.7",
        reasoning_summary="Full-equity risk is justified by the model",
        reason_codes=["AGGRESSIVE_SIZING"],
    )

    outcome = AutonomousResearchLoop(SequenceProvider([final]), FakeToolbox()).run(request(value), value)

    assert outcome.accepted is True
    assert outcome.proposal.maximum_loss == Decimal("500.00")


def test_loss_above_experimental_equity_is_blocked():
    value = bundle("500.00")
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=proposal(maximum_loss="500.01"),
        confidence="0.7",
        reasoning_summary="Too much liability",
        reason_codes=[],
    )

    outcome = AutonomousResearchLoop(SequenceProvider([final]), FakeToolbox()).run(request(value), value)

    assert outcome.accepted is False
    assert outcome.reason_codes == ("EXPERIMENT_CAPITAL_BOUNDARY",)


def test_no_trade_remains_valid_after_autonomous_research():
    value = bundle()
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        confidence="0.8",
        reasoning_summary="No opportunity has positive enough terminal-equity expectation",
        reason_codes=["NO_EDGE_FOUND"],
    )

    outcome = AutonomousResearchLoop(SequenceProvider([final]), FakeToolbox()).run(request(value), value)

    assert outcome.accepted is True
    assert outcome.decision == TraderDecision.NO_TRADE


def test_unbounded_liability_is_blocked_by_loop_even_if_toolbox_would_accept():
    value = bundle("500.00")
    raw = proposal(maximum_loss="100.00").model_dump()
    raw["loss_is_bounded"] = False
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=AutonomousTradeProposal(**raw),
        confidence="0.7",
        reasoning_summary="Model considered an unbounded structure",
        reason_codes=[],
    )

    outcome = AutonomousResearchLoop(SequenceProvider([final]), FakeToolbox()).run(request(value), value)

    assert outcome.accepted is False
    assert outcome.reason_codes == ("UNBOUNDED_LIABILITY",)


def test_capital_required_cannot_use_rest_of_broker_account():
    value = bundle("500.00")
    raw = proposal(maximum_loss="400.00").model_dump()
    raw["capital_required"] = "500.01"
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=AutonomousTradeProposal(**raw),
        confidence="0.7",
        reasoning_summary="Broker may have more buying power but experiment does not",
        reason_codes=[],
    )

    outcome = AutonomousResearchLoop(SequenceProvider([final]), FakeToolbox()).run(request(value), value)

    assert outcome.accepted is False
    assert outcome.reason_codes == ("CAPITAL_REQUIRED_EXCEEDS_EQUITY",)


def test_stale_market_gate_blocks_before_autonomous_provider_call():
    value = bundle("500.00").model_copy(update={"market_data_snapshot": {"gate_status": "BLOCK"}})
    provider = SequenceProvider([])

    outcome = AutonomousResearchLoop(provider, FakeToolbox()).run(request(value), value)

    assert outcome.accepted is False
    assert outcome.reason_codes == ("MARKET_DATA_GATE_BLOCK",)
    assert provider.histories == []


def test_stale_input_hash_blocks_before_autonomous_provider_call():
    value = bundle("500.00")
    bad_request = request(value).model_copy(update={"input_bundle_sha256": "0" * 64})
    provider = SequenceProvider([])

    outcome = AutonomousResearchLoop(provider, FakeToolbox()).run(bad_request, value)

    assert outcome.accepted is False
    assert outcome.reason_codes == ("INPUT_HASH_MISMATCH",)
    assert provider.histories == []


def test_codex_can_reduce_existing_position_autonomously():
    value = bundle("650.00").model_copy(update={
        "positions_snapshot": [
            {"symbol": "NVDA", "security_type": "STK", "quantity": "2"}
        ]
    })
    action = AutonomousPositionAction(
        symbol="NVDA",
        sec_type="STK",
        action="SELL",
        quantity="1",
        order_type="MKT",
        limit_price=None,
        contract_id=None,
        expiry=None,
        strike=None,
        right=None,
        reason="Reduce exposure because the original catalyst weakened",
    )
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.REDUCE_POSITION,
        proposal=None,
        position_action=action,
        confidence="0.82",
        reasoning_summary="The position remains viable but no longer warrants full size.",
        reason_codes=["THESIS_WEAKENED"],
    )

    outcome = AutonomousResearchLoop(
        SequenceProvider([final]), FakeToolbox()
    ).run(request(value), value)

    assert outcome.accepted is True
    assert outcome.decision == TraderDecision.REDUCE_POSITION
    assert outcome.position_action is not None
    assert outcome.position_action.quantity == Decimal("1")


def test_blocked_position_management_falls_back_to_monitor():
    value = bundle("650.00").model_copy(update={
        "positions_snapshot": [
            {"symbol": "NVDA", "security_type": "STK", "quantity": "2"}
        ]
    })
    action = AutonomousPositionAction(
        symbol="NVDA",
        sec_type="STK",
        action="SELL",
        quantity="2",
        order_type="MKT",
        limit_price=None,
        contract_id=None,
        expiry=None,
        strike=None,
        right=None,
        reason="Attempt close",
    )
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.CLOSE_POSITION,
        proposal=None,
        position_action=action,
        confidence="0.9",
        reasoning_summary="Close the position.",
        reason_codes=["EXIT_NOW"],
    )

    outcome = AutonomousResearchLoop(
        SequenceProvider([final]), FakeToolbox(validation=False)
    ).run(request(value), value)

    assert outcome.accepted is False
    assert outcome.decision == TraderDecision.MONITOR_POSITION
    assert outcome.reason_codes == ("POSITION_ACTION_BLOCKED",)
