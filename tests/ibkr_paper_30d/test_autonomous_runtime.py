from __future__ import annotations

import sqlite3

import pytest

from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousTurn,
    AutonomousTurnMode,
    ProposalValidation,
    ResearchResult,
)
from ibkr_paper_30d.autonomous_runtime import (
    AutonomousTraderBoundary,
    run_autonomous_cycle,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle


class NoTradeProvider:
    last_native_tool_events = []

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            confidence="0.8",
            reasoning_summary="No sufficiently attractive opportunity.",
            reason_codes=["NO_EDGE_FOUND"],
        )


class PassiveToolbox:
    def manifest(self):
        return []

    def execute(self, request, bundle):
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=False,
            data={},
            error="not_expected",
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(passed=True, reason_codes=(), broker_evidence={})


class OpenOrderToolbox(PassiveToolbox):
    def validate_open_order_action(self, action, bundle, decision):
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={"decision": decision.value},
        )


class CancelProvider:
    last_native_tool_events = []

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.CANCEL_ORDER,
            proposal=None,
            position_action=None,
            open_order_action=AutonomousOpenOrderAction(
                order_ref=self.snapshot["orderRef"],
                order_id=self.snapshot["orderId"],
                perm_id=self.snapshot["permId"],
                client_id=self.snapshot["clientId"],
                contract_id=self.snapshot["contract"]["conId"],
                observed_state_sha256=self.snapshot["state_sha256"],
                reason="Cancel the selected resting experiment order.",
            ),
            confidence="0.9",
            reasoning_summary="The resting order no longer has sufficient edge.",
            reason_codes=["EDGE_DECAYED"],
        )


class RecordingExecutor:
    def __init__(self):
        self.open_order_calls = []

    def execute_open_order_action(
        self, action, bundle, decision, *, invocation_id=None
    ):
        self.open_order_calls.append((action, decision, invocation_id))
        return PaperExecutionResult(
            success=True,
            status="Cancelled",
            reason_codes=(),
            order={"order_management": decision.value, "fills": []},
            broker_validation={},
        )


def bundle():
    return TraderInputBundle(
        decision_cycle_id="cycle-runtime-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"buying_power": "500.00"},
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


def bundle_with_owned_open_order():
    snapshot = {
        "orderRef": "codex-ibkr-paper-30d-a-cycle",
        "orderId": 41,
        "permId": 9001,
        "clientId": 19761,
        "contract": {"conId": 756733},
        "state_sha256": "a" * 64,
    }
    return bundle().model_copy(update={"open_orders_snapshot": [snapshot]})


def test_runtime_persists_canonical_bundle_invocation_result_and_research(tmp_path):
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            bundle(),
            database=db,
            provider=NoTradeProvider(),
            toolbox=PassiveToolbox(),
        )

        assert result["outcome"]["decision"] == "NO_TRADE"
        assert db.execute("SELECT COUNT(*) FROM trader_input_bundles").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM trader_invocations").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM trader_results").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM autonomous_research_events").fetchone()[0] >= 3
        assert db.execute(
            "SELECT COUNT(*) FROM autonomous_research_events WHERE event_type='interference_observation'"
        ).fetchone()[0] == 1
        assert result["interference"]["interference_source"] == "MODEL_DECISION"
        assert result["interference"]["provider_policy_attribution"] == "UNDETERMINED"
        final_payload = db.execute(
            "SELECT payload_json FROM autonomous_research_events WHERE event_type='final_outcome'"
        ).fetchone()[0]
        assert '"proposal.expected_value":"MODEL_INFERENCE"' in final_payload
        assert '"broker_validation":"BROKER_OR_DETERMINISTIC_EVIDENCE"' in final_payload


def test_autonomous_trader_boundary_accepts_frozen_bundle_mapping():
    boundary = AutonomousTraderBoundary(
        provider=NoTradeProvider(),
        toolbox=PassiveToolbox(),
    )

    result = boundary.invoke("SCHEDULED_SCAN", bundle().model_dump(mode="json"))

    assert result["schema"] == "CODEX_IBKR_AUTONOMOUS_CYCLE_V1"
    assert result["outcome"]["decision"] == "NO_TRADE"


def test_runtime_dispatches_accepted_cancel_to_open_order_executor(tmp_path):
    value = bundle_with_owned_open_order()
    executor = RecordingExecutor()
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            execute_paper=True,
            database=db,
            provider=CancelProvider(value.open_orders_snapshot[0]),
            toolbox=OpenOrderToolbox(),
            executor=executor,
        )
        final_payload = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='final_outcome'"
        ).fetchone()[0]

    assert executor.open_order_calls[0][1] == TraderDecision.CANCEL_ORDER
    assert executor.open_order_calls[0][2].startswith("autonomous-")
    assert result["execution"]["order"]["order_management"] == "CANCEL_ORDER"
    assert '"open_order_action"' in final_payload


def test_accepted_cycle_cannot_dispatch_open_order_action_twice(tmp_path):
    value = bundle_with_owned_open_order()
    executor = RecordingExecutor()
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            value,
            execute_paper=True,
            database=db,
            provider=CancelProvider(value.open_orders_snapshot[0]),
            toolbox=OpenOrderToolbox(),
            executor=executor,
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
            run_autonomous_cycle(
                value,
                execute_paper=True,
                database=db,
                provider=CancelProvider(value.open_orders_snapshot[0]),
                toolbox=OpenOrderToolbox(),
                executor=executor,
            )

    assert len(executor.open_order_calls) == 1
