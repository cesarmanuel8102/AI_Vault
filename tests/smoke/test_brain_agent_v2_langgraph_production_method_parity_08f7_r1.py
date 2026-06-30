
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2


def _runtime():
    tmp = tempfile.TemporaryDirectory()
    return tmp, LangGraphParityRuntimeV2(run_root=tmp.name)


def test_langgraph_has_production_methods_callable():
    tmp, rt = _runtime()
    try:
        for method in ("create_run", "plan_run", "pause_run", "resume_run", "cancel_run", "execute_run", "list_runs", "get_run", "get_trace"):
            assert callable(getattr(rt, method, None)), method
    finally:
        tmp.cleanup()


def test_plan_pause_resume_cancel_persist_and_trace():
    tmp, rt = _runtime()
    try:
        run = rt.create_run("inspect repo status", mode="read_only", user_id="08f7_r1")
        run_id = run["run_id"]
        planned = rt.plan_run(run_id)
        assert planned["status"] == "planned"
        assert isinstance(planned.get("plan"), list)
        assert planned.get("planner_used") is True
        paused = rt.pause_run(run_id)
        assert paused["status"] == "paused"
        resumed = rt.resume_run(run_id)
        assert resumed["status"] == "resumed"
        cancelled = rt.cancel_run(run_id)
        assert cancelled["status"] == "cancelled"
        persisted = rt.get_run(run_id)
        assert persisted["status"] == "cancelled"
        events = [e.get("event_type") for e in rt.get_trace(run_id)]
        for event in ("run_created", "plan_created", "run_paused", "run_resumed", "run_cancelled"):
            assert event in events
    finally:
        tmp.cleanup()


def test_invalid_transition_fails_safely_without_terminal_corruption():
    tmp, rt = _runtime()
    try:
        run = rt.create_run("terminal transition probe", mode="read_only", user_id="08f7_r1")
        run_id = run["run_id"]
        cancelled = rt.cancel_run(run_id)
        assert cancelled["status"] == "cancelled"
        after = rt.resume_run(run_id)
        assert after["status"] == "cancelled"
        assert "cannot transition terminal run" in after.get("error", "")
        assert rt.get_run(run_id)["status"] == "cancelled"
    finally:
        tmp.cleanup()


def test_read_only_plan_does_not_write_memory_or_faiss(tmp_path):
    tmp, rt = _runtime()
    try:
        before = _memory_faiss_snapshot()
        run = rt.create_run("patch the kernel code", mode="read_only", user_id="08f7_r1")
        planned = rt.plan_run(run["run_id"])
        after = _memory_faiss_snapshot()
        assert before == after
        assert planned.get("mode_escalation_required") is True
        assert planned.get("approval_required") is True
        assert planned.get("required_permission") == "build"
        assert planned.get("status") == "planned"
    finally:
        tmp.cleanup()


def test_timeout_circuit_breaker_builds_safe_failed_state_without_writes():
    tmp, rt = _runtime()
    try:
        rt.execute_timeout_seconds = 0.05
        result = rt._build_timeout_state({"message": "timeout", "mode_requested": "read_only", "user_id": "08f7_r1"})
        assert result["status"] == "failed"
        assert result["error"] == "timeout"
        assert result["backend_selected"] == "langgraph_parity"
        assert result["tool_results"] == []
        assert result["memory_hits"] == []
    finally:
        tmp.cleanup()


def _memory_faiss_snapshot():
    files = [
        Path("memory/semantic/semantic_memory.jsonl"),
        Path("memory/semantic/semantic_memory_faiss.index"),
        Path("memory/semantic/semantic_memory_faiss_ids.json"),
    ]
    out = {}
    for path in files:
        if path.exists():
            stat = path.stat()
            out[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        else:
            out[str(path)] = None
    return out
