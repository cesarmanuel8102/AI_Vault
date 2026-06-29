"""Recovery tests for native default Agent V2 chat after 08E backend selector guard.

Validates that /v2/chat/agent, /chat legacy, /v1/chat/completions, and the runtime
selector all remain healthy with Native as default and with safe fallback for
incompatible LangGraph backend requests.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9 import api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import (
    get_agent_runtime_v2,
    is_agent_v2_production_runtime_compatible,
)
from tmp_agent.brain_v9.main import app

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "RECOVERY_R1_TEST_ADMIN_TOKEN")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for recovery r1"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


def _client():
    return TestClient(app)


def _native_default_env(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)


def test_native_default_runtime_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"
    assert getattr(rt, "backend_fallback_used", False) is False


def test_invalid_backend_falls_back_to_native_after_08e_r1(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "invalid_backend")
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"
    assert rt.backend_fallback_used is True
    assert "not a recognized backend" in rt.backend_fallback_reason


def test_langgraph_requested_falls_back_if_not_production_compatible_after_08e_r1(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    rt = get_agent_runtime_v2()
    if type(rt).__name__ == "NativeAgentRuntimeV2":
        assert rt.backend_fallback_used is True
        assert (
            "production runtime compatible" in rt.backend_fallback_reason
            or "create_run" in rt.backend_fallback_reason
            or "execute_run" in rt.backend_fallback_reason
        )
    else:
        compatible, missing = is_agent_v2_production_runtime_compatible(rt)
        assert compatible, f"selected backend runtime is missing required methods: {missing}"
        assert rt.backend == "langgraph_parity"


def test_v2_chat_agent_native_default_recovers_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    client = _client()
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hi", "mode": "read_only", "user_id": "recovery_r1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend"] == "native_runtime"
    assert data["final_answer"]
    assert data["run_id"].startswith("agv2_")
    assert data["trace_url"]
    assert isinstance(data["provider_metadata"], dict)
    assert isinstance(data["capability_metadata"], dict)


def test_v2_chat_agent_invalid_backend_safe_fallback_after_08e_r1(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "invalid_backend")
    client = _client()
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hi", "mode": "read_only", "user_id": "recovery_r1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend"] == "native_runtime"
    assert data["backend_fallback_used"] is True


def test_v2_chat_agent_langgraph_env_safe_fallback_after_08e_r1(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    client = _client()
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hi", "mode": "read_only", "user_id": "recovery_r1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["final_answer"]
    assert data["backend"] == "native_runtime"
    assert data["backend_fallback_used"] is True
    assert (
        "production runtime compatible" in (data.get("backend_fallback_reason") or "")
        or "create_run" in (data.get("backend_fallback_reason") or "")
        or "execute_run" in (data.get("backend_fallback_reason") or "")
    )


def test_v2_chat_agent_empty_message_error_shape_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    client = _client()
    response = client.post(
        "/v2/chat/agent",
        json={"message": "", "mode": "read_only", "user_id": "recovery_r1"},
    )
    assert response.status_code in (200, 400, 422)
    body = response.json()
    assert isinstance(body, dict)
    assert body.get("detail") or body.get("error") or "ok" in body


def test_legacy_chat_still_works_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    client = _client()
    response = client.post(
        "/chat",
        json={"message": "hi", "session_id": "recovery_r1", "model_priority": "chat"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data or "content" in data
    assert "canonical_agent_v2" not in data


def test_openai_compat_still_works_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    client = _client()
    response = client.post(
        "/v1/chat/completions",
        json={"model": "brain-v9-local", "messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Brain-Token": "test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    required = {"id", "object", "created", "model", "choices"}
    assert required.issubset(set(data.keys()))
    assert data["object"] == "chat.completion"


def test_no_langgraph_default_activation_after_08e_r1(monkeypatch):
    _native_default_env(monkeypatch)
    client = _client()
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hi", "mode": "read_only", "user_id": "recovery_r1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["backend"] != "langgraph_parity"
    assert "langgraph" not in (data.get("backend") or "").lower()
