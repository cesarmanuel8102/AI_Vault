from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.trader_invocation import (
    CodexCLIProvider,
    InvocationRequest,
    TraderInputBundle,
)


def bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="real-codex-test-cycle-v1",
        utc_timestamp="2026-09-20T17:00:00Z",
        market_session_state="SYNTHETIC_NON_TRADING",
        reconciliation_receipt={"status": "SYNTHETIC", "sha256": "r" * 64},
        experiment_subledger_snapshot={"equity": "500.00", "synthetic": True},
        broker_account_snapshot={"synthetic": True, "account_identity": None},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"status": "BLOCK", "order_authority": False},
        kill_switch_state="KILL_SWITCH_TRIGGERED",
        market_data_snapshot={"gate_status": "PASS", "synthetic": True},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="PROCESS_TEST_V1",
        execution_realism_version="NON_EXECUTABLE_TEST_V1",
        benchmark_state={"synthetic": True},
    )


def request(value: TraderInputBundle) -> InvocationRequest:
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="real-codex-test-invocation-v1",
        utc_timestamp="2026-09-20T17:00:01Z",
        requested_model="gpt-5.5",
        actual_model="gpt-5.5",
        model_configuration={"provider": "codex-cli", "synthetic": True},
        reasoning_effort="medium",
        input_bundle_sha256=value.sha256,
        risk_policy_version="MONTH1_V1",
        experiment_id="prelifecycle-provider-test",
        invocation_trigger="OWNER_AUTHORIZED_NON_TRADING_TEST",
        timeout_seconds=60,
    )


def output(value: TraderInputBundle) -> dict[str, object]:
    return {
        "decision_cycle_id": value.decision_cycle_id,
        "invocation_id": "real-codex-test-invocation-v1",
        "decision": "NO_TRADE",
        "input_bundle_sha256": value.sha256,
        "utc_timestamp": "2026-09-20T17:00:02Z",
        "confidence": "1.0",
        "reason_codes": ["SYNTHETIC_NON_TRADING_TEST"],
        "proposal": None,
    }


def test_codex_cli_provider_uses_isolated_schema_bound_ephemeral_invocation() -> None:
    value = bundle()
    captured = {}

    def runner(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        captured["cwd_entries_before"] = sorted(
            path.name for path in Path(kwargs["cwd"]).iterdir()
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(output(value)), encoding="utf-8")
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

    response = CodexCLIProvider(runner=runner).invoke(request(value), value)

    command = captured["command"]
    assert command[:2] == ["codex", "exec"]
    assert "--ephemeral" in command
    assert "--ignore-rules" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="medium"' in command
    assert captured["kwargs"]["cwd"] != Path.cwd()
    assert captured["cwd_entries_before"] == ["trader_output_schema.json"]
    assert captured["kwargs"]["timeout"] == 60
    assert "Secrets" not in captured["kwargs"]["input"]
    assert response.actual_model == "gpt-5.5"
    assert response.structured_output["decision"] == "NO_TRADE"


@pytest.mark.parametrize(
    "item_type", ["command_execution", "mcp_tool_call", "file_change", "web_search"]
)
def test_codex_cli_provider_rejects_any_tool_activity(item_type) -> None:
    value = bundle()

    def runner(command, **kwargs):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(output(value)), encoding="utf-8")
        stdout = json.dumps(
            {"type": "item.started", "item": {"type": item_type, "id": "unsafe"}}
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(RuntimeError, match="CODEX_TOOL_ACTIVITY_DETECTED"):
        CodexCLIProvider(runner=runner).invoke(request(value), value)


def test_codex_cli_provider_timeout_is_normalized() -> None:
    value = bundle()

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(TimeoutError):
        CodexCLIProvider(runner=runner).invoke(request(value), value)


def test_codex_output_schema_requires_nullable_fields() -> None:
    schema = CodexCLIProvider.strict_output_schema()

    assert set(schema["required"]) == set(schema["properties"])
    assert "proposal" in schema["required"]
    assert schema["additionalProperties"] is False
    assert "pattern" not in json.dumps(schema)
