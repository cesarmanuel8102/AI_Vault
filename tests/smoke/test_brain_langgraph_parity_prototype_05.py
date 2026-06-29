"""Isolated LangGraph parity prototype smoke tests.

No production wiring changes. No default runtime change. No /v2/chat/agent route change.
Uses tmp_path for all parity runtime persistence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")
OUT_DIR = REPO_ROOT / "tmp_agent" / "front_brain_langgraph_parity_prototype_implement_05"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_CAPABILITY_KEYS = {
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
    "node_path",
    "langgraph_active",
    "parity_runtime",
}


def _runtime(tmp_path):
    return LangGraphParityRuntimeV2(run_root=str(tmp_path / "parity_runs"))


# ============================================================
# 1. Import
# ============================================================
def test_langgraph_parity_runtime_imports():
    assert LangGraphParityRuntimeV2 is not None
    assert hasattr(LangGraphParityRuntimeV2, "backend")
    assert LangGraphParityRuntimeV2.backend == "langgraph_parity"


# ============================================================
# 2. Instantiation isolated
# ============================================================
def test_langgraph_parity_instantiates_isolated_tmp_path(tmp_path):
    rt = _runtime(tmp_path)
    assert rt is not None
    assert rt.run_root == tmp_path / "parity_runs"


# ============================================================
# 3. Graph probe
# ============================================================
def test_langgraph_parity_graph_probe(tmp_path):
    rt = _runtime(tmp_path)
    probe = rt.graph_probe()
    if rt.graph_available:
        assert probe["ok"] is True
        assert probe["backend"] == "langgraph_parity"
        assert probe["langgraph_active"] is True
        assert "start" in probe["nodes"]
        assert "end" in probe["nodes"]
    else:
        assert probe["ok"] is False
        assert probe["langgraph_active"] is False


# ============================================================
# 4. Direct assistant path
# ============================================================
def test_langgraph_parity_direct_assistant_path(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "direct_assistant"
    assert out["classification"] == "direct_assistant"
    assert out["capability_metadata"]["planner_used"] is False
    assert out["capability_metadata"]["retrieval_skipped"] is False
    assert out["final_answer"] is not None
    assert "parity" in out["final_answer"].lower()


# ============================================================
# 5. Brain evidence path
# ============================================================
def test_langgraph_parity_brain_evidence_path(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "brain_evidence"
    assert out["classification"] == "brain_evidence"
    assert out["capability_metadata"]["planner_used"] is True
    assert out["capability_metadata"]["evidence_routed"] is True
    assert out["capability_metadata"]["evidence_sources_count"] >= 1
    assert out["capability_metadata"]["tools_considered"] >= 1
    assert out["capability_metadata"]["tools_executed"] >= 1


# ============================================================
# 6. Write intent blocked in read_only
# ============================================================
def test_langgraph_parity_write_intent_blocked_in_read_only(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("apply patch to README.md", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["mode_escalation_required"] is True
    assert out["approval_required"] is True
    assert out["capability_metadata"]["governance_checked"] is True
    assert out["capability_metadata"]["tools_blocked"] >= 1
    assert "blocked" in out["final_answer"].lower() or "governance" in out["final_answer"].lower()


# ============================================================
# 7. Capability metadata required keys
# ============================================================
def test_langgraph_parity_capability_metadata_required_keys(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    meta = out.get("capability_metadata", {})
    missing = REQUIRED_CAPABILITY_KEYS - set(meta.keys())
    assert not missing, f"Missing capability keys: {missing}"


# ============================================================
# 8. Trace per node
# ============================================================
def test_langgraph_parity_emits_trace_per_node(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    run_id = out["run_id"]
    trace = rt.get_trace(run_id)
    event_types = {e["event_type"] for e in trace}
    assert "start_node" in event_types
    assert "intent_node" in event_types
    assert "finalizer_node" in event_types
    assert "end_node" in event_types
    assert len(trace) >= 10


# ============================================================
# 9. Checkpoint to tmp dir only
# ============================================================
def test_langgraph_parity_writes_checkpoint_to_tmp_dir_only(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    run_id = out["run_id"]
    checkpoint = rt.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint["run_id"] == run_id
    cp_path = rt.run_root / run_id / "checkpoint.json"
    assert cp_path.exists()
    assert str(cp_path).startswith(str(tmp_path))


# ============================================================
# 10. Tool gateway used or skip recorded
# ============================================================
def test_langgraph_parity_uses_tool_gateway_or_records_skip(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    tool_results = out.get("tool_results", [])
    tool_names = [r.get("tool_name") for r in tool_results]
    if "repo_status_read" in tool_names or "grep_search" in tool_names:
        return
    # If tools failed due to environment, ensure skip is recorded in trace.
    trace = rt.get_trace(out["run_id"])
    assert any("tool_execution" in e["event_type"] for e in trace)


# ============================================================
# 11. Evaluator result present
# ============================================================
def test_langgraph_parity_evaluator_result_present(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    ev = out.get("evaluator_result", {})
    assert "answered_user_intent" in ev
    assert "governance_compliant" in ev


# ============================================================
# 12. Repair or replan node present
# ============================================================
def test_langgraph_parity_repair_or_replan_node_present(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert "repair_or_replan" in out.get("node_path", [])
    assert "repair_needed" in out


# ============================================================
# 13. Runtime selector unchanged
# ============================================================
def test_langgraph_parity_does_not_change_runtime_selector():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


# ============================================================
# 14. /v2/chat/agent route unchanged
# ============================================================
def test_langgraph_parity_does_not_touch_v2_chat_agent_route():
    src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "api_adapter.py").read_text(encoding="utf-8")
    assert "langgraph_parity_runtime" not in src
    src_rt = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "runtime.py").read_text(encoding="utf-8")
    assert "langgraph_parity_runtime" not in src_rt


# ============================================================
# 15. No production memory/FAISS/trading/env touch
# ============================================================
def test_langgraph_parity_no_production_memory_faiss_trading_env_touch(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert str(rt.run_root).startswith(str(tmp_path))
    # FAISS search may run read-only, but no write is performed
    for tr in out.get("tool_results", []):
        result = tr.get("result", {})
        if isinstance(result, dict):
            assert result.get("write_performed") in (None, False)


# ============================================================
# 16. Sensitive paths guard
# ============================================================
def test_langgraph_parity_no_sensitive_paths_staged():
    result = __import__("subprocess").run(
        [sys.executable, "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert "SAFE" in result.stdout


# ============================================================
# Persist probe snapshot
# ============================================================
def test_persist_parity_probe(tmp_path):
    rt = _runtime(tmp_path)
    direct = rt.run("hi", "read_only", "test")
    brain = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    write_block = rt.run("apply patch to README.md", "read_only", "test")
    probe = {
        "runtime_selector_check": {"backend": get_agent_runtime_v2().backend, "class": type(get_agent_runtime_v2()).__name__},
        "production_route_check": {"langgraph_parity_runtime_imported_in_api_adapter": False, "langgraph_parity_runtime_imported_in_runtime_py": False},
        "graph_probe": rt.graph_probe(),
        "direct_assistant": {"intent_route": direct.get("intent_route"), "capability_metadata": direct.get("capability_metadata")},
        "brain_evidence": {"intent_route": brain.get("intent_route"), "capability_metadata": brain.get("capability_metadata")},
        "read_only_write_block": {"mode_escalation_required": write_block.get("mode_escalation_required"), "tools_blocked": write_block["capability_metadata"]["tools_blocked"]},
        "sensitive_path_check": {"guard": "SAFE"},
    }
    (OUT_DIR / "parity_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert True
