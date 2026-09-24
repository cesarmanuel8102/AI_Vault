from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

import ibkr_paper_30d.autonomous_runtime as runtime
from ibkr_paper_30d.autonomous_research import (
    AutonomousTurn,
    AutonomousTurnMode,
    ProposalValidation,
)
from ibkr_paper_30d.autonomous_runtime import run_autonomous_cycle
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import (
    InvocationRequest,
    TraderDecision,
    TraderInputBundle,
)


REPO = Path(__file__).resolve().parents[2]


class SequenceProvider:
    def __init__(self, turns):
        self.turns = list(turns)

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return self.turns.pop(0)


class AcceptingToolbox:
    def manifest(self):
        return []

    def execute(self, request, bundle):
        raise AssertionError("not expected")

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(passed=True, reason_codes=(), broker_evidence={})


class FillingExecutor:
    """Executor that records calls and returns a filled order."""

    def __init__(self):
        self.execute_calls = []

    def execute(self, proposal, bundle):
        self.execute_calls.append(proposal)
        return type(
            "Result",
            (),
            {
                "success": True,
                "status": "FILLED",
                "reason_codes": (),
                "order": {
                    "orderRef": "codex-ibkr-paper-30d-a-cycle-diag",
                    "fills": [
                        {
                            "contract": {
                                "conId": 265598,
                                "symbol": "AAPL",
                                "secType": "STK",
                                "multiplier": "1",
                            },
                            "side": "BUY",
                            "quantity": "2",
                            "price": "100.00",
                            "commission": "1.00",
                            "orderRef": "codex-ibkr-paper-30d-a-cycle-diag",
                            "permId": 9001,
                            "orderId": 41,
                            "clientId": 19761,
                            "execution_time": "2026-09-24T15:00:00Z",
                        }
                    ],
                },
                "broker_validation": {},
            },
        )()


def bundle(cycle="cycle-diag-1", equity="500.00"):
    return TraderInputBundle(
        decision_cycle_id=cycle,
        utc_timestamp="2026-09-24T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": equity, "allocation": "500.00"},
        broker_account_snapshot={"buying_power": equity},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )


def propose_trade_turn():
    from ibkr_paper_30d.autonomous_research import AutonomousTradeProposal

    return AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=AutonomousTradeProposal(
            thesis="Asymmetric opportunity",
            catalyst="Catalyst",
            symbol="AAPL",
            sec_type="STK",
            direction="LONG",
            action="BUY",
            quantity="2",
            order_type="MKT",
            capital_required="200.00",
            maximum_loss="200.00",
            loss_is_bounded=True,
            probability_profit="0.6",
            probability_loss="0.4",
            expected_gain="300.00",
            expected_loss="200.00",
            expected_value="100.00",
            expected_holding_period="1 day",
            entry_condition="fill",
            invalidation_condition="thesis breaks",
            exit_plan="exit plan",
            why_now="now",
            alternatives_considered=["cash"],
            evidence_used=["quote"],
            disconfirming_evidence=[],
            confidence="0.7",
        ),
        confidence="0.7",
        reasoning_summary="Trade",
        reason_codes=[],
    )


def diagnostics_rows(db):
    return db.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='risk_diagnostics'"
    ).fetchall()


def test_runtime_persists_risk_diagnostics_after_ledger_projection(tmp_path):
    value = bundle("cycle-diag-a")
    executor = FillingExecutor()
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            execute_paper=True,
            database=db,
            provider=SequenceProvider([propose_trade_turn()]),
            toolbox=AcceptingToolbox(),
            executor=executor,
        )

        assert result["execution"]["success"] is True
        rows = diagnostics_rows(db)
        assert rows, "risk_diagnostics event must be persisted after execution"
        payload = json.loads(rows[-1][0])
        diagnostics = payload["observation"]
        assert diagnostics["diagnostic_status"] == "OBSERVATION_ONLY"
        # Honest metrics from the real projection (open position, no closes).
        assert diagnostics["current_equity"] == "499.00"
        assert diagnostics["gross_exposure"] == "200.00"
        assert diagnostics["realized_pnl"] == "0.00"
        assert diagnostics["win_count"] == 0
        assert diagnostics["loss_count"] == 0
        assert diagnostics["turnover"] == "0.40"
        # Never computable here -> explicitly unavailable, never invented.
        assert diagnostics["equity_variability"] == "unavailable"
        assert diagnostics["time_under_water"] == "unavailable"
        assert diagnostics["payoff_asymmetry"] == "unavailable"


def test_diagnostic_builder_failure_is_analytical_not_authoritative(
    tmp_path, monkeypatch
):
    value = bundle("cycle-diag-fail")
    executor = FillingExecutor()
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        def broken_diagnostics(state, *, fills=None):
            raise RuntimeError("diagnostics exploded")

        monkeypatch.setattr(runtime, "build_risk_diagnostics", broken_diagnostics)

        result = run_autonomous_cycle(
            value,
            execute_paper=True,
            database=db,
            provider=SequenceProvider([propose_trade_turn()]),
            toolbox=AcceptingToolbox(),
            executor=executor,
        )

        # The already-authorized execution is unchanged by the failure.
        assert result["execution"]["success"] is True
        assert len(executor.execute_calls) == 1
        # No fabricated diagnostics event.
        assert diagnostics_rows(db) == []
        # Sanitized analytical failure note exists without raw messages.
        failure_rows = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='analytical_observer_failure'"
        ).fetchall()
        assert failure_rows
        note = json.loads(failure_rows[0][0])["observation"]
        assert note["stage"] == "risk_diagnostics"
        assert note["error_class"] == "RuntimeError"
        assert "diagnostics exploded" not in json.dumps(note)


def test_risk_diagnostics_absent_without_execution(tmp_path):
    value = bundle("cycle-diag-noexec")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            execute_paper=False,
            database=db,
            provider=SequenceProvider([propose_trade_turn()]),
            toolbox=AcceptingToolbox(),
        )

        assert result["execution"] is None
        assert diagnostics_rows(db) == []


def test_execution_and_validation_never_consume_risk_diagnostics():
    for path in (
        Path("ibkr_paper_30d/autonomous_execution.py"),
        Path("ibkr_paper_30d/ibkr_research_tools.py"),
        Path("ibkr_paper_30d/risk.py"),
        Path("ibkr_paper_30d/autonomous_research.py"),
    ):
        source = (REPO / path).read_text(encoding="utf-8")
        assert "risk_diagnostics" not in source, f"{path} must not consume diagnostics"
        assert "build_risk_diagnostics" not in source, f"{path} must not build diagnostics"