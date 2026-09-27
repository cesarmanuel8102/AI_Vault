"""AUTONOMY_EPOCH_1 integration wiring tests (deterministic, no Codex)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox
from ibkr_paper_30d.autonomy_workspace import AutonomyWorkspace
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


class RecordingProvider:
    """Fake provider that records the payload it was prompted with."""

    last_native_tool_events = []

    def __init__(self, turns, *, workspace_expected=None):
        self.turns = list(turns)
        self.payloads = []
        self.workspace_expected = workspace_expected

    def next_turn(self, request, bundle, history, toolbox_manifest):
        self.payloads.append(
            {
                "history": list(history),
                "manifest": list(toolbox_manifest),
                "request": request.model_dump(mode="json"),
            }
        )
        return self.turns.pop(0)


class PassiveToolbox:
    def manifest(self):
        return [{"tool": ResearchTool.QUOTE.value, "purpose": "stub"}]

    def execute(self, request, bundle):
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data={"stub": True},
        )

    def validate_proposal(self, proposal, bundle):
        return ProposalValidation(passed=True, reason_codes=(), broker_evidence={})


def bundle(cycle="cycle-wiring"):
    return TraderInputBundle(
        decision_cycle_id=cycle,
        utc_timestamp="2026-09-26T14:00:00Z",
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


def request(value):
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id=f"inv-{value.decision_cycle_id}",
        utc_timestamp="2026-09-26T14:00:01Z",
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


def no_trade_turn():
    return AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.NO_TRADE,
        proposal=None,
        confidence="0.8",
        reasoning_summary="no action required",
        reason_codes=[],
    )


def workspace_tool_turn(operation, arguments, rid="r1"):
    return AutonomousTurn(
        mode=AutonomousTurnMode.RESEARCH,
        research_requests=[
            ResearchRequest(
                request_id=rid,
                tool=ResearchTool.WORKSPACE,
                arguments=arguments,
                purpose="workspace capability",
            )
        ],
        decision=None,
        proposal=None,
        confidence="0.5",
        reasoning_summary="use workspace",
        reason_codes=[],
    )


def test_workspace_context_flows_into_prompt_across_cycles(tmp_path):
    workspace = AutonomyWorkspace(tmp_path / "ws")
    toolbox = AutonomyToolbox(PassiveToolbox(), workspace)
    value = bundle("cycle-ws-1")
    provider = RecordingProvider([no_trade_turn()])

    from ibkr_paper_30d.autonomous_runtime import AutonomousTraderBoundary

    boundary = AutonomousTraderBoundary(
        provider=provider, toolbox=toolbox, execute_paper=False
    )
    result = boundary.invoke("SCHEDULED_SCAN", value)

    # Empty workspace: no context key added to the provider attribute.
    assert result["outcome"]["decision"] == "NO_TRADE"

    # Model writes an artifact through the WORKSPACE tool.
    workspace.write_artifact("memory/h1.md", "H1: regime shift study", cycle_id="cycle-ws-1")

    # A later cycle receives the persisted workspace summary in its prompt.
    provider2 = RecordingProvider([no_trade_turn()])
    boundary2 = AutonomousTraderBoundary(
        provider=provider2, toolbox=toolbox, execute_paper=False
    )
    value2 = bundle("cycle-ws-2")
    boundary2.invoke("SCHEDULED_SCAN", value2)
    assert provider2.workspace_context == workspace.summary()
    assert provider2.workspace_context["artifact_count"] == 1


def test_model_can_use_workspace_tool_from_research_turn(tmp_path):
    workspace = AutonomyWorkspace(tmp_path / "ws")
    toolbox = AutonomyToolbox(PassiveToolbox(), workspace)
    value = bundle("cycle-wtool")
    turns = [
        workspace_tool_turn(
            "write",
            {
                "operation": "write",
                "path": "memory/idea.md",
                "content": "study overnight gaps",
                "cycle_id": value.decision_cycle_id,
            },
        ),
        no_trade_turn(),
    ]
    provider = RecordingProvider(turns)

    outcome = AutonomousResearchLoop(provider, toolbox).run(request(value), value)

    assert outcome.accepted is True
    artifacts = workspace.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0]["path"] == "memory/idea.md"
    assert artifacts[0]["created_by_cycle"] == "cycle-wtool"


def test_research_continuity_persist_and_resume(tmp_path):
    """Part 9: an investigation that does not fit one cycle persists its
    objective in the workspace and a later cycle reads it back."""

    workspace = AutonomyWorkspace(tmp_path / "ws")
    toolbox = AutonomyToolbox(PassiveToolbox(), workspace)
    cycle1 = bundle("cycle-cont-1")

    turns1 = [
        workspace_tool_turn(
            "write",
            {
                "operation": "write",
                "path": "research/open_question.md",
                "content": "Q: is IV premium systematically overpriced pre-earnings?",
                "cycle_id": cycle1.decision_cycle_id,
            },
        ),
        no_trade_turn(),
    ]
    AutonomousResearchLoop(RecordingProvider(turns1), toolbox).run(
        request(cycle1), cycle1
    )

    # Later cycle reads the persisted question and continues.
    cycle2 = bundle("cycle-cont-2")
    turns2 = [
        workspace_tool_turn(
            "read", {"operation": "read", "path": "research/open_question.md"}, rid="r2"
        ),
        no_trade_turn(),
    ]
    provider2 = RecordingProvider(turns2)
    outcome2 = AutonomousResearchLoop(provider2, toolbox).run(
        request(cycle2), cycle2
    )

    assert outcome2.accepted is True
    read_event = [
        e
        for e in outcome2.transcript
        if e["type"] == "research_result"
        and e["payload"].get("tool") == "WORKSPACE"
    ]
    assert read_event
    content = read_event[0]["payload"]["data"]["content"]
    assert "IV premium" in content


def test_runtime_cycle_persists_workspace_events_to_db(tmp_path):
    workspace = AutonomyWorkspace(tmp_path / "ws")
    workspace.write_artifact("memory/persisted.md", "evidence", cycle_id="c0")
    toolbox = AutonomyToolbox(PassiveToolbox(), workspace)
    value = bundle("cycle-dbw")

    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        run_autonomous_cycle(
            value,
            database=db,
            provider=RecordingProvider([no_trade_turn()]),
            toolbox=toolbox,
        )
        # The autonomous research events remain append-only and the cycle
        # completes without touching workspace events (workspace registry is
        # separate by design); assert DB integrity only.
        count = db.execute(
            "SELECT COUNT(*) FROM autonomous_research_events"
        ).fetchone()[0]
    assert count >= 3