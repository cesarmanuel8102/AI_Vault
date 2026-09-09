"""R8.2 contract: bounded, secret-safe provider resilience policy without execution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_transient_failures_have_a_bounded_deterministic_retry_policy():
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    decision = provider_resilience_decision(
        "codex",
        outcome="transport_timeout",
        consecutive_failures=1,
    )

    assert decision.provider_id == "codex"
    assert decision.max_attempts == 3
    assert decision.retry_allowed is True
    assert decision.circuit_state == "CLOSED"
    assert decision.reason == "transient_failure"


def test_policy_accepts_bounded_secret_safe_prompt_and_cost_accounting_metadata():
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    decision = provider_resilience_decision(
        "local_ollama",
        outcome="success",
        consecutive_failures=0,
        metadata={
            "model_id": "local-model",
            "prompt_version": "r8.2",
            "request_class": "inspection",
            "cost_microunits": 17,
        },
    )

    assert decision.cost_microunits == 17


@pytest.mark.parametrize("cost", [-1, True, "17"])
def test_policy_rejects_invalid_cost_accounting_values(cost):
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    with pytest.raises(ValueError, match="provider_cost_microunits_invalid"):
        provider_resilience_decision(
            "local_ollama",
            outcome="success",
            consecutive_failures=0,
            metadata={"cost_microunits": cost},
        )


@pytest.mark.parametrize(
    ("outcome", "failures", "expected_reason"),
    [
        ("transport_timeout", 2, "circuit_open"),
        ("transport_failure", 2, "circuit_open"),
        ("configuration_failure", 0, "configuration_failure"),
    ],
)
def test_policy_never_retries_open_circuit_or_configuration_failure(
    outcome, failures, expected_reason
):
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    decision = provider_resilience_decision(
        "kimi_k2_6_cloud",
        outcome=outcome,
        consecutive_failures=failures,
    )

    assert decision.retry_allowed is False
    assert decision.reason == expected_reason
    assert decision.circuit_state == ("OPEN" if failures >= 2 else "CLOSED")


@pytest.mark.parametrize(
    "metadata",
    [
        {"api_key": "not-a-secret"},
        {"nested": {"authorization": "not-a-secret"}},
        {"runtime_configuration": "mutate"},
        {"unknown": "value"},
    ],
)
def test_policy_rejects_secret_bearing_or_non_allowlisted_metadata(metadata):
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    with pytest.raises(ValueError):
        provider_resilience_decision(
            "local_ollama",
            outcome="success",
            consecutive_failures=0,
            metadata=metadata,
        )


@pytest.mark.parametrize(
    ("provider_id", "outcome", "failures"),
    [
        ("unknown", "success", 0),
        ("codex", "unknown", 0),
        ("codex", "success", -1),
        ("codex", "success", 3),
    ],
)
def test_policy_fails_closed_for_unknown_or_unbounded_inputs(provider_id, outcome, failures):
    from tmp_agent.brain_v9.core.provider_gateway import provider_resilience_decision

    with pytest.raises(ValueError):
        provider_resilience_decision(
            provider_id,
            outcome=outcome,
            consecutive_failures=failures,
        )


def test_policy_module_has_no_provider_client_network_or_runtime_configuration_imports():
    source = (ROOT / "tmp_agent/brain_v9/core/provider_gateway.py").read_text(encoding="utf-8")

    for forbidden in ("import os", "import requests", "import subprocess", "from .llm import"):
        assert forbidden not in source
    assert "provider_resilience_decision" in source


def test_evidence_records_a_static_no_deploy_resilience_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R8_2_PROVIDER_RESILIENCE_SECRET_SAFE_OPERATIONS.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item_id"] == "R8.2"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "provider_call": False,
        "runtime_configuration_mutation": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
    }


def test_closeout_closes_r8_2_and_authorizes_only_bound_r8_3():
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R8_2_PROVIDER_RESILIENCE_SECRET_SAFE_OPERATIONS_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["roadmap_items"]["R8.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert [
        item_id
        for item_id, item in manifest["roadmap_items"].items()
        if item["status"] == "AUTHORIZED_ACTIVE"
    ] == ["R8.3"]
    binding = manifest["roadmap_items"]["R8.3"]["automation"]
    assert binding["jit_binding_completed"] is True
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["work_branch"] == "control-plane/r8-3-provider-gateway-route-fallback-validation"
    assert closeout["parent_merge_commit"] == "227fbca2cc9856e9cc47a22aab37c69891d56884"
    assert closeout["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "provider_call": False,
        "canonical_local_sync": False,
    }
