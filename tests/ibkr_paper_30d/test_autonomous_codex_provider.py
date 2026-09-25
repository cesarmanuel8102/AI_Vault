from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.autonomous_research import (
    CodexAutonomousCLIProvider,
    _resolve_codex_executable,
)
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


def test_codex_executable_resolves_from_desktop_install_when_path_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    executable = tmp_path / "OpenAI" / "Codex" / "bin" / "build" / "codex.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert _resolve_codex_executable() == str(executable)


def test_codex_executable_prefers_desktop_install_over_older_path_cli(
    tmp_path: Path, monkeypatch
) -> None:
    path_cli = tmp_path / "npm" / "codex.cmd"
    path_cli.parent.mkdir(parents=True)
    path_cli.write_bytes(b"")
    desktop_cli = tmp_path / "OpenAI" / "Codex" / "bin" / "build" / "codex.exe"
    desktop_cli.parent.mkdir(parents=True)
    desktop_cli.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        "ibkr_paper_30d.autonomous_research.shutil.which",
        lambda _name: str(path_cli),
    )

    assert _resolve_codex_executable() == str(desktop_cli)


def test_strict_schema_encodes_dynamic_research_arguments_as_json_string() -> None:
    schema = CodexAutonomousCLIProvider.strict_output_schema()

    arguments = schema["$defs"]["ResearchRequest"]["properties"]["arguments"]

    assert arguments["type"] == "string"
    assert "JSON object" in arguments["description"]


def test_autonomous_codex_decodes_strict_research_arguments() -> None:
    value = bundle()

    def runner(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mode": "RESEARCH",
                    "research_requests": [
                        {
                            "request_id": "scan-1",
                            "tool": "MARKET_SCANNER",
                            "arguments": '{"scan_code":"TOP_PERC_GAIN"}',
                            "purpose": "Discover candidates",
                        }
                    ],
                    "decision": None,
                    "proposal": None,
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.5",
                    "reasoning_summary": "Need discovery",
                    "reason_codes": ["NEED_DISCOVERY"],
                },
                handle,
            )
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "thread.started",
                        "thread_id": "t",
                        "actual_model": "gpt-5.6-sol",
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    turn = CodexAutonomousCLIProvider(runner=runner).next_turn(
        request(value), value, [], [{"tool": "MARKET_SCANNER"}]
    )

    assert turn.research_requests[0].arguments == {
        "scan_code": "TOP_PERC_GAIN"
    }


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
                json.dumps({"type": "thread.started", "thread_id": "t", "actual_model": "gpt-5.6-sol"}),
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
    assert command.index("--search") < command.index("exec")
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="max"' in command
    assert turn.decision.value == "NO_TRADE"
    prompt_payload = json.loads(captured["input"])
    assert prompt_payload["mandate"]["objective"].startswith("Maximize terminal experimental equity")
    assert "trader_style" not in prompt_payload["mandate"]
    assert prompt_payload["mandate"]["predefined_symbol_universe"] is False
    assert prompt_payload["mandate"]["predefined_strategy_family"] is False
    assert provider.last_native_tool_events == [
        {"type": "web_search", "status": "completed", "id": "w1"}
    ]


def test_autonomous_codex_rejects_reported_model_substitution():
    value = bundle()

    def runner(command, **kwargs):
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
                    "reasoning_summary": "No trade.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                },
                handle,
            )
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "thread.started",
                        "thread_id": "t",
                        "model": "gpt-5.5",
                        "actual_model": "gpt-5.5",
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    provider = CodexAutonomousCLIProvider(runner=runner)

    import pytest

    with pytest.raises(
        RuntimeError, match="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED"
    ):
        provider.next_turn(request(value), value, [], [{"tool": "MARKET_SCANNER"}])


def test_owner_exception_accepts_only_completed_pinned_model_invocation():
    value = bundle()

    def runner(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "NO_TRADE",
                    "proposal": None,
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.75",
                    "reasoning_summary": "No trade.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                }
            ),
            encoding="utf-8",
        )
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    provider = CodexAutonomousCLIProvider(
        runner=runner,
        owner_model_attestation_exception_sha256="e" * 64,
    )

    turn = provider.next_turn(
        request(value), value, [], [{"tool": "MARKET_SCANNER"}]
    )

    assert turn.decision.value == "NO_TRADE"
    assert provider.last_model_attestation_mode == "OWNER_EXCEPTION_REQUEST_PIN"


def test_owner_exception_still_rejects_conflicting_model_evidence():
    output = "\n".join(
        [
            json.dumps(
                {
                    "type": "thread.started",
                    "thread_id": "t",
                    "model": "gpt-5.5",
                }
            ),
            json.dumps({"type": "turn.completed"}),
        ]
    )

    with pytest.raises(
        RuntimeError, match="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED"
    ):
        CodexAutonomousCLIProvider._assert_effective_model_with_owner_exception(
            output, "gpt-5.6-sol"
        )


def test_owner_exception_rejects_incomplete_invocation():
    output = json.dumps({"type": "thread.started", "thread_id": "t"})

    with pytest.raises(
        RuntimeError, match="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED"
    ):
        CodexAutonomousCLIProvider._assert_effective_model_with_owner_exception(
            output, "gpt-5.6-sol"
        )


def test_transient_codex_exit_one_is_retried_before_any_turn_is_accepted():
    value = bundle()
    attempts = []
    delays = []

    def runner(command, **kwargs):
        attempts.append(command)
        if len(attempts) < 3:
            return subprocess.CompletedProcess(
                command, 1, stdout="", stderr="transient failure"
            )
        output_path = command[command.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "NO_TRADE",
                    "proposal": None,
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.75",
                    "reasoning_summary": "No trade.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                }
            ),
            encoding="utf-8",
        )
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    provider = CodexAutonomousCLIProvider(
        runner=runner,
        retry_sleep=delays.append,
        owner_model_attestation_exception_sha256="e" * 64,
    )

    turn = provider.next_turn(
        request(value), value, [], [{"tool": "MARKET_SCANNER"}]
    )

    assert turn.decision.value == "NO_TRADE"
    assert len(attempts) == 3
    assert delays == [1.0, 3.0]
    assert provider.last_failure_code is None
