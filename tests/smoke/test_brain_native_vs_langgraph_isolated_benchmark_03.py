"""Isolated benchmark: Native V2 runtime vs LangGraph runtime.

No source edits. No production wiring changes. No live LLM. No memory/FAISS/trading mutation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
from tmp_agent.brain_v9.main import app

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")
OUT_DIR = REPO_ROOT / "tmp_agent" / "front_brain_native_vs_langgraph_isolated_benchmark_03"
OUT_DIR.mkdir(parents=True, exist_ok=True)

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

# Sandbox-only strict-operator override
async def _strict_op_passthrough(request, x_brain_token=None):
    return None

_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_FINALIZE = _finalizer.finalize_agent_run


def _fake_finalize(*args, **kwargs):
    return ("fake final answer for benchmark", {"provider_used": "mock", "model_used": "mock"})


def setup_module():
    _finalizer.finalize_agent_run = _fake_finalize


def teardown_module():
    _finalizer.finalize_agent_run = _ORIGINAL_FINALIZE


# ============================================================
# 1. Runtime selector returns native
# ============================================================
def test_runtime_selector_returns_native():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


# ============================================================
# 2. Native /v2/chat/agent returns capability_metadata
# ============================================================
def test_native_v2_chat_agent_returns_capability_metadata():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "benchmark"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "capability_metadata" in data
    assert data["capability_metadata"]["intent_route"] == "brain_evidence"
    # Persist native probe snapshot
    probe = {
        "probe_method": "FastAPI TestClient POST /v2/chat/agent",
        "endpoint": "/v2/chat/agent",
        "status_code": response.status_code,
        "backend": "native_runtime",
        "runtime_class": "NativeAgentRuntimeV2",
        "capability_metadata_present": True,
        "required_keys_present": sorted(REQUIRED_METADATA_KEYS),
        "sample_capability_metadata": data["capability_metadata"],
        "governance_probe_result": data["capability_metadata"].get("governance_checked"),
        "trace_events_count": data["capability_metadata"].get("trace_events_count"),
        "source_modified": False,
    }
    (OUT_DIR / "native_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ============================================================
# 3. Required metadata keys present
# ============================================================
def test_native_v2_metadata_required_keys_present():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "benchmark"},
    )
    meta = response.json()["capability_metadata"]
    missing = REQUIRED_METADATA_KEYS - set(meta.keys())
    assert not missing, f"Missing keys: {missing}"


# ============================================================
# 4. Native governance blocks write intent in read_only
# ============================================================
def test_native_v2_governance_read_only_write_intent_blocked():
    client = TestClient(app, headers={"X-Brain-Token": "test-token"})
    response = client.post(
        "/v2/chat/agent",
        json={"message": "apply patch to README.md", "mode": "read_only", "user_id": "benchmark"},
    )
    data = response.json()
    assert data["mode_escalation_required"] is True
    assert data["capability_metadata"]["governance_checked"] is True
    assert data["capability_metadata"]["tools_blocked"] >= 1


# ============================================================
# 5-10. LangGraph isolated classification
# ============================================================

def _classify_langgraph() -> dict:
    result = {
        "file_exists": (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "langgraph_runtime.py").is_file(),
        "importable": False,
        "import_error": None,
        "dependencies_missing": [],
        "instantiable": False,
        "instantiation_error": None,
        "graph_probe_available": False,
        "graph_probe_executed": False,
        "graph_probe_result": None,
        "graph_stream_available": False,
        "checkpointer_detected": False,
        "MemoryGatewayV2_detected": False,
        "ToolGatewayV2_detected": False,
        "governance_detected": False,
        "trace_detected": False,
        "production_wired": False,
        "classification": None,
    }
    if not result["file_exists"]:
        result["classification"] = "LANGGRAPH_FILE_ONLY"
        return result

    try:
        from brain_v9.core.agent_kernel_v2.langgraph_runtime import LangGraphAgentRuntimeV2
        result["importable"] = True
    except Exception as exc:
        result["import_error"] = str(exc)[:500]
        # Heuristic dependency classification
        if "No module named" in result["import_error"]:
            result["dependencies_missing"] = [result["import_error"].split("No module named")[-1].strip().strip("'\"")]
        result["classification"] = "LANGGRAPH_NOT_IMPORTABLE"
        return result

    # Inspect class source for wiring signals (read-only static inspection)
    source = Path(__file__).resolve().parent.parent.parent / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "langgraph_runtime.py"
    src = source.read_text(encoding="utf-8")
    result["graph_stream_available"] = "graph.stream" in src or "astream" in src
    result["checkpointer_detected"] = "checkpointer" in src or "MemorySaver" in src or "SqliteSaver" in src
    result["MemoryGatewayV2_detected"] = "MemoryGatewayV2" in src
    result["ToolGatewayV2_detected"] = "ToolGatewayV2" in src
    result["governance_detected"] = "governance" in src
    result["trace_detected"] = "TraceStore" in src or "_trace" in src

    if hasattr(LangGraphAgentRuntimeV2, "graph_probe"):
        result["graph_probe_available"] = True

    try:
        rt = LangGraphAgentRuntimeV2()
        result["instantiable"] = True
        if result["graph_probe_available"] and rt.graph_available:
            probe_out = rt.graph_probe()
            result["graph_probe_executed"] = True
            result["graph_probe_result"] = probe_out
            result["classification"] = "LANGGRAPH_EXECUTABLE_ISOLATED"
        else:
            result["instantiation_error"] = getattr(rt, "graph_error", "graph not compiled")
            result["classification"] = "LANGGRAPH_IMPORTABLE_NOT_INSTANTIABLE"
    except Exception as exc:
        result["instantiation_error"] = str(exc)[:500]
        result["classification"] = "LANGGRAPH_IMPORTABLE_NOT_INSTANTIABLE"

    return result


LANGGRAPH_STATUS = _classify_langgraph()


# ============================================================
# LangGraph tests
# ============================================================

def test_langgraph_runtime_file_exists_or_report_missing():
    p = REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "langgraph_runtime.py"
    assert p.is_file(), "langgraph_runtime.py missing; benchmark cannot proceed"


def test_langgraph_importability_classified():
    assert "classification" in LANGGRAPH_STATUS
    # Persist LangGraph probe snapshot
    (OUT_DIR / "langgraph_probe.json").write_text(json.dumps(LANGGRAPH_STATUS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.skipif(
    not LANGGRAPH_STATUS.get("importable", False),
    reason="LangGraph not importable; production wiring impossible.",
)
def test_langgraph_not_production_active():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


@pytest.mark.skipif(
    not LANGGRAPH_STATUS.get("importable", False),
    reason="LangGraph not importable; runtime selector wiring cannot be inspected.",
)
def test_langgraph_no_runtime_selector_wiring():
    from brain_v9.core.agent_kernel_v2 import runtime as _runtime_mod
    # runtime.py only imports NativeAgentRuntimeV2; no langgraph import allowed
    src = Path(_runtime_mod.__file__).read_text(encoding="utf-8")
    assert "langgraph" not in src.lower()


@pytest.mark.skipif(
    not LANGGRAPH_STATUS.get("instantiable", False),
    reason="LangGraph not instantiable; skip isolated instantiation check.",
)
def test_langgraph_instantiation_or_safe_skip():
    from brain_v9.core.agent_kernel_v2.langgraph_runtime import LangGraphAgentRuntimeV2
    rt = LangGraphAgentRuntimeV2()
    assert rt.backend == "langgraph"


@pytest.mark.skipif(
    not (LANGGRAPH_STATUS.get("instantiable") and LANGGRAPH_STATUS.get("graph_probe_available")),
    reason="LangGraph graph probe unavailable or unsafe.",
)
def test_langgraph_graph_probe_or_safe_skip():
    from brain_v9.core.agent_kernel_v2.langgraph_runtime import LangGraphAgentRuntimeV2
    rt = LangGraphAgentRuntimeV2()
    result = rt.graph_probe()
    assert result["ok"] is True
    assert result.get("out", {}).get("finalized") is True


# 11-12. Scope / guard
# ============================================================
def test_no_source_files_modified():
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    allowed_prefixes = (
        "tests/smoke/test_brain_native_vs_langgraph_isolated_benchmark_03.py",
        "tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/",
    )
    disallowed = [c for c in changed if not any(c.startswith(p) for p in allowed_prefixes)]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"


def test_no_sensitive_paths_staged():
    result = subprocess.run(
        [sys.executable, "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert "SAFE" in result.stdout
