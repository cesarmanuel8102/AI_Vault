from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest

from ibkr_paper_30d.autonomous_research import (
    AutonomousResearchLoop,
    AutonomousTurn,
    AutonomousTurnMode,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.research_telemetry import (
    ResearchTelemetryAccumulator,
    build_telemetry_summary_from_history,
    classify_research_depth,
)
from ibkr_paper_30d.autonomous_runtime import run_autonomous_cycle
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderDecision, TraderInputBundle


class SequenceProvider:
    def __init__(self, turns):
        self.turns = list(turns)

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return self.turns.pop(0)


class ScannerToolbox:
    """Fake toolbox whose execute() returns realistic tool payloads."""

    def __init__(self, *, results=None):
        self.requests = []
        self.results = results or {}

    def manifest(self):
        return [{"tool": item.value} for item in ResearchTool]

    def execute(self, request, bundle):
        self.requests.append(request)
        data = self.results.get(request.tool, {"note": "ok"})
        success = not str(data.get("error") or "")
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=success,
            data=data,
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(passed=True, reason_codes=(), broker_evidence={})


def bundle(equity="500.00"):
    return TraderInputBundle(
        decision_cycle_id="cycle-telemetry-1",
        utc_timestamp="2026-09-23T20:00:00Z",
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
        invocation_id="inv-telemetry-1",
        utc_timestamp="2026-09-23T20:00:01Z",
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


def research_turn(requests):
    return AutonomousTurn(
        mode=AutonomousTurnMode.RESEARCH,
        research_requests=requests,
        decision=None,
        proposal=None,
        confidence="0.5",
        reasoning_summary="Discover opportunities",
        reason_codes=[],
    )


def final_no_trade(summary="No sufficiently attractive opportunity."):
    return AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        confidence="0.8",
        reasoning_summary=summary,
        reason_codes=["NO_EDGE_FOUND"],
    )


def scanner_request(rid="r1"):
    return ResearchRequest(
        request_id=rid,
        tool=ResearchTool.MARKET_SCANNER,
        arguments={"scan_code": "TOP_PERC_GAIN"},
        purpose="discovery",
    )


SCANNER_RESULTS = {
    ResearchTool.MARKET_SCANNER: {
        "success": True,
        "results": [
            {"rank": 0, "contract": {"symbol": "GCTK"}},
            {"rank": 1, "contract": {"symbol": "TWG"}},
            {"rank": 2, "contract": {"symbol": "ARTL"}},
        ],
    }
}


def test_telemetry_counts_only_executed_tool_calls():
    accumulator = ResearchTelemetryAccumulator()
    req = scanner_request()
    accumulator.observe_request(req)
    accumulator.observe_result(
        ResearchResult(
            request_id="r1",
            tool=ResearchTool.MARKET_SCANNER,
            success=True,
            data=SCANNER_RESULTS[ResearchTool.MARKET_SCANNER],
        )
    )

    summary = accumulator.summary()
    assert summary["research_requests_executed"] == 1
    assert summary["scanner_queries"] == 1
    assert summary["scanner_results_received"] == 3
    assert summary["symbols_examined"] == ["ARTL", "GCTK", "TWG"]
    assert summary["telemetry_source"] == "SYSTEM_GENERATED"


def test_model_narrative_does_not_increment_any_counter():
    value = bundle()
    provider = SequenceProvider(
        [final_no_trade("I searched extensively across many instruments and sessions.")]
    )
    toolbox = ScannerToolbox()

    outcome = AutonomousResearchLoop(provider, toolbox).run(request(value), value)

    assert outcome.accepted is True
    assert toolbox.requests == []
    summary = build_telemetry_summary_from_history(outcome.transcript)
    assert summary["research_requests_executed"] == 0
    assert summary["scanner_queries"] == 0
    assert summary["symbols_examined"] == []
    assert classify_research_depth(summary) == "MINIMAL"
    final_events = [
        e for e in outcome.transcript if e["type"] == "research_telemetry_summary"
    ]
    assert final_events, "telemetry summary event must exist in transcript"
    assert final_events[-1]["payload"]["research_requests_executed"] == 0
    assert (
        "extensively_researched" not in json.dumps(final_events[-1]).lower()
    )


def test_claimed_scanner_use_without_execution_counts_zero():
    value = bundle()
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        confidence="0.8",
        reasoning_summary="Scanner showed nothing",
        reason_codes=["USED_SCANNER", "NO_EDGE_FOUND"],
    )
    toolbox = ScannerToolbox()

    outcome = AutonomousResearchLoop(SequenceProvider([final]), toolbox).run(
        request(value), value
    )

    summary = build_telemetry_summary_from_history(outcome.transcript)
    assert summary["scanner_queries"] == 0
    assert summary["research_requests_executed"] == 0


def test_blocked_tool_requests_are_recorded_objectively():
    accumulator = ResearchTelemetryAccumulator()
    req = ResearchRequest(
        request_id="r9",
        tool=ResearchTool.HISTORICAL_BARS,
        arguments={},
        purpose="history",
    )
    accumulator.observe_request(req)
    accumulator.observe_result(
        ResearchResult(
            request_id="r9",
            tool=ResearchTool.HISTORICAL_BARS,
            success=False,
            data={},
            error="market_data_unavailable",
        )
    )

    summary = accumulator.summary()
    assert summary["research_requests_executed"] == 1
    assert summary["blocked_requests"] == 1


def test_tools_used_derives_from_actually_executed_tools():
    value = bundle()
    turns = [
        research_turn(
            [
                scanner_request("r1"),
                ResearchRequest(
                    request_id="r2",
                    tool=ResearchTool.QUOTE,
                    arguments={"symbol": "SPY"},
                    purpose="quote",
                ),
            ]
        ),
        final_no_trade(),
    ]
    toolbox = ScannerToolbox()

    outcome = AutonomousResearchLoop(SequenceProvider(turns), toolbox).run(
        request(value), value
    )

    summary = build_telemetry_summary_from_history(outcome.transcript)
    assert summary["research_requests_executed"] == 2
    assert summary["tools_used"] == ["MARKET_SCANNER", "QUOTE"]


def test_runtime_persists_telemetry_summary_event(tmp_path):
    value = bundle()
    turns = [research_turn([scanner_request("r1")]), final_no_trade()]
    toolbox = ScannerToolbox(results=SCANNER_RESULTS)

    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            database=db,
            provider=SequenceProvider(list(turns)),
            toolbox=toolbox,
        )
        rows = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='research_telemetry_summary'"
        ).fetchall()

    assert rows, "research_telemetry_summary event must be persisted"
    payload = json.loads(rows[-1][0])
    event = payload.get("event") or payload
    assert event["telemetry_source"] == "SYSTEM_GENERATED"
    assert event["research_requests_executed"] == 1
    assert event["scanner_queries"] == 1
    assert event["scanner_results_received"] == 3


def test_telemetry_summary_is_canonical_serializable():
    accumulator = ResearchTelemetryAccumulator()
    accumulator.observe_request(scanner_request())
    accumulator.observe_result(
        ResearchResult(
            request_id="r1",
            tool=ResearchTool.MARKET_SCANNER,
            success=True,
            data=SCANNER_RESULTS[ResearchTool.MARKET_SCANNER],
        )
    )
    summary = accumulator.summary()

    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded)["telemetry_source"] == "SYSTEM_GENERATED"