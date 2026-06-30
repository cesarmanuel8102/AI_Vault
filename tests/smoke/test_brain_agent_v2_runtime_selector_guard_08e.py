"""Contract tests for the runtime selector guard.

Pins that LangGraphParityRuntimeV2 is now the default when AGENT_V2_BACKEND is unset, that invalid values fall back safely to Native, and that explicit Native remains the rollback backend.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import (
    NATIVE_BACKEND_VALUES,
    get_agent_runtime_backend_name,
    get_agent_runtime_v2,
    is_langgraph_backend_requested,
    resolve_agent_v2_backend_choice,
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


def _clear_env(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)


def test_default_backend_is_langgraph_when_env_unset(monkeypatch):
    _clear_env(monkeypatch)
    rt = get_agent_runtime_v2()
    selected = getattr(rt, "backend_selected", rt.backend)
    if selected != "langgraph_parity":
        pytest.skip("LangGraph unavailable; fallback verified elsewhere")
    assert rt.backend == "langgraph_parity"
    assert getattr(rt, "backend_default", None) == "langgraph_parity"


@pytest.mark.parametrize("value", ["native", "native_runtime", ""])
def test_native_backend_selected_for_native_values(value, monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", value)
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert get_agent_runtime_backend_name() == "native_runtime"


def test_invalid_backend_value_falls_back_to_native(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "bad_value")
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert getattr(rt, "backend_fallback_used", False) is True
    assert getattr(rt, "backend_fallback_reason", "") is not None


def test_unset_env_resolves_to_langgraph_default(monkeypatch):
    _clear_env(monkeypatch)
    assert get_agent_runtime_backend_name() == "langgraph_parity"
    assert is_langgraph_backend_requested(os.environ.get("AGENT_V2_BACKEND"))


def test_langgraph_backend_request_falls_back_if_unavailable(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    # Simulate LangGraph unavailable by monkeypatching the runtime module's helper
    import brain_v9.core.agent_kernel_v2.runtime as runtime_module
    original_try = runtime_module._try_build_langgraph_runtime
    def _fake_try_build(_requested_value):
        return None
    monkeypatch.setattr(runtime_module, "_try_build_langgraph_runtime", _fake_try_build)
    try:
        rt = get_agent_runtime_v2()
        assert rt.backend == "native_runtime"
        assert getattr(rt, "backend_fallback_used", False) is True
        reason = getattr(rt, "backend_fallback_reason", "")
        assert "unavailable" in reason.lower() or "failed" in reason.lower()
    finally:
        runtime_module._try_build_langgraph_runtime = original_try


def test_langgraph_backend_request_can_select_langgraph_if_available(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    rt = get_agent_runtime_v2()
    selected = getattr(rt, "backend_selected", rt.backend)
    if selected in {"langgraph_parity", "langgraph_parity_runtime"}:
        assert rt.backend != "native_runtime"
    else:
        pytest.skip("LangGraph package not installed or failed to initialize; fallback verified elsewhere")


def test_api_adapter_default_langgraph_contract_after_selector_change(monkeypatch):
    _clear_env(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the agent kernel?", "mode": "read_only", "user_id": "tester_08e"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend_default"] == "langgraph_parity"
    assert data["rollback_backend"] == "native_runtime"


def test_api_adapter_invalid_env_fallback_contract(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "invalid_backend")
    import brain_v9.core.agent_kernel_v2.runtime as runtime_module
    rt = runtime_module.get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert rt.backend_fallback_used is True
    assert "not a recognized backend" in rt.backend_fallback_reason
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the agent kernel?", "mode": "read_only", "user_id": "tester_08e"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["backend"] == "native_runtime"
    assert data["backend_fallback_used"] is True
    assert data["backend_fallback_reason"]
    assert data["trace_url"]
    assert data["run_id"].startswith("agv2_")
    # The API adapter does not have direct access to runtime fallback state,
    # so ensure the reason text mentions the env value at normalization time.
    assert "invalid_backend" in data["backend_fallback_reason"] or "invalid" in data["backend_fallback_reason"].lower()


def test_resolve_backend_choice_function():
    assert resolve_agent_v2_backend_choice(None) == "langgraph_parity"
    assert resolve_agent_v2_backend_choice("") == "native_runtime"
    assert resolve_agent_v2_backend_choice("native") == "native_runtime"
    assert resolve_agent_v2_backend_choice("native_runtime") == "native_runtime"
    assert resolve_agent_v2_backend_choice("langgraph") == "langgraph_parity"
    assert resolve_agent_v2_backend_choice("langgraph_parity") == "langgraph_parity"
    assert resolve_agent_v2_backend_choice("bad") == "native_runtime"


def test_is_langgraph_backend_requested_function():
    assert is_langgraph_backend_requested(None)
    assert not is_langgraph_backend_requested("")
    assert not is_langgraph_backend_requested("native")
    assert is_langgraph_backend_requested("langgraph")
    assert is_langgraph_backend_requested("langgraph_parity")


def test_no_frontend_dashboard_source_modified():
    import subprocess
    result = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True)
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    forbidden = [
        "tmp_agent/brain_v9/ui/index.html",
        "tmp_agent/brain_v9/ui/agent_trace_console.html",
        "tmp_agent/brain_v9/dashboard/dashboard_app.py",
        "tmp_agent/brain_v9/dashboard/static/app.js",
    ]
    disallowed = [c for c in changed if any(c.startswith(f) for f in forbidden)]
    assert not disallowed, f"Disallowed frontend/dashboard files modified: {disallowed}"


def test_no_sensitive_paths_touched():
    import subprocess
    for prefix in [
        "memory/semantic", "memory/autonomous_journal", "memory/promotion_queue",
        "memory/semantic_staging", "tmp_test_faiss.py", ".env", ".env.local",
        "20_TRADING", "tmp_agent/brain_v9/trading", "tmp_agent/brain_v9/broker",
        "tmp_agent/brain_v9/qc", "tmp_agent/brain_v9/quantconnect",
    ]:
        result = subprocess.run(["git", "status", "--short", "--", prefix], cwd=REPO_ROOT, capture_output=True, text=True)
        tracked = [l.strip() for l in result.stdout.splitlines() if l.strip() and not l.startswith("??")]
        assert not tracked, f"Sensitive tracked change in {prefix}: {tracked}"
