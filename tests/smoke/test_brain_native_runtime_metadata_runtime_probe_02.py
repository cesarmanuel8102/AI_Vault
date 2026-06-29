"""Runtime probe for /v2/chat/agent capability_metadata exposure.

Verifies the actual API path (not just the helper) returns capability_metadata.
Uses FastAPI TestClient with strict-operator dependency overridden and finalizer
monkeypatched to avoid live LLM calls.

No memory writes, no FAISS mutation, no trading, no server process required.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import pytest
from fastapi.testclient import TestClient

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
from tmp_agent.brain_v9.main import app

# Disable strict operator dependency for tests only
async def _require_strict_operator_access_passthrough(request, x_brain_token=None):
    return None

_api_security.require_strict_operator_access.__code__ = _require_strict_operator_access_passthrough.__code__

_ORIGINAL_FINALIZE = _finalizer.finalize_agent_run

def _fake_finalize(*args, **kwargs):
    return ("fake final answer for probe", {"provider_used": "mock", "model_used": "mock"})


def setup_module():
    _finalizer.finalize_agent_run = _fake_finalize


def teardown_module():
    _finalizer.finalize_agent_run = _ORIGINAL_FINALIZE


REQUIRED_METADATA_KEYS = {
    "memory_used",
    "retrieval_attempted",
    "retrieval_no_results",
    "retrieval_skipped",
    "planner_used",
    "evidence_routed",
    "evidence_sources_count",
    "tools_considered",
    "tools_executed",
    "tools_blocked",
    "governance_checked",
    "trace_events_count",
    "intent_route",
    "classification",
}


# ============================================================
# Test cases
# ============================================================
def test_runtime_selector_is_native():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


def test_langgraph_not_active():
    rt = get_agent_runtime_v2()
    assert rt.backend != "langgraph"
    assert type(rt).__name__ != "LangGraphAgentRuntimeV2"


def test_route_exists_v2_chat_agent():
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/v2/chat/agent" in routes


def test_capability_metadata_helper_exists():
    from brain_v9.core.agent_kernel_v2 import api_adapter as _api_adapter
    assert hasattr(_api_adapter, "_build_capability_metadata")


def test_chat_agent_response_contains_capability_metadata():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "probe"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "capability_metadata" in data
    assert REQUIRED_METADATA_KEYS.issubset(set(data["capability_metadata"].keys()))


def test_capability_metadata_required_keys():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "probe"},
    )
    data = response.json()
    meta = data["capability_metadata"]
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"Missing metadata key: {key}"


def test_trace_events_count_is_reported():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "probe"},
    )
    meta = response.json()["capability_metadata"]
    assert "trace_events_count" in meta
    assert isinstance(meta["trace_events_count"], int)
    assert meta["trace_events_count"] >= 0


def test_retrieval_skipped_for_brain_evidence_without_semantic():
    """For a brain_evidence route without semantic_retrieve, retrieval_skipped=True."""
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "probe"},
    )
    meta = response.json()["capability_metadata"]
    assert meta["intent_route"] == "brain_evidence"
    # This query does not trigger semantic_retrieve in the evidence plan
    assert meta["retrieval_skipped"] is True


def test_direct_assistant_route_does_not_skip_retrieval():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hi", "mode": "read_only", "user_id": "probe"},
    )
    meta = response.json()["capability_metadata"]
    assert meta["intent_route"] == "direct_assistant"
    assert meta["retrieval_skipped"] is False
    assert meta["planner_used"] is False


def test_governance_checked_true_when_blocked_tools_present():
    # "approval_required_write" classification schedules a write tool in read_only mode
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "apply patch to README.md", "mode": "read_only", "user_id": "probe"},
    )
    data = response.json()
    meta = data["capability_metadata"]
    assert data.get("mode_escalation_required") is True
    assert meta["governance_checked"] is True
    assert meta["tools_blocked"] >= 1


def test_native_runtime_source_untouched_by_metadata_patch():
    nr_path = Path("C:/AI_VAULT_CANONICAL/tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py")
    content = nr_path.read_text(encoding="utf-8")
    assert "capability_metadata" not in content


def test_no_sensitive_paths_modified_by_probe():
    import subprocess
    result = subprocess.run(
        [sys.executable, "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd=Path("C:/AI_VAULT_CANONICAL"),
        capture_output=True,
        text=True,
    )
    assert "SAFE" in result.stdout


# Optional deterministic helper tests using the real helper function
from brain_v9.core.agent_kernel_v2.api_adapter import _build_capability_metadata


def test_helper_retrieval_attempted_true_when_semantic_step_exists():
    run = {
        "intent_route": "brain_evidence",
        "plan": [
            {
                "tool_name": "semantic_retrieve",
                "status": "completed",
                "output": {"result": {"hits": [{"id": "x"}]}},
            }
        ],
    }
    meta = _build_capability_metadata(run)
    assert meta["retrieval_attempted"] is True
    assert meta["memory_used"] is True


def test_helper_retrieval_skipped_for_non_direct_without_semantic():
    run = {
        "intent_route": "mixed_brain_reasoning",
        "plan": [{"tool_name": "grep_search", "status": "completed"}],
    }
    meta = _build_capability_metadata(run)
    assert meta["retrieval_attempted"] is False
    assert meta["retrieval_skipped"] is True


def test_helper_governance_checked_with_blocked_tools():
    run = {
        "intent_route": "operational_agent",
        "blocked_tools": ["write_file"],
        "mode_escalation_required": False,
        "plan": [{"tool_name": "write_file", "status": "blocked"}],
    }
    meta = _build_capability_metadata(run)
    assert meta["governance_checked"] is True
    assert meta["tools_blocked"] == 1
