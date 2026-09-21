from __future__ import annotations

import json
import subprocess

from ibkr_paper_30d.autonomous_research import (
    AutonomousResearchProvider,
    ResearchRequest,
)
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle


class FakeToolbox:
    def __init__(self):
        self.bound_equity = None
        self.calls = []

    def bind_bundle(self, bundle):
        self.bound_equity = bundle.experiment_subledger_snapshot["equity"]

    def manifest(self):
        return {
            "schema": "TEST",
            "tools": {
                "contract_search": {
                    "purpose": "discover any contract",
                    "arguments": {"pattern": "string"},
                }
            },
        }

    def execute(self, request: ResearchRequest):
        self.calls.append(request)
        return {
            "status": "PASS",
            "matches": [
                {
                    "symbol": "NVDA",
                    "security_type": "STK",
                    "contract_id": 12345,
                }
            ],
        }


def bundle():
    return TraderInputBundle(
        decision_cycle_id="cycle-auto-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS", "sha256": "r" * 64},
        experiment_subledger_snapshot={"equity": "735.40"},
        broker_account_snapshot={"buying_power": "735.40"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"status": "PASS"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[{"symbol": "SPY"}],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_REALISM_V1",
        benchmark_state={"cash": "500.00"},
        broker_capability_snapshot={"options_permission_level": 4},
        research_round_budget=4,
    )


def request(value):
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="invocation-auto-1",
        utc_timestamp="2026-09-20T20:00:01Z",
        requested_model="codex-highest",
        actual_model="codex-highest",
        model_configuration={"provider": "codex-cli"},
        reasoning_effort="HIGH",
        input_bundle_sha256=value.sha256,
        risk_policy_version="CAPITAL_BOUNDARY_V2",
        experiment_id="experiment-1",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=60,
    )


def _final_output(value):
    return {
        "decision_cycle_id": value.decision_cycle_id,
        "invocation_id": "invocation-auto-1",
        "decision": "PROPOSE_TRADE",
        "input_bundle_sha256": value.sha256,
        "utc_timestamp": "2026-09-20T20:00:03Z",
        "confidence": "0.74",
        "reason_codes": ["AUTONOMOUSLY_DISCOVERED_OPPORTUNITY"],
        "proposal": {
            "thesis": "Autonomously discovered continuation setup",
            "mechanism": "relative demand",
            "catalyst": "broker-observed market activity",
            "symbol": "NVDA",
            "instrument": "STK",
            "direction": "LONG",
            "security_type": "STK",
            "contract_id": 12345,
            "quantity": "1",
            "capital_required": "150.00",
            "maximum_loss": "150.00",
            "probability_profit": "0.58",
            "expected_value": "21.00",
            "legs": [],
            "entry_condition": "fresh broker quote confirms thesis",
            "invalidation_condition": "thesis invalidates",
            "profit_taking_rule": "adaptive exit",
            "expected_holding_period": "intraday to several days",
            "expected_reward": "60.00",
            "expected_risk": "40.00",
            "expected_reward_risk": "1.50",
            "why_now": "research evidence supports action now",
            "why_this_beats_cash": "positive estimated expected value",
            "best_reasonable_alternative": "remain in cash",
            "disconfirming_evidence": ["market regime can change"],
            "confidence": "0.74",
        },
    }


def test_codex_can_research_symbol_not_present_in_candidate_screen():
    value = bundle()
    calls = {"count": 0}

    def runner(command, **kwargs):
        calls["count"] += 1
        output_path = command[command.index("--output-last-message") + 1]
        if calls["count"] == 1:
            payload = {
                "action": "RESEARCH",
                "rationale_summary": "Search beyond advisory candidates.",
                "capital_state_assessment": "Equity is 735.40; strategy space expanded.",
                "strategy_space_assessment": "No symbol or strategy allowlist applies.",
                "research_requests": [
                    {
                        "request_id": "r1",
                        "tool": "contract_search",
                        "arguments": {"pattern": "NVDA"},
                        "purpose": "Investigate an independently selected opportunity.",
                    }
                ],
                "final_output": None,
            }
        else:
            payload = {
                "action": "FINAL",
                "rationale_summary": "Evidence is sufficient.",
                "capital_state_assessment": "Current equity supports the proposed risk.",
                "strategy_space_assessment": "NVDA was discovered autonomously.",
                "research_requests": [],
                "final_output": _final_output(value),
            }
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "test"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "structured"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    toolbox = FakeToolbox()
    provider = AutonomousResearchProvider(toolbox, runner=runner, max_rounds=4)
    response = provider.invoke(request(value), value)

    assert toolbox.bound_equity == "735.40"
    assert len(toolbox.calls) == 1
    assert toolbox.calls[0].arguments == {"pattern": "NVDA"}
    assert response.structured_output["proposal"]["symbol"] == "NVDA"
    assert response.research_metadata["rounds_used"] == 2
    assert response.research_metadata["tool_calls"] == 1
    assert response.research_evidence[0]["result"]["matches"][0]["symbol"] == "NVDA"


def test_research_budget_exhaustion_fails_to_no_trade():
    value = bundle()

    def runner(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        payload = {
            "action": "RESEARCH",
            "rationale_summary": "Need more evidence.",
            "capital_state_assessment": "Capital noted.",
            "strategy_space_assessment": "Continue research.",
            "research_requests": [
                {
                    "request_id": "same-id",
                    "tool": "contract_search",
                    "arguments": {"pattern": "ANY"},
                    "purpose": "Keep searching.",
                }
            ],
            "final_output": None,
        }
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"type": "turn.completed"}),
            stderr="",
        )

    response = AutonomousResearchProvider(
        FakeToolbox(), runner=runner, max_rounds=2
    ).invoke(request(value), value)

    assert response.structured_output["decision"] == "NO_TRADE"
    assert response.structured_output["reason_codes"] == [
        "RESEARCH_ROUND_BUDGET_EXHAUSTED"
    ]
