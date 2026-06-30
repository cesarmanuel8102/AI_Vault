
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2 import runtime as runtime_module
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_backend_name, get_agent_runtime_v2
from tmp_agent.brain_v9.main import app

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN_08F7_R1")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__
_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for 08f7 r1 default promotion"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


def test_env_unset_selects_langgraph_default(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    assert get_agent_runtime_backend_name() == "langgraph_parity"
    rt = get_agent_runtime_v2()
    if getattr(rt, "backend_selected", rt.backend) != "langgraph_parity":
        pytest.skip("LangGraph unavailable; fallback behavior is tested separately")
    assert rt.backend == "langgraph_parity"
    assert rt.backend_default == "langgraph_parity"
    assert rt.backend_fallback_used is False
    assert rt.rollback_backend == "native_runtime"


def test_explicit_langgraph_selects_langgraph(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    rt = get_agent_runtime_v2()
    if getattr(rt, "backend_selected", rt.backend) != "langgraph_parity":
        pytest.skip("LangGraph unavailable; fallback behavior is tested separately")
    assert rt.backend == "langgraph_parity"
    assert rt.backend_default == "langgraph_parity"


def test_explicit_native_is_rollback(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "native")
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert rt.backend_selected == "native_runtime"
    assert rt.backend_default == "langgraph_parity"
    assert rt.backend_fallback_used is False


def test_langgraph_failure_falls_back_to_native_with_metadata(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    original_try = runtime_module._try_build_langgraph_runtime

    def _fake_try_build(_requested_value):
        return None

    monkeypatch.setattr(runtime_module, "_try_build_langgraph_runtime", _fake_try_build)
    try:
        rt = get_agent_runtime_v2()
        assert rt.backend == "native_runtime"
        assert rt.backend_default == "langgraph_parity"
        assert rt.backend_fallback_used is True
        assert rt.backend_fallback_reason
    finally:
        runtime_module._try_build_langgraph_runtime = original_try


def test_chat_agent_normalized_schema_with_promoted_default(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of Agent V2?", "mode": "read_only", "user_id": "tester_08f7_r1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend_default"] == "langgraph_parity"
    assert data["rollback_backend"] == "native_runtime"
    assert data["runtime_type"]
    assert data["trace_url"]
    assert data["run_id"].startswith("agv2_")


def test_agent_v2_status_exposes_backend_metadata(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    client = TestClient(app)
    response = client.get("/v2/agent/status")
    assert response.status_code == 200
    data = response.json()
    assert data["backend_default"] == "langgraph_parity"
    assert data["rollback_backend"] == "native_runtime"
    assert "backend_selected" in data
    assert "backend_fallback_used" in data


def test_native_rollback_chat_still_works(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "native")
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "hello", "mode": "read_only", "user_id": "tester_08f7_r1_native"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend_selected"] == "native_runtime"
    assert data["backend_default"] == "langgraph_parity"
