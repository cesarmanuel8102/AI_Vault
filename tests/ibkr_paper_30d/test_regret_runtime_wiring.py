from __future__ import annotations

import json
from decimal import Decimal

import pytest

import ibkr_paper_30d.autonomous_runtime as runtime
from ibkr_paper_30d.autonomous_research import (
    AutonomousResearchLoop,
    AutonomousTurn,
    AutonomousTurnMode,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.autonomous_runtime import run_autonomous_cycle
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import (
    InvocationRequest,
    TraderDecision,
    TraderInputBundle,
)


class SequenceProvider:
    def __init__(self, turns):
        self.turns = list(turns)

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return self.turns.pop(0)


class RejectingToolbox:
    """Toolbox whose validate_proposal always blocks, like a broker
    feasibility rejection."""

    def __init__(self, *, validation_reason="BROKER_FEASIBILITY_FAILED"):
        self.requests = []
        self.validation_reason = validation_reason

    def manifest(self):
        return [{"tool": item.value} for item in ResearchTool]

    def execute(self, request, bundle):
        self.requests.append(request)
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data={"contract": {"symbol": str(request.arguments.get("symbol", ""))},
                  "last": "6.10"},
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(
            passed=False,
            reason_codes=(self.validation_reason,),
            broker_evidence={"what_if": "BLOCK", "initMarginChange": "950.00"},
        )


class QuoteToolbox:
    """Toolbox returning a legitimate observed quote for a symbol."""

    def __init__(self, *, quote_price="6.10"):
        self.quote_price = quote_price

    def manifest(self):
        return [{"tool": item.value} for item in ResearchTool]

    def execute(self, request, bundle):
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data={
                "contract": {"symbol": str(request.arguments.get("symbol", "")).upper()},
                "bid": "6.05",
                "ask": "6.15",
                "last": self.quote_price,
            },
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(passed=True, reason_codes=(), broker_evidence={})


def bundle(cycle="cycle-wiring-1", equity="500.00"):
    return TraderInputBundle(
        decision_cycle_id=cycle,
        utc_timestamp="2026-09-24T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": equity},
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


def request(value):
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id=f"inv-{value.decision_cycle_id}",
        utc_timestamp="2026-09-24T20:00:01Z",
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


def propose_trade_turn(symbol="NVDA"):
    return AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=proposal(symbol),
        confidence="0.7",
        reasoning_summary="Opportunity identified",
        reason_codes=[],
    )


def proposal(symbol="NVDA", maximum_loss="400.00"):
    from ibkr_paper_30d.autonomous_research import AutonomousTradeProposal

    return AutonomousTradeProposal(
        thesis="Autonomously identified asymmetric opportunity",
        catalyst="Model-selected catalyst",
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
        expected_loss="400.00",
        expected_value="132.50",
        expected_reward_risk="1.30",
        expected_holding_period="1-5 days",
        entry_condition="Liquidity and price remain acceptable",
        invalidation_condition="Catalyst or price thesis invalidates",
        exit_plan="Dynamic exit based on thesis and payoff",
        why_now="Current opportunity set is favorable",
        alternatives_considered=["cash"],
        evidence_used=["scanner", "quote"],
        disconfirming_evidence=["event risk"],
        confidence="0.72",
    )


def no_trade_turn():
    return AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        confidence="0.8",
        reasoning_summary="No attractive opportunity",
        reason_codes=["NO_EDGE_FOUND"],
    )


def research_quote_turn(symbol="NVDA"):
    return AutonomousTurn(
        mode=AutonomousTurnMode.RESEARCH,
        research_requests=[
            ResearchRequest(
                request_id="rq1",
                tool=ResearchTool.QUOTE,
                arguments={"symbol": symbol},
                purpose="observe current price",
            )
        ],
        decision=None,
        proposal=None,
        confidence="0.5",
        reasoning_summary="Observe the market",
        reason_codes=[],
    )


def event_types(db):
    return [
        row[0]
        for row in db.execute(
            "SELECT DISTINCT event_type FROM autonomous_research_events "
            "ORDER BY event_type"
        ).fetchall()
    ]


def regret_rows(db):
    return db.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='regret_observation'"
    ).fetchall()


def regret_outcome_rows(db):
    return db.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='regret_outcome'"
    ).fetchall()


def observation_payload(row):
    payload = json.loads(row[0])
    return payload.get("observation") or payload


def test_runtime_persists_regret_for_rejected_identifiable_proposal(tmp_path):
    value = bundle("cycle-regret-a")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            database=db,
            provider=SequenceProvider([propose_trade_turn("NVDA")]),
            toolbox=RejectingToolbox(),
        )

        assert result["outcome"]["decision"] == "NO_TRADE"
        assert result["outcome"]["accepted"] is False

        types = event_types(db)
        for expected in (
            "model_turn",
            "proposal_validation",
            "research_telemetry_summary",
            "final_outcome",
            "interference_observation",
            "regret_observation",
        ):
            assert expected in types, f"missing event_type {expected}"

        records = [observation_payload(row) for row in regret_rows(db)]
        assert len(records) == 1
        record = records[0]
        assert record["candidate"]["symbol"] == "NVDA"
        assert record["decision_cycle_id"] == "cycle-regret-a"
        assert record["ex_ante_evidence_sha256"]
        assert record["rejection_reason_codes"] == ["BROKER_FEASIBILITY_FAILED"]
        assert record["rejection_mechanism"] == "BROKER_OR_EXECUTION_FEASIBILITY"
        assert record["ex_post_outcome"] is None
        assert record["policy_status"] == "OBSERVATION"


def test_no_regret_for_no_trade_without_identifiable_candidate(tmp_path):
    value = bundle("cycle-notrade-a")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            value,
            database=db,
            provider=SequenceProvider([no_trade_turn()]),
            toolbox=QuoteToolbox(),
        )

        assert regret_rows(db) == []
        assert regret_outcome_rows(db) == []


def test_ex_post_observer_persists_outcome_from_later_legitimate_observation(
    tmp_path,
):
    cycle1 = bundle("cycle-regret-1")
    cycle2 = bundle("cycle-regret-2")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            cycle1,
            database=db,
            provider=SequenceProvider([propose_trade_turn("NVDA")]),
            toolbox=RejectingToolbox(),
        )
        original = observation_payload(regret_rows(db)[0])
        record_id = original["record_id"]

        run_autonomous_cycle(
            cycle2,
            database=db,
            provider=SequenceProvider(
                [research_quote_turn("NVDA"), no_trade_turn()]
            ),
            toolbox=QuoteToolbox(quote_price="6.10"),
        )

        outcomes = [observation_payload(row) for row in regret_outcome_rows(db)]
        assert len(outcomes) == 1
        outcome = outcomes[0]
        assert outcome["regret_record_id"] == record_id
        assert outcome["decision_cycle_id"] == "cycle-regret-1"
        assert outcome["observed_at_utc"]
        assert outcome["observed_value"] == "6.10"
        assert outcome["price_source"] == "last"
        assert outcome["source_event_sha256"]
        assert "sample_size" in outcome
        assert outcome["policy_status"] == "OBSERVATION"


def test_no_regret_outcome_without_real_observation(tmp_path):
    cycle1 = bundle("cycle-regret-x1")
    cycle2 = bundle("cycle-regret-x2")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            cycle1,
            database=db,
            provider=SequenceProvider([propose_trade_turn("NVDA")]),
            toolbox=RejectingToolbox(),
        )
        assert len(regret_rows(db)) == 1

        # Later cycle observes nothing about NVDA.
        run_autonomous_cycle(
            cycle2,
            database=db,
            provider=SequenceProvider([no_trade_turn()]),
            toolbox=QuoteToolbox(),
        )

        assert regret_outcome_rows(db) == []


def test_regret_outcome_idempotent_across_cycle_reprocessing(tmp_path):
    cycle1 = bundle("cycle-regret-i1")
    cycle2 = bundle("cycle-regret-i2")
    cycle2b = bundle("cycle-regret-i2b")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            cycle1,
            database=db,
            provider=SequenceProvider([propose_trade_turn("NVDA")]),
            toolbox=RejectingToolbox(),
        )

        # Two later cycles legitimately observe the same market state
        # (same quote evidence). The pending regret must be resolved once,
        # not once per observing cycle.
        run_autonomous_cycle(
            cycle2,
            database=db,
            provider=SequenceProvider(
                [research_quote_turn("NVDA"), no_trade_turn()]
            ),
            toolbox=QuoteToolbox(),
        )
        run_autonomous_cycle(
            cycle2b,
            database=db,
            provider=SequenceProvider(
                [research_quote_turn("NVDA"), no_trade_turn()]
            ),
            toolbox=QuoteToolbox(),
        )

        outcomes = [observation_payload(row) for row in regret_outcome_rows(db)]
        assert len(outcomes) == 1
        assert outcomes[0]["decision_cycle_id"] == "cycle-regret-i1"


def test_regret_extraction_failure_is_analytical_not_authoritative(
    tmp_path, monkeypatch
):
    value = bundle("cycle-regret-fail")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        def broken_extract(outcome, *, rejection_mechanism, decision_cycle_id=""):
            raise RuntimeError("analysis exploded")

        monkeypatch.setattr(runtime, "extract_regret_observations", broken_extract)

        result = run_autonomous_cycle(
            value,
            database=db,
            provider=SequenceProvider([propose_trade_turn("NVDA")]),
            toolbox=RejectingToolbox(),
        )

        # The trading decision is unchanged by the analytical failure.
        assert result["outcome"]["decision"] == "NO_TRADE"
        assert result["outcome"]["accepted"] is False
        # No fabricated regret record.
        assert regret_rows(db) == []
        # A sanitized analytical failure note exists (no raw message).
        failure_rows = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='analytical_observer_failure'"
        ).fetchall()
        assert failure_rows
        note = observation_payload(failure_rows[0])
        assert note["stage"] == "regret_extraction"
        assert note["error_class"] == "RuntimeError"
        assert "analysis exploded" not in json.dumps(note)


def test_same_cycle_observation_never_becomes_ex_post_outcome(tmp_path):
    value = bundle("cycle-regret-self")
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        # The cycle observes NVDA and then rejects an NVDA proposal in the
        # same cycle: the self-observation must not resolve itself.
        run_autonomous_cycle(
            value,
            database=db,
            provider=SequenceProvider(
                [research_quote_turn("NVDA"), propose_trade_turn("NVDA")]
            ),
            toolbox=RejectingToolbox(),
        )

        assert len(regret_rows(db)) == 1
        assert regret_outcome_rows(db) == []
