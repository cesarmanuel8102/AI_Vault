from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.autonomous_research import (
    AutonomousTradeProposal,
    CodexAutonomousCLIProvider,
    _resolve_codex_executable,
)
from ibkr_paper_30d.autonomous_runtime import build_request
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


def test_build_request_preserves_exact_authority_visible_provider_timeout() -> None:
    value = bundle()

    built = build_request(
        value,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        experiment_id="paper-30d",
        timeout_seconds=321,
        trigger="SCHEDULED_SCAN",
    )

    assert built.timeout_seconds == 321


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


def test_strict_schema_and_prompt_expose_neutral_continuity_authority() -> None:
    schema = CodexAutonomousCLIProvider.strict_output_schema()
    assert "continuity_plan" in schema["properties"]
    assert "continuity_reviews" in schema["properties"]

    value = bundle().model_copy(
        update={
            "continuity_context": {
                "authority_contract_required": True,
                "active_plans": [{"plan_id": "plan-1"}],
                "provider_states": [{"state": "TIMEOUT_CONFIRMED"}],
                "pending_factual_reports": [{"report_id": "report-1"}],
                "prior_reflections": [
                    {"reflection_id": "reflection-1", "trust": "UNTRUSTED_MODEL_REFLECTION"}
                ],
            }
        }
    )
    payload = CodexAutonomousCLIProvider._prompt_payload(
        request(value), value, [], []
    )
    assert payload["continuity_authority"] == value.continuity_context
    instruction = payload["output_contract"]["continuity_instruction"].lower()
    assert all(
        token not in instruction
        for token in ("timeout", "cancel", "retain", "price", "symbol", "strategy", "adversarial")
    )


def test_prompt_exposes_both_sleeves_and_capabilities_without_host_recommendation():
    value = bundle().model_copy(
        update={
            "multi_sleeve_portfolio": {
                "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
                "regular": {"equity": "500"},
                "extended": {"equity": "500"},
            },
            "contract_ownership_snapshot": {"contract_sleeves": {}},
            "product_capability_snapshot": {"families": []},
        }
    )
    payload = CodexAutonomousCLIProvider._prompt_payload(request(value), value, [], [])
    assert payload["bundle"]["multi_sleeve_portfolio"] == value.multi_sleeve_portfolio
    assert payload["mandate"]["predefined_symbol_universe"] is False
    assert payload["mandate"]["predefined_strategy_family"] is False


def test_prompt_exposes_host_derived_continuity_provenance_bindings() -> None:
    value = bundle().model_copy(
        update={
            "continuity_context": {
                "authority_contract_required": True,
                "epoch_id": "AUTONOMY_EPOCH_2",
                "definition_sha256": "a" * 64,
                "clock_event_sha256": "b" * 64,
                "owner_authorization_sha256": "c" * 64,
            }
        }
    )
    invocation = request(value)

    payload = CodexAutonomousCLIProvider._prompt_payload(
        invocation, value, [], []
    )

    bindings = payload["continuity_contract"]["host_provenance_bindings"]
    assert bindings == {
        "created_by_model": invocation.actual_model,
        "model_attestation_sha256": sha256_json(
            {"actual_model": invocation.actual_model}
        ),
        "decision_cycle_id": invocation.decision_cycle_id,
        "invocation_id": invocation.invocation_id,
        "input_bundle_sha256": value.sha256,
        "epoch_id": "AUTONOMY_EPOCH_2",
        "definition_sha256": "a" * 64,
        "clock_event_sha256": "b" * 64,
        "owner_authorization_sha256": "c" * 64,
    }
    assert payload["continuity_contract"]["plan_required_for"] == [
        "PROPOSE_TRADE",
        "MODIFY_ORDER",
    ]
    assert payload["continuity_contract"]["host_verifies_bindings"] is True
    assert payload["continuity_contract"]["host_new_proposal_bindings"] == {
        "order_ref": (
            "codex-ibkr-paper-30d-a-"
            f"{invocation.decision_cycle_id[-12:]}"
        ),
    }
    assert "copy" in payload["output_contract"]["continuity_instruction"].lower()
    assert "do not calculate" in payload["output_contract"]["continuity_instruction"].lower()
    assert "proposal_sha256" in payload["output_contract"]["continuity_instruction"]
    assert "original_intent_sha256" in payload["output_contract"]["continuity_instruction"]
    assert "continuity_host_bindings" in payload["output_contract"]["continuity_instruction"]
    assert "same canonical sha256" in payload["output_contract"]["continuity_instruction"].lower()


def test_provider_repairs_wrong_host_attestation_before_returning_turn(
    continuity_plan_factory,
) -> None:
    open_order = {
        "orderRef": "order-78",
        "orderId": 78,
        "permId": 225256222,
        "clientId": 17,
        "contract": {"conId": 756733},
    }
    value = bundle().model_copy(
        update={
            "open_orders_snapshot": [open_order],
            "continuity_context": {
                "authority_contract_required": True,
                "epoch_id": "AUTONOMY_EPOCH_2",
                "definition_sha256": "c" * 64,
                "clock_event_sha256": "d" * 64,
                "owner_authorization_sha256": "e" * 64,
            },
        }
    )
    invocation = request(value)
    correct_attestation = sha256_json({"actual_model": invocation.actual_model})
    wrong_plan = continuity_plan_factory(
        decision_cycle_id=invocation.decision_cycle_id,
        invocation_id=invocation.invocation_id,
        input_bundle_sha256=value.sha256,
        created_by_model=invocation.actual_model,
        model_attestation_sha256="f" * 64,
    )
    correct_plan = wrong_plan.model_copy(
        update={"model_attestation_sha256": correct_attestation}
    )
    prompts = []

    def runner(command, **kwargs):
        prompts.append(json.loads(kwargs["input"]))
        output_path = command[command.index("--output-last-message") + 1]
        selected_plan = wrong_plan if len(prompts) == 1 else correct_plan
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
                    "reasoning_summary": "Preserve the exact owned order authority.",
                    "reason_codes": ["ORDER_CONTINUITY_AUTHORED"],
                    "continuity_plan": selected_plan.model_dump(mode="json"),
                    "continuity_reviews": [],
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

    turn = provider.next_turn(invocation, value, [], [])

    assert turn.continuity_plan == correct_plan
    assert len(prompts) == 2
    repair = prompts[1]["semantic_repair"]
    assert any(
        error["message"] == "CONTINUITY_PLAN_MODEL_ATTESTATION_MISMATCH"
        for error in repair["validation_errors"]
    )
    assert (
        prompts[1]["continuity_contract"]["host_provenance_bindings"]
        ["model_attestation_sha256"]
        == correct_attestation
    )


def test_provider_repairs_missing_required_plan_without_changing_proposal(
    continuity_plan_factory,
) -> None:
    value = bundle().model_copy(
        update={
            "continuity_context": {
                "authority_contract_required": True,
                "epoch_id": "AUTONOMY_EPOCH_2",
                "definition_sha256": "c" * 64,
                "clock_event_sha256": "d" * 64,
                "owner_authorization_sha256": "e" * 64,
            }
        }
    )
    invocation = request(value)
    proposal = AutonomousTradeProposal(
        thesis="Autonomously discovered asymmetric opportunity",
        catalyst="Fresh catalyst",
        symbol="PCVX",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="4",
        order_type="MKT",
        capital_required="295.60",
        maximum_loss="295.60",
        loss_is_bounded=True,
        probability_profit="0.55",
        probability_loss="0.45",
        expected_gain="60.00",
        expected_loss="40.00",
        expected_value="15.00",
        expected_reward_risk="1.50",
        expected_holding_period="1-5 days",
        entry_condition="Thesis remains intact",
        invalidation_condition="Catalyst invalidates",
        exit_plan="Exit when the thesis changes",
        why_now="Current evidence supports entry",
        alternatives_considered=["cash"],
        evidence_used=["quote", "news"],
        disconfirming_evidence=["event risk"],
        confidence="0.72",
    )
    proposal_sha = sha256_json(proposal)
    plan = continuity_plan_factory(
        decision_cycle_id=invocation.decision_cycle_id,
        invocation_id=invocation.invocation_id,
        input_bundle_sha256=value.sha256,
        created_by_model=invocation.actual_model,
        model_attestation_sha256=sha256_json(
            {"actual_model": invocation.actual_model}
        ),
        order_binding={
            "binding_type": "NEW_PROPOSAL",
            "ibkr_order_id": None,
            "perm_id": None,
            "original_order_state_sha256": None,
            "proposal_sha256": proposal_sha,
            "original_intent_sha256": proposal_sha,
        },
    )
    prompts = []

    def runner(command, **kwargs):
        prompts.append(json.loads(kwargs["input"]))
        output_path = command[command.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "PROPOSE_TRADE",
                    "proposal": proposal.model_dump(mode="json"),
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.72",
                    "reasoning_summary": "The proposal remains preferred.",
                    "reason_codes": ["EDGE_FOUND"],
                    "continuity_plan": (
                        None if len(prompts) == 1 else plan.model_dump(mode="json")
                    ),
                    "continuity_reviews": [],
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

    turn = provider.next_turn(invocation, value, [], [])

    assert turn.proposal == proposal
    assert turn.continuity_plan == plan
    assert len(prompts) == 2
    assert any(
        error["message"] == "CONTINUITY_PLAN_REQUIRED"
        for error in prompts[1]["semantic_repair"]["validation_errors"]
    )


def test_provider_repairs_equal_but_wrong_new_proposal_hashes(
    continuity_plan_factory,
) -> None:
    value = bundle().model_copy(
        update={
            "continuity_context": {
                "authority_contract_required": True,
                "epoch_id": "AUTONOMY_EPOCH_2",
                "definition_sha256": "c" * 64,
                "clock_event_sha256": "d" * 64,
                "owner_authorization_sha256": "e" * 64,
            }
        }
    )
    invocation = request(value)
    proposal = AutonomousTradeProposal(
        thesis="Autonomously discovered asymmetric opportunity",
        catalyst="Fresh catalyst",
        symbol="PCVX",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="4",
        order_type="MKT",
        capital_required="295.60",
        maximum_loss="295.60",
        loss_is_bounded=True,
        probability_profit="0.55",
        probability_loss="0.45",
        expected_gain="60.00",
        expected_loss="40.00",
        expected_value="15.00",
        expected_reward_risk="1.50",
        expected_holding_period="1-5 days",
        entry_condition="Thesis remains intact",
        invalidation_condition="Catalyst invalidates",
        exit_plan="Exit when the thesis changes",
        why_now="Current evidence supports entry",
        alternatives_considered=["cash"],
        evidence_used=["quote", "news"],
        disconfirming_evidence=["event risk"],
        confidence="0.72",
    )
    proposal_sha = sha256_json(proposal)
    correct_plan = continuity_plan_factory(
        decision_cycle_id=invocation.decision_cycle_id,
        invocation_id=invocation.invocation_id,
        input_bundle_sha256=value.sha256,
        created_by_model=invocation.actual_model,
        model_attestation_sha256=sha256_json(
            {"actual_model": invocation.actual_model}
        ),
        order_binding={
            "binding_type": "NEW_PROPOSAL",
            "ibkr_order_id": None,
            "perm_id": None,
            "original_order_state_sha256": None,
            "proposal_sha256": proposal_sha,
            "original_intent_sha256": proposal_sha,
        },
    )
    wrong_plan = correct_plan.model_copy(
        update={
            "order_binding": correct_plan.order_binding.model_copy(
                update={
                    "proposal_sha256": "f" * 64,
                    "original_intent_sha256": "f" * 64,
                }
            )
        }
    )
    prompts = []

    def runner(command, **kwargs):
        prompts.append(json.loads(kwargs["input"]))
        output_path = command[command.index("--output-last-message") + 1]
        selected_plan = wrong_plan if len(prompts) == 1 else correct_plan
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "PROPOSE_TRADE",
                    "proposal": proposal.model_dump(mode="json"),
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.72",
                    "reasoning_summary": "The proposal remains preferred.",
                    "reason_codes": ["EDGE_FOUND"],
                    "continuity_plan": selected_plan.model_dump(mode="json"),
                    "continuity_reviews": [],
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

    turn = provider.next_turn(invocation, value, [], [])

    assert turn.proposal == proposal
    assert turn.continuity_plan == correct_plan
    assert len(prompts) == 2
    messages = [
        error["message"]
        for error in prompts[1]["semantic_repair"]["validation_errors"]
    ]
    assert any(proposal_sha in message for message in messages)


def test_strict_schema_has_no_untyped_anyof_branches() -> None:
    schema = CodexAutonomousCLIProvider.strict_output_schema()
    invalid_paths = []

    def inspect(node, path=()):
        if isinstance(node, dict):
            for index, branch in enumerate(node.get("anyOf", [])):
                if isinstance(branch, dict) and not ({"type", "$ref"} & set(branch)):
                    invalid_paths.append(path + ("anyOf", index))
            for key, value in node.items():
                inspect(value, path + (key,))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                inspect(value, path + (index,))

    inspect(schema)

    assert invalid_paths == []


def test_strict_schema_expands_continuity_state_actions_to_fixed_properties() -> None:
    schema = CodexAutonomousCLIProvider.strict_output_schema()
    state_actions = schema["$defs"]["ContinuityContingency"]["properties"][
        "state_actions"
    ]

    assert "propertyNames" not in state_actions
    assert state_actions["additionalProperties"] is False
    assert set(state_actions["properties"]) == {
        "UNFILLED",
        "PARTIALLY_FILLED",
        "FILLED",
        "PENDING_CANCEL",
        "CANCELLED",
        "REJECTED",
        "ABSENT",
    }


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
    assert prompt_payload["mandate"]["objective"].startswith("Maximize terminal experimental PAPER equity")
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


def test_owner_exception_retries_transient_invalid_jsonl_before_accepting_turn():
    value = bundle()
    attempts = []
    delays = []

    def runner(command, **kwargs):
        attempts.append(command)
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
        stdout = (
            "not-json\n"
            if len(attempts) == 1
            else "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "t"}),
                    json.dumps({"type": "turn.completed"}),
                ]
            )
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
    assert len(attempts) == 2
    assert delays == [1.0]
    assert provider.last_failure_code is None


def test_semantically_invalid_turn_is_returned_to_codex_for_bounded_repair():
    value = bundle()
    prompts = []

    def runner(command, **kwargs):
        prompts.append(json.loads(kwargs["input"]))
        output_path = command[command.index("--output-last-message") + 1]
        decision = None if len(prompts) == 1 else "NO_TRADE"
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": decision,
                    "proposal": None,
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.75",
                    "reasoning_summary": "No sufficiently attractive opportunity.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                    "continuity_plan": None,
                    "continuity_reviews": [],
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
    assert len(prompts) == 2
    assert "semantic_repair" not in prompts[0]
    repair = prompts[1]["semantic_repair"]
    assert repair["attempt"] == 1
    assert repair["maximum_attempts"] == 2
    assert repair["invalid_output"]["decision"] is None
    assert any(
        "FINAL mode requires decision" in error["message"]
        for error in repair["validation_errors"]
    )
    assert provider.last_failure_code is None


def test_semantic_repair_attempts_are_bounded_and_leave_diagnostic():
    value = bundle()
    prompts = []

    def runner(command, **kwargs):
        prompts.append(json.loads(kwargs["input"]))
        output_path = command[command.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": None,
                    "proposal": None,
                    "position_action": None,
                    "open_order_action": None,
                    "confidence": "0.75",
                    "reasoning_summary": "Incomplete final decision.",
                    "reason_codes": ["NO_EDGE_FOUND"],
                    "continuity_plan": None,
                    "continuity_reviews": [],
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

    with pytest.raises(RuntimeError, match="AUTONOMOUS_CODEX_OUTPUT_INVALID"):
        provider.next_turn(
            request(value), value, [], [{"tool": "MARKET_SCANNER"}]
        )

    assert len(prompts) == 3
    assert prompts[-1]["semantic_repair"]["attempt"] == 2
    assert provider.last_failure_code == "OUTPUT_INVALID"
    assert "FINAL mode requires decision" in provider.last_failure_detail
