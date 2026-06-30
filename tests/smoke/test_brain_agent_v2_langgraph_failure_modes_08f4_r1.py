"""Focused failure-mode hardening tests for LangGraph parity runtime (08F4-R1).

Validates BUG-08F4-03 timeout/circuit-breaker, BUG-08F4-01 malformed run state
rejection, BUG-08F4-02 auto write-intent escalation reflection, and the
existing default-preservation contract.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
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

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN_08F4")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for 08f4 failure mode test"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")

_ALLOWED_PREFIXES = [
    "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
    "tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py",
    "tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4_r1/",
]


@pytest.fixture
def temp_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        yield LangGraphParityRuntimeV2(run_root=tmp)


# ------------------------------------------------------------------
# BUG-08F4-03: timeout / circuit-breaker
# ------------------------------------------------------------------
class _StallingGraph:
    def invoke(self, initial_state):
        time.sleep(600)
        return {"status": "completed"}


def test_execute_run_returns_failed_state_on_timeout(temp_runtime, monkeypatch):
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed")
    # Force an extremely short timeout and a graph that never returns.
    temp_runtime.execute_timeout_seconds = 0.05
    temp_runtime._graph = _StallingGraph()
    created = temp_runtime.create_run("timeout probe", mode="read_only", user_id="tester_08f4")
    run_id = created["run_id"]
    start = time.monotonic()
    completed = temp_runtime.execute_run(run_id)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"Timeout did not bound execution: elapsed={elapsed:.2f}s"
    assert completed["status"] == "failed"
    assert completed["error"] == "timeout"
    assert "exceeded the internal timeout" in completed["final_answer"]
    assert completed["backend_selected"] == "langgraph_parity"
    persisted = temp_runtime.get_run(run_id)
    assert persisted["status"] == "failed"


def test_run_method_returns_failed_state_on_timeout(temp_runtime, monkeypatch):
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed")
    temp_runtime.execute_timeout_seconds = 0.05
    temp_runtime._graph = _StallingGraph()
    result = temp_runtime.run("timeout probe direct", mode="read_only", user_id="tester_08f4")
    assert result["status"] == "failed"
    assert result["error"] == "timeout"


# ------------------------------------------------------------------
# BUG-08F4-01: malformed run state handling
# ------------------------------------------------------------------
def test_execute_run_rejects_missing_required_fields(temp_runtime):
    run_id = "agv2_malformed_08f4_missing"
    temp_runtime._run_dir(run_id)
    run_dir = temp_runtime._run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id, "mode": "read_only"}, ensure_ascii=False, indent=2), encoding="utf-8")
    completed = temp_runtime.execute_run(run_id)
    assert completed["status"] == "failed"
    assert completed["error"] == "malformed_run_state"
    assert completed["backend_selected"] == "langgraph_parity"


def test_execute_run_rejects_invalid_json_run_state(temp_runtime):
    run_id = "agv2_malformed_08f4_json"
    run_dir = temp_runtime._run_dir(run_id)
    (run_dir / "run.json").write_text("{not valid json", encoding="utf-8")
    completed = temp_runtime.execute_run(run_id)
    assert completed["status"] == "failed"
    assert completed["error"] == "malformed_run_state"


def test_get_run_returns_failed_stub_for_malformed_state(temp_runtime):
    run_id = "agv2_malformed_08f4_get"
    run_dir = temp_runtime._run_dir(run_id)
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = temp_runtime.get_run(run_id)
    assert loaded is not None
    assert loaded["status"] == "failed"
    assert loaded["error"] == "malformed_run_state"


# ------------------------------------------------------------------
# BUG-08F4-02: auto write-intent escalation reflection
# ------------------------------------------------------------------
def test_auto_mode_write_intent_escalates_to_approval_required(temp_runtime):
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed")
    created = temp_runtime.create_run("patch the kernel code", mode="auto", user_id="tester_08f4")
    completed = temp_runtime.execute_run(created["run_id"])
    assert completed["mode_requested"] == "auto"
    assert completed["mode_effective"] == "approval_required"
    assert completed.get("mode_escalation_required") or completed.get("approval_required")
    assert "write" in completed["final_answer"].lower() or completed.get("required_permission") == "build"


def test_auto_mode_harmless_query_does_not_escalate(temp_runtime):
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed")
    created = temp_runtime.create_run("What is the agent kernel status?", mode="auto", user_id="tester_08f4")
    completed = temp_runtime.execute_run(created["run_id"])
    assert completed["mode_requested"] == "auto"
    assert completed["mode_effective"] != "approval_required"


# ------------------------------------------------------------------
# Default and opt-in preservation
# ------------------------------------------------------------------
def test_native_default_unchanged(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"


def test_langgraph_opt_in_still_selects_langgraph(monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    rt = get_agent_runtime_v2()
    selected = getattr(rt, "backend_selected", rt.backend)
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph package not installed")
    assert selected == "langgraph_parity"


# ------------------------------------------------------------------
# Scope guard
# ------------------------------------------------------------------
def test_only_allowed_source_files_modified():
    import subprocess

    result = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True)
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    disallowed = [c for c in changed if not any(c.startswith(p) for p in _ALLOWED_PREFIXES)]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"
