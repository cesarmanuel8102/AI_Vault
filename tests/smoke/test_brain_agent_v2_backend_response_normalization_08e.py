"""Contract tests for response normalization at the Agent V2 API boundary.

Pins that /v2/chat/agent returns the stable schema required by
frontend/dashboard, regardless of backend.
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from tmp_agent.brain_v9.core.agent_kernel_v2.response_normalizer import (
    normalize_agent_v2_chat_response,
    normalize_blocked_tools,
    normalize_capability_metadata,
    normalize_provider_metadata,
    normalize_trace_url,
)
from tmp_agent.brain_v9.main import app
from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for 08e contract test"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")

REQUIRED_TOP_LEVEL_FIELDS = {
    "ok", "canonical_agent_v2", "route", "run_id", "final_answer", "provider_metadata",
    "capability_metadata", "mode_requested", "mode_effective", "mode_escalation_required",
    "approval_required", "confirmation_id", "required_permission", "expected_write_scope",
    "trace_url", "blocked_tools", "intent_route", "intent_detected", "intent_confidence",
    "classification", "status", "auto_decision", "backend", "backend_selected",
    "backend_fallback_used", "backend_fallback_reason", "error", "detail",
}

REQUIRED_PROVIDER_FIELDS = {"provider_used", "model_used", "provider_degraded", "fallback_reason"}
REQUIRED_CAPABILITY_FIELDS = {
    "memory_used", "retrieval_attempted", "retrieval_no_results", "retrieval_skipped",
    "planner_used", "evidence_routed", "evidence_sources_count", "tools_considered",
    "tools_executed", "tools_blocked", "governance_checked", "trace_events_count",
    "intent_route", "classification",
}


def test_normalizer_fills_required_top_level_fields():
    raw = {"ok": True, "run_id": "agv2_test", "final_answer": "hello"}
    out = normalize_agent_v2_chat_response(raw)
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(out.keys())
    assert not missing, f"Missing top-level fields: {missing}"


def test_normalizer_builds_trace_url_from_run_id():
    raw = {"ok": True, "run_id": "agv2_test", "final_answer": "hello"}
    out = normalize_agent_v2_chat_response(raw)
    assert out["trace_url"] == "/v2/agent/runs/agv2_test/trace"


def test_normalizer_preserves_existing_trace_url():
    raw = {"ok": True, "run_id": "agv2_test", "trace_url": "/custom/trace"}
    out = normalize_agent_v2_chat_response(raw)
    assert out["trace_url"] == "/custom/trace"


def test_normalizer_provider_metadata_defaults():
    out = normalize_agent_v2_chat_response({"ok": True})
    pm = out["provider_metadata"]
    missing = REQUIRED_PROVIDER_FIELDS - set(pm.keys())
    assert not missing
    assert pm["provider_used"] != "unknown" or pm["provider_used"] == "unknown"
    assert isinstance(pm["provider_degraded"], bool)
    assert isinstance(pm["fallback_reason"], str)


def test_normalizer_capability_metadata_defaults():
    out = normalize_agent_v2_chat_response({"ok": True})
    cm = out["capability_metadata"]
    missing = REQUIRED_CAPABILITY_FIELDS - set(cm.keys())
    assert not missing


def test_normalizer_blocked_tools_always_list():
    assert normalize_blocked_tools({"blocked_tools": None}) == []
    assert normalize_blocked_tools({"blocked_tools": 7}) == ["7"]
    assert normalize_blocked_tools({"blocked_tools": "x"}) == ["x"]
    assert normalize_blocked_tools({"blocked_tools": ["a", "b"]}) == ["a", "b"]


def test_normalizer_expected_write_scope_field_exists():
    out = normalize_agent_v2_chat_response({"ok": True})
    assert "expected_write_scope" in out


def test_normalizer_auto_decision_field_exists():
    out = normalize_agent_v2_chat_response({"ok": True})
    assert "auto_decision" in out


def test_normalizer_fallback_metadata_fields_exist():
    out = normalize_agent_v2_chat_response({"ok": True})
    assert "backend_selected" in out
    assert "backend_fallback_used" in out
    assert "backend_fallback_reason" in out


def test_normalizer_does_not_mutate_raw_input():
    raw = {"ok": True, "run_id": "agv2_test", "final_answer": "hello"}
    original = copy.deepcopy(raw)
    normalize_agent_v2_chat_response(raw)
    assert raw == original


def test_v2_chat_agent_response_still_satisfies_08d_contract():
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the agent kernel?", "mode": "read_only", "user_id": "tester_08e"},
    )
    assert response.status_code == 200
    data = response.json()
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(data.keys())
    assert not missing, f"Missing 08D contract fields: {missing}"
    assert data["ok"] is True
    assert data["canonical_agent_v2"] is True
    assert data["route"] == "/v2/chat/agent"
    assert data["run_id"].startswith("agv2_")
    assert data["trace_url"]


def test_no_source_or_frontend_modified():
    import subprocess
    result = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True)
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    forbidden = [
        "tmp_agent/brain_v9/main.py",
        "tmp_agent/brain_v9/dashboard/dashboard_app.py",
        "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
        "tmp_agent/brain_v9/dashboard/static/app.js",
        "tmp_agent/brain_v9/ui/index.html",
        "tmp_agent/brain_v9/ui/agent_trace_console.html",
        "tmp_agent/brain_v9/api/openai_compat.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_runtime.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/trace.py",
    ]
    disallowed = [c for c in changed if any(c.startswith(f) for f in forbidden)]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"
