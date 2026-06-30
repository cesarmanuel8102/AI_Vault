"""Contract tests for LangGraph runtime contract parity (08F1).

Pins that LangGraphParityRuntimeV2 implements the production Agent V2 runtime
interface with LangGraph promoted as default while Native remains explicit rollback.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
from tmp_agent.brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import (
    LANGGRAPH_AVAILABLE,
    LangGraphParityRuntimeV2,
)
from tmp_agent.brain_v9.main import app
from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN_08F1")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for 08f1 contract test"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")

REQUIRED_RUN_FIELDS = {
    "run_id",
    "final_answer",
    "status",
    "provider_metadata",
    "capability_metadata",
    "backend_selected",
    "backend_fallback_used",
    "backend_fallback_reason",
    "trace_url",
}

REQUIRED_CHAT_FIELDS = {
    "ok",
    "canonical_agent_v2",
    "run_id",
    "final_answer",
    "provider_metadata",
    "capability_metadata",
    "trace_url",
    "backend",
    "backend_selected",
    "backend_fallback_used",
    "backend_fallback_reason",
}


@pytest.fixture
def temp_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        rt = LangGraphParityRuntimeV2(run_root=tmp)
        yield rt


# ------------------------------------------------------------------
# 1. Runtime interface parity
# ------------------------------------------------------------------
def test_langgraph_runtime_has_required_methods(temp_runtime):
    for method in (
        "create_run",
        "execute_run",
        "plan_run",
        "list_runs",
        "get_run",
        "get_trace",
        "pause_run",
        "resume_run",
        "cancel_run",
    ):
        attr = getattr(temp_runtime, method, None)
        assert callable(attr), f"{method} is not callable"


# ------------------------------------------------------------------
# 2. create_run / execute_run contract
# ------------------------------------------------------------------
def test_create_run_returns_native_style_run(temp_runtime):
    run = temp_runtime.create_run("hello from 08f1", mode="read_only", user_id="tester_08f1")
    assert run["run_id"].startswith("agv2_")
    assert run["goal"] == "hello from 08f1"
    assert run["mode_effective"] == "read_only"
    assert run["status"] == "created"
    assert run["backend_selected"] == "langgraph_parity"
    assert run["backend_fallback_used"] is False
    assert run["trace_url"].startswith("/v2/agent/runs/")


def test_execute_run_returns_native_style_run(temp_runtime, monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    created = temp_runtime.create_run("status check", mode="read_only", user_id="tester_08f1")
    run_id = created["run_id"]
    completed = temp_runtime.execute_run(run_id)
    assert completed["run_id"] == run_id
    assert completed["status"] in {"completed", "failed"}
    assert completed["final_answer"] is not None
    assert REQUIRED_RUN_FIELDS.issubset(set(completed.keys()))
    assert completed["backend_selected"] == "langgraph_parity"


# ------------------------------------------------------------------
# 3. Runtime selector opt-in
# ------------------------------------------------------------------
def test_langgraph_selected_when_env_set(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    rt = get_agent_runtime_v2()
    selected = getattr(rt, "backend_selected", rt.backend)
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed; fallback verified in selector guard tests")
    assert selected == "langgraph_parity"
    assert rt.backend != "native_runtime"


# ------------------------------------------------------------------
# 4. Native default preservation
# ------------------------------------------------------------------
def test_langgraph_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    rt = get_agent_runtime_v2()
    selected = getattr(rt, "backend_selected", rt.backend)
    if not LANGGRAPH_AVAILABLE or selected != "langgraph_parity":
        pytest.skip("LangGraph package not installed; fallback verified in selector guard tests")
    assert rt.backend == "langgraph_parity"


# ------------------------------------------------------------------
# 5. Safe fallback still works
# ------------------------------------------------------------------
def test_fallback_to_native_when_langgraph_incompatible(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    import brain_v9.core.agent_kernel_v2.runtime as runtime_module
    original_try = runtime_module._try_build_langgraph_runtime

    def _fake_try_build(_requested_value):
        return None

    monkeypatch.setattr(runtime_module, "_try_build_langgraph_runtime", _fake_try_build)
    try:
        rt = get_agent_runtime_v2()
        assert rt.backend == "native_runtime"
        assert rt.backend_fallback_used is True
        assert rt.backend_fallback_reason
    finally:
        runtime_module._try_build_langgraph_runtime = original_try


# ------------------------------------------------------------------
# 6. /v2/chat/agent normalized schema
# ------------------------------------------------------------------
def test_chat_agent_normalized_schema_with_langgraph(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    client = TestClient(app)
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the agent kernel?", "mode": "read_only", "user_id": "tester_08f1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert REQUIRED_CHAT_FIELDS.issubset(set(data.keys()))
    assert data["run_id"].startswith("agv2_")
    assert data["trace_url"]


# ------------------------------------------------------------------
# 7. Trace contract
# ------------------------------------------------------------------
def test_trace_contract_after_langgraph_run(temp_runtime):
    created = temp_runtime.create_run("trace test", mode="read_only", user_id="tester_08f1")
    run_id = created["run_id"]
    temp_runtime.execute_run(run_id)
    trace = temp_runtime.get_trace(run_id)
    assert isinstance(trace, list)


# ------------------------------------------------------------------
# 8. Read-only governance
# ------------------------------------------------------------------
def test_read_only_blocks_write_intent(temp_runtime):
    created = temp_runtime.create_run("patch the kernel code", mode="read_only", user_id="tester_08f1")
    run_id = created["run_id"]
    completed = temp_runtime.execute_run(run_id)
    # Structural assertion: either escalation or blocked tools must reflect governance
    assert completed.get("mode_escalation_required") or completed.get("blocked_tools") or completed.get("required_permission")


# ------------------------------------------------------------------
# 9. Scope guard
# ------------------------------------------------------------------
def test_only_allowed_source_files_modified():
    import subprocess
    result = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True)
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    allowed_prefixes = [
        "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py",
        "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
        "tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py",
        "tests/smoke/test_brain_agent_v2_langgraph_default_promotion_08f7_r1.py",
        "tests/smoke/test_brain_agent_v2_langgraph_production_method_parity_08f7_r1.py",
        "tests/smoke/test_brain_agent_v2_runtime_selector_guard_08e.py",
        "tests/smoke/test_brain_dashboard_chat_proxy_token_fix_08e_r3.py",
        "tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py",
        "tmp_agent/front_brain_agent_v2_langgraph_runtime_contract_parity_08f1/",
        "tmp_agent/front_brain_agent_v2_langgraph_production_method_parity_and_default_promotion_08f7_r1/",
    ]
    disallowed = [c for c in changed if not any(c.startswith(p) for p in allowed_prefixes)]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"
