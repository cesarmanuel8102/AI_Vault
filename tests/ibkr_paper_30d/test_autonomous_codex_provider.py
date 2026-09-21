from __future__ import annotations

import json
import subprocess

from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle


def bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-provider-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"declared_options_level": 4},
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
        experiment_clock={"remaining_days": 30},
    )


def request(value: TraderInputBundle) -> InvocationRequest:
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="inv-provider-1",
        utc_timestamp="2026-09-20T20:00:01Z",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        model_configuration={"mode": "autonomous_research"},
        reasoning_effort="max",
        input_bundle_sha256=value.sha256,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id="paper-30d",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=60,
    )


def test_autonomous_codex_invocation_enables_live_search_and_max_reasoning():
    value = bundle()
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "NO_TRADE",
                    "proposal": None,
                    "position_action": None,
                    "confidence": "0.75",
                    "reasoning_summary": "No sufficiently attractive opportunity.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                },
                handle,
            )
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "web_search", "id": "w1", "status": "completed"},
                }),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    provider = CodexAutonomousCLIProvider(runner=runner)
    turn = provider.next_turn(request(value), value, [], [{"tool": "MARKET_SCANNER"}])

    command = captured["command"]
    assert "--search" in command
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="max"' in command
    assert turn.decision.value == "NO_TRADE"
    assert provider.last_native_tool_events == [
        {"type": "web_search", "status": "completed", "id": "w1"}
    ]
