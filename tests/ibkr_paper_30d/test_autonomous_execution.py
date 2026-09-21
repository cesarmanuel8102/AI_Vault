from __future__ import annotations

import pytest
from types import SimpleNamespace

from ibkr_paper_30d.autonomous_execution import (
    AutonomousPaperExecutionNotArmed,
    AutonomousPaperExecutor,
)
from ibkr_paper_30d.autonomous_research import AutonomousTradeProposal, ProposalValidation
from ibkr_paper_30d.trader_invocation import TraderInputBundle


class NoCallToolbox:
    def validate_proposal(self, proposal, bundle):
        raise AssertionError("toolbox should not be called when deterministic safety gate blocks")


def bundle(*, reconciliation="PASS", kill_switch="KILL_SWITCH_CLEAR", market_gate="PASS"):
    return TraderInputBundle(
        decision_cycle_id="cycle-exec-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": reconciliation},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"buying_power": "500.00"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state=kill_switch,
        market_data_snapshot={"gate_status": market_gate},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )


def proposal():
    return AutonomousTradeProposal(
        thesis="test",
        catalyst="test",
        symbol="SPY",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="MKT",
        limit_price=None,
        expiry=None,
        strike=None,
        right=None,
        legs=[],
        capital_required="100",
        maximum_loss="100",
        loss_is_bounded=True,
        probability_profit="0.6",
        probability_loss="0.4",
        expected_gain="20",
        expected_loss="10",
        expected_value="8",
        expected_reward_risk="2",
        expected_holding_period="intraday",
        entry_condition="now",
        invalidation_condition="invalid",
        exit_plan="exit",
        why_now="test",
        alternatives_considered=["cash"],
        evidence_used=["quote"],
        disconfirming_evidence=[],
        confidence="0.6",
    )


def test_executor_is_not_armed_by_default(monkeypatch):
    monkeypatch.delenv("IBKR_AUTONOMOUS_PAPER_ARMED", raising=False)
    executor = AutonomousPaperExecutor(NoCallToolbox())

    with pytest.raises(AutonomousPaperExecutionNotArmed):
        executor.execute(proposal(), bundle())


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"reconciliation": "BLOCK"}, "BROKER_RECONCILIATION_REQUIRED"),
        ({"kill_switch": "KILL_SWITCH_TRIGGERED"}, "KILL_SWITCH_TRIGGERED"),
        ({"market_gate": "BLOCK"}, "MARKET_DATA_GATE_BLOCK"),
    ],
)
def test_executor_retains_non_strategic_safety_gates(kwargs, reason):
    executor = AutonomousPaperExecutor(NoCallToolbox(), armed=True)

    result = executor.execute(proposal(), bundle(**kwargs))

    assert result.success is False
    assert result.status == "BLOCKED"
    assert reason in result.reason_codes


class _FakeIB:
    def __init__(self):
        self.place_calls = 0

    def placeOrder(self, contract, order):
        self.place_calls += 1
        raise AssertionError("placeOrder must not be reached")

    def disconnect(self):
        pass


class _PassUntilOperatorControlToolbox:
    def __init__(self):
        self.ib = _FakeIB()

    def _connect(self):
        return self.ib

    def _proposal_contract(self, ib, proposal):
        return SimpleNamespace(conId=123, symbol=proposal.symbol)

    def live_contract_quote_evidence(self, ib, contract):
        return {"success": True, "market_data_type": 1}

    def validate_proposal(self, proposal, bundle, *, ib=None):
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={"what_if": {"success": True}},
        )


def test_immediate_operator_control_blocks_place_order(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: ("OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE",),
        )
        result = executor.execute(proposal(), bundle())

    assert result.success is False
    assert result.status == "BLOCKED"
    assert "OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE" in result.reason_codes
    assert toolbox.ib.place_calls == 0


def test_missing_immediate_operator_control_callback_fails_closed(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
        )
        result = executor.execute(proposal(), bundle())

    assert result.success is False
    assert "FRESH_OPERATOR_CONTROL_CHECK_REQUIRED" in result.reason_codes
    assert toolbox.ib.place_calls == 0
