from __future__ import annotations

from ibkr_paper_30d.autonomous_research import (
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
