from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousTradeProposal,
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
from ibkr_paper_30d.continuity_models import ContinuityReview
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
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


class TimeoutProvider:
    def next_turn(self, request, bundle, history, toolbox_manifest):
        raise TimeoutError("provider deadline")


class ErrorProvider:
    def next_turn(self, request, bundle, history, toolbox_manifest):
        raise RuntimeError("provider process exited")


class RecordingLifecycle:
    def __init__(self, db):
        self.db = db
        self.events = []

    def begin(self, request, broker_time):
        self.events.append(("IN_FLIGHT", request.invocation_id))
        return request.invocation_id

    def fail(self, token, failure_code, broker_time):
        self.events.append((failure_code, token))

    def complete(self, token, state, broker_time, result_sha256=None):
        durable = self.db.execute(
            "SELECT accepted,payload_sha256 FROM trader_results WHERE invocation_id=?",
            (token,),
        ).fetchone()
        assert durable is not None
        assert durable[1] == result_sha256
        self.events.append((state, token))


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


def _install_continuity(db):
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)


class ReportAwareProvider(NoTradeProvider):
    def __init__(self):
        self.received = None

    def next_turn(self, request, bundle, history, toolbox_manifest):
        self.received = bundle.continuity_context
        return super().next_turn(request, bundle, history, toolbox_manifest)


class ReviewProvider(NoTradeProvider):
    def __init__(self, report_id, report_sha256):
        self.report_id = report_id
        self.report_sha256 = report_sha256

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            confidence="0.8",
            reasoning_summary="Reviewed the factual outage report.",
            reason_codes=["CONTINUITY_REVIEWED"],
            continuity_reviews=[
                ContinuityReview(
                    review_id="review-runtime-1",
                    report_id=self.report_id,
                    report_sha256=self.report_sha256,
                    invocation_id="HOST_BINDS_INVOCATION",
                    accepted_result_sha256="0" * 64,
                    disposition="ACK_NO_METHOD_CHANGE",
                )
            ],
        )


class ProposalProvider(NoTradeProvider):
    def next_turn(self, request, bundle, history, toolbox_manifest):
        proposal = AutonomousTradeProposal(
            thesis="Bounded PAPER setup.",
            symbol="SPY",
            sec_type="STK",
            direction="LONG",
            action="BUY",
            quantity="1",
            order_type="LMT",
            limit_price="1.00",
            capital_required="1.00",
            maximum_loss="1.00",
            loss_is_bounded=True,
            probability_profit="0.6",
            probability_loss="0.4",
            expected_gain="0.20",
            expected_loss="0.10",
            expected_value="0.08",
            expected_reward_risk="2",
            expected_holding_period="intraday",
            entry_condition="Current quote remains valid.",
            invalidation_condition="Quoted state changes.",
            exit_plan="Model-directed later cycle.",
            alternatives_considered=["NO_TRADE"],
            evidence_used=["PAPER quote"],
            disconfirming_evidence=["Pending continuity report"],
            confidence="0.6",
        )
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.PROPOSE_TRADE,
            proposal=proposal,
            confidence="0.6",
            reasoning_summary="A proposal that must remain gated.",
            reason_codes=["MODEL_SELECTED"],
        )


class TradeExecutorTripwire:
    armed = True

    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("new exposure reached broker executor")


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


def test_runtime_records_lifecycle_around_provider_and_durable_result(tmp_path):
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        lifecycle = RecordingLifecycle(db)
        result = run_autonomous_cycle(
            bundle(), database=db, provider=NoTradeProvider(), toolbox=PassiveToolbox(),
            provider_lifecycle=lifecycle, broker_time_reader=lambda: "paper-time",
        )

    invocation_id = result["request"]["invocation_id"]
    assert lifecycle.events == [
        ("IN_FLIGHT", invocation_id),
        ("COMPLETED_ACCEPTED", invocation_id),
    ]


def test_runtime_delivers_pending_report_before_provider_can_expand_authority(tmp_path):
    provider = ReportAwareProvider()
    with Database.open(tmp_path / "continuity-context.sqlite3") as db:
        _install_continuity(db)
        store = ContinuityStore(db)
        report = {
            "report_id": "report-runtime-1",
            "outage_id": "outage-runtime-1",
            "failure_codes": ["PROVIDER_TIMEOUT"],
        }
        report_hash = store.append_report(
            "report-runtime-1", "outage-runtime-1", report
        )
        run_autonomous_cycle(
            bundle(),
            database=db,
            provider=provider,
            toolbox=PassiveToolbox(),
            continuity_store=store,
        )

    assert provider.received["pending_reports"] == [
        {**report, "report_sha256": report_hash, "trust": "FACTUAL_HASH_BOUND"}
    ]


def test_runtime_host_binds_and_persists_review_before_releasing_gate(tmp_path):
    with Database.open(tmp_path / "continuity-review.sqlite3") as db:
        _install_continuity(db)
        store = ContinuityStore(db)
        report = {"report_id": "report-runtime-1", "outage_id": "outage-runtime-1"}
        report_hash = store.append_report(
            "report-runtime-1", "outage-runtime-1", report
        )
        result = run_autonomous_cycle(
            bundle(),
            database=db,
            provider=ReviewProvider("report-runtime-1", report_hash),
            toolbox=PassiveToolbox(),
            continuity_store=store,
        )
        row = db.execute(
            "SELECT invocation_id,payload_json FROM continuity_review_events"
        ).fetchone()

    assert row is not None
    review = ContinuityReview.model_validate_json(str(row[1]))
    assert row[0] == result["request"]["invocation_id"]
    assert review.invocation_id == result["request"]["invocation_id"]
    assert review.accepted_result_sha256 != "0" * 64
    assert result["continuity_authority"]["authorized"] is True


def test_runtime_blocks_new_exposure_while_report_is_pending(tmp_path):
    executor = TradeExecutorTripwire()
    with Database.open(tmp_path / "continuity-block.sqlite3") as db:
        _install_continuity(db)
        store = ContinuityStore(db)
        store.append_report(
            "report-runtime-1",
            "outage-runtime-1",
            {"report_id": "report-runtime-1", "outage_id": "outage-runtime-1"},
        )
        result = run_autonomous_cycle(
            bundle(),
            execute_paper=True,
            database=db,
            provider=ProposalProvider(),
            toolbox=PassiveToolbox(),
            executor=executor,
            continuity_store=store,
        )

    assert executor.calls == []
    assert result["execution"]["status"] == "BLOCKED"
    assert result["execution"]["reason_codes"] == ["CONTINUITY_REVIEW_REQUIRED"]


@pytest.mark.parametrize(
    ("provider", "expected", "error_type"),
    [
        (TimeoutProvider(), "PROVIDER_TIMEOUT", TimeoutError),
        (ErrorProvider(), "PROVIDER_PROCESS_ERROR", RuntimeError),
    ],
)
def test_runtime_records_provider_failures(tmp_path, provider, expected, error_type):
    with Database.open(tmp_path / f"{expected}.sqlite3") as db:
        lifecycle = RecordingLifecycle(db)
        with pytest.raises(error_type):
            run_autonomous_cycle(
                bundle(), database=db, provider=provider, toolbox=PassiveToolbox(),
                provider_lifecycle=lifecycle, broker_time_reader=lambda: "paper-time",
            )
    assert lifecycle.events[0][0] == "IN_FLIGHT"
    assert lifecycle.events[1][0] == expected


def test_runtime_records_unaccepted_only_after_rejected_result_is_durable(tmp_path):
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        lifecycle = RecordingLifecycle(db)
        result = run_autonomous_cycle(
            bundle().model_copy(update={"kill_switch_state": "KILL_SWITCH_TRIGGERED"}),
            database=db, provider=NoTradeProvider(), toolbox=PassiveToolbox(),
            provider_lifecycle=lifecycle, broker_time_reader=lambda: "paper-time",
        )
    assert result["outcome"]["accepted"] is False
    assert lifecycle.events[-1][0] == "COMPLETED_UNACCEPTED"


def test_runtime_persists_validated_plan_only_after_accepted_result(
    tmp_path, monkeypatch, continuity_plan_factory
):
    from ibkr_paper_30d.autonomous_research import AutonomousResearchOutcome

    plan = continuity_plan_factory(
        plan_id="plan-runtime-1",
        clock_event_sha256="a" * 64,
        owner_authorization_sha256="b" * 64,
        model_attestation_sha256="c" * 64,
    )
    outcome = AutonomousResearchOutcome(
        accepted=True,
        validation="PASS",
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        position_action=None,
        open_order_action=None,
        reason_codes=("PLAN_ONLY",),
        rounds=1,
        transcript=[],
        transcript_sha256="d" * 64,
        continuity_plan=plan,
    )

    class RecordingStore:
        def __init__(self, db):
            self.db = db
            self.calls = []

        def append_plan_event(self, event_type, value, **kwargs):
            row = self.db.execute(
                "SELECT accepted,payload_sha256 FROM trader_results"
            ).fetchone()
            assert row is not None and row[0] == 1
            assert kwargs["bindings"]["result_sha256"] == row[1]
            self.calls.append((event_type, value, kwargs))

        def pending_reports(self):
            return []

    monkeypatch.setattr(
        "ibkr_paper_30d.autonomous_runtime.AutonomousResearchLoop.run",
        lambda self, request, value: outcome,
    )
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        store = RecordingStore(db)
        run_autonomous_cycle(
            bundle(), database=db, provider=NoTradeProvider(), toolbox=PassiveToolbox(),
            continuity_store=store,
        )
    assert store.calls[0][0] == "VALIDATED"
    assert store.calls[0][2]["bindings"]["input_bundle_sha256"]


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
