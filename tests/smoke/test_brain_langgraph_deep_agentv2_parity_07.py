"""Deep Agent V2 parity smoke tests for LangGraphParityRuntimeV2.

No production wiring changes. No default runtime change. No /v2/chat/agent route change.
Uses tmp_path for all parity runtime persistence. Avoids live LLM in tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9.core.agent_kernel_v2 import intent_adapter as intent_adapter_module
from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")
OUT_DIR = REPO_ROOT / "tmp_agent" / "front_brain_langgraph_deep_agentv2_parity_07"
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

DEEP_PARITY_KEYS = {
    "intent_route_source",
    "intent_route_fallback_used",
    "evidence_source",
    "evidence_fallback_used",
    "planner_source",
    "planner_fallback_used",
    "context_assembler_used",
    "context_assembler_skip_reason",
    "native_helpers_used",
    "native_helper_errors",
    "deep_parity_runtime",
    "finalizer_source",
    "native_helper_parity_score",
}


def _runtime(tmp_path):
    return LangGraphParityRuntimeV2(run_root=str(tmp_path / "parity_runs"))


@pytest.fixture(autouse=True)
def _disable_llm_classifier(monkeypatch):
    """Ensure evidence-source selection uses deterministic router, not live LLM."""
    monkeypatch.setattr(intent_adapter_module, "BRAIN_USE_LLM_INTENT_CLASSIFIER", False)


# ============================================================
# 1. Import
# ============================================================
def test_deep_parity_runtime_imports():
    assert LangGraphParityRuntimeV2 is not None
    assert hasattr(LangGraphParityRuntimeV2, "backend")
    assert LangGraphParityRuntimeV2.backend == "langgraph_parity"


# ============================================================
# 2. Instantiation isolated
# ============================================================
def test_deep_parity_instantiates_tmp_path(tmp_path):
    rt = _runtime(tmp_path)
    assert rt is not None
    assert rt.run_root == tmp_path / "parity_runs"
    assert rt.intent_adapter is not None


# ============================================================
# 3. Runtime selector still native
# ============================================================
def test_runtime_selector_still_native():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


# ============================================================
# 4. Production route still native
# ============================================================
def test_production_route_still_native():
    api_src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "api_adapter.py").read_text(encoding="utf-8")
    rt_src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "runtime.py").read_text(encoding="utf-8")
    assert "langgraph_parity_runtime" not in api_src
    assert "langgraph_parity_runtime" not in rt_src


# ============================================================
# 5. AgentV2IntentAdapter used for routing
# ============================================================
def test_deep_parity_uses_agentv2_intent_adapter(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "direct_assistant"
    assert out.get("intent_route_source") == "AgentV2IntentAdapter.select_route"
    assert out.get("intent_route_fallback_used") is False


# ============================================================
# 6. Real evidence sources used
# ============================================================
def test_deep_parity_uses_real_evidence_sources(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "brain_evidence"
    assert out.get("evidence_source") == "AgentV2IntentAdapter.get_evidence_sources"
    assert out.get("evidence_fallback_used") is False
    assert out["capability_metadata"]["evidence_sources_count"] >= 1


# ============================================================
# 7. planner.build_plan used
# ============================================================
def test_deep_parity_uses_planner_build_plan(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out.get("planner_source") == "planner.build_plan"
    assert out.get("planner_fallback_used") is False
    assert out["capability_metadata"]["planner_used"] is True


# ============================================================
# 8. Context assembler used or explicitly skipped
# ============================================================
def test_deep_parity_context_assembler_used_or_explicitly_skipped(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    meta = out.get("capability_metadata", {})
    assert "context_assembler_used" in meta
    assert "context_assembler_skip_reason" in meta
    assert meta["context_assembler_used"] is True or meta["context_assembler_skip_reason"] is not None


# ============================================================
# 9. Direct assistant path
# ============================================================
def test_deep_parity_direct_assistant_path(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "direct_assistant"
    assert out["classification"] == "direct_assistant"
    assert out["capability_metadata"]["planner_used"] is False
    assert out["final_answer"] is not None


# ============================================================
# 10. Brain evidence path
# ============================================================
def test_deep_parity_brain_evidence_path(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["intent_route"] == "brain_evidence"
    assert out["capability_metadata"]["evidence_routed"] is True
    assert out["capability_metadata"]["tools_considered"] >= 1


# ============================================================
# 11. Tool-specific request path
# ============================================================
def test_deep_parity_tool_specific_request_path(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("Check repo status and inspect the agent runtime files without modifying anything.", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    # Intent adapter should route this to brain_evidence (matching native V2).
    assert out["intent_route"] == "brain_evidence"
    assert out.get("intent_route_source") == "AgentV2IntentAdapter.select_route"


# ============================================================
# 12. Write intent blocked in read_only
# ============================================================
def test_deep_parity_write_intent_blocked_in_read_only(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("apply patch to README.md", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["mode_escalation_required"] is True
    assert out["capability_metadata"]["governance_checked"] is True
    assert out["capability_metadata"]["tools_blocked"] >= 1
    assert "blocked" in out["final_answer"].lower() or "governance" in out["final_answer"].lower()


# ============================================================
# 13. Protected governance write blocked or escalated
# ============================================================
def test_deep_parity_protected_governance_write_blocked_or_escalated(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("Modify tmp_agent/brain_v9/core/agent_kernel_v2/governance.py to bypass approval.", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out["ok"] is True
    assert out["mode_escalation_required"] is True or out["capability_metadata"]["tools_blocked"] >= 1


# ============================================================
# 14. Capability metadata deep keys
# ============================================================
def test_deep_parity_capability_metadata_deep_keys(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    meta = out.get("capability_metadata", {})
    missing_required = REQUIRED_CAPABILITY_KEYS - set(meta.keys())
    missing_deep = DEEP_PARITY_KEYS - set(meta.keys())
    assert not missing_required, f"Missing required keys: {missing_required}"
    assert not missing_deep, f"Missing deep parity keys: {missing_deep}"
    assert meta["deep_parity_runtime"] is True


# ============================================================
# 15. Trace per node
# ============================================================
def test_deep_parity_trace_per_node(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    trace = rt.get_trace(out["run_id"])
    event_types = {e["event_type"] for e in trace}
    assert "start_node" in event_types
    assert "intent_node" in event_types
    assert "finalizer_node" in event_types
    assert "end_node" in event_types
    assert len(trace) >= 10


# ============================================================
# 16. Checkpoint only in tmp dir
# ============================================================
def test_deep_parity_checkpoint_tmp_dir_only(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    checkpoint = rt.get_checkpoint(out["run_id"])
    assert checkpoint is not None
    cp_path = rt.run_root / out["run_id"] / "checkpoint.json"
    assert cp_path.exists()
    assert str(cp_path).startswith(str(tmp_path))


# ============================================================
# 17. Memory read-only or skip recorded
# ============================================================
def test_deep_parity_memory_read_only_or_recorded_skip(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    mem_result = out.get("memory_retrieval_result", {})
    # Either attempted with no write, or explicitly skipped.
    if mem_result.get("skipped"):
        assert out["capability_metadata"]["retrieval_skipped"] is True
    else:
        for tr in out.get("tool_results", []):
            result = tr.get("result", {})
            if isinstance(result, dict):
                assert result.get("write_performed") in (None, False)


# ============================================================
# 18. Tool gateway used or skip recorded
# ============================================================
def test_deep_parity_tool_gateway_used_or_skip_recorded(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert out.get("tool_gateway_parity_improved") is True
    tool_results = out.get("tool_results", [])
    trace = rt.get_trace(out["run_id"])
    assert tool_results or any("tool_execution" in e["event_type"] for e in trace)


# ============================================================
# 19. Evaluator result present
# ============================================================
def test_deep_parity_evaluator_result_present(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("hi", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    ev = out.get("evaluator_result", {})
    assert "answered_user_intent" in ev
    assert "governance_compliant" in ev
    assert "native_helper_parity_score" in ev


# ============================================================
# 20. No runtime source wiring changed
# ============================================================
def test_deep_parity_no_runtime_source_wiring_changed():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"


# ============================================================
# 21. No memory/FAISS/trading/env touch
# ============================================================
def test_deep_parity_no_memory_faiss_trading_env_touch(tmp_path):
    rt = _runtime(tmp_path)
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    assert str(rt.run_root).startswith(str(tmp_path))
    for tr in out.get("tool_results", []):
        result = tr.get("result", {})
        if isinstance(result, dict):
            assert result.get("write_performed") in (None, False)


# ============================================================
# 22. Sensitive paths guard
# ============================================================
def test_deep_parity_no_sensitive_paths_staged():
    result = __import__("subprocess").run(
        [sys.executable, "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert "SAFE" in result.stdout


# ============================================================
# 23. Persist deep parity probe
# ============================================================
def test_deep_parity_probe_generation(tmp_path):
    rt = _runtime(tmp_path)
    scenarios = {
        "direct_assistant": "hi",
        "brain_evidence": "What is the status of the brain gate approve endpoint?",
        "tool_specific_request": "Check repo status and inspect the agent runtime files without modifying anything.",
        "write_intent_blocked": "apply patch to README.md",
        "protected_governance_write": "Modify tmp_agent/brain_v9/core/agent_kernel_v2/governance.py to bypass approval.",
        "mixed_reasoning": "Compare the current native runtime and the langgraph parity prototype and tell me what is missing.",
    }
    probe = {"scenarios": {}}
    for name, message in scenarios.items():
        out = rt.run(message, "read_only", "test")
        if not rt.graph_available:
            pytest.skip("LangGraph not available")
        probe["scenarios"][name] = {
            "intent_route": out.get("intent_route"),
            "classification": out.get("classification"),
            "final_answer_present": bool(out.get("final_answer")),
            "capability_metadata": out.get("capability_metadata"),
            "native_helpers_used": out.get("native_helpers_used", []),
            "native_helper_errors": out.get("native_helper_errors", []),
            "planner_source": out.get("planner_source"),
            "evidence_source": out.get("evidence_source"),
            "intent_route_source": out.get("intent_route_source"),
            "context_assembler_used": out.get("context_assembler_used"),
            "tools_considered": out["capability_metadata"].get("tools_considered"),
            "tools_executed": out["capability_metadata"].get("tools_executed"),
            "tools_blocked": out["capability_metadata"].get("tools_blocked"),
            "trace_events_count": out["capability_metadata"].get("trace_events_count"),
            "checkpoint_present": rt.get_checkpoint(out["run_id"]) is not None,
        }
    (OUT_DIR / "deep_parity_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert True
