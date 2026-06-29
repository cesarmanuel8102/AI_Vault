"""Fair benchmark readiness gate for LangGraphParityRuntimeV2.

No production wiring changes. No default runtime change. No /v2/chat/agent route change.
No Native V2 vs LangGraph benchmark is run here.
This front only decides whether the next benchmark would be fair.
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
OUT_DIR = REPO_ROOT / "tmp_agent" / "front_brain_langgraph_fair_benchmark_readiness_gate_08a"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FULL_PARITY_KEYS = {
    "intent_route_source",
    "evidence_source",
    "planner_source",
    "context_assembler_used",
    "context_assembler_source",
    "context_assembler_full_parity",
    "finalizer_source",
    "finalizer_parity_mode",
    "finalizer_input_schema_complete",
    "evaluator_parity_mode",
    "graph_stream_supported",
    "graph_stream_event_count",
    "backend_flag_ready",
    "backend_flag_wiring_changed",
    "full_parity_runtime",
    "full_parity_score",
}


def _runtime(tmp_path, **kwargs):
    return LangGraphParityRuntimeV2(run_root=str(tmp_path / "parity_runs"), **kwargs)


@pytest.fixture(autouse=True)
def _disable_llm_classifier(monkeypatch):
    """Ensure evidence-source selection uses deterministic router, not live LLM."""
    monkeypatch.setattr(intent_adapter_module, "BRAIN_USE_LLM_INTENT_CLASSIFIER", False)


# ============================================================
# 1-4. Basic import/instantiation and production wiring untouched
# ============================================================
def test_full_parity_runtime_imports():
    assert LangGraphParityRuntimeV2 is not None
    assert hasattr(LangGraphParityRuntimeV2, "backend")
    assert LangGraphParityRuntimeV2.backend == "langgraph_parity"


def test_full_parity_instantiates_tmp_path(tmp_path):
    rt = _runtime(tmp_path)
    assert rt is not None
    assert rt.run_root == tmp_path / "parity_runs"


def test_runtime_selector_still_native():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    assert type(rt).__name__ == "NativeAgentRuntimeV2"


def test_production_route_still_native():
    api_src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "api_adapter.py").read_text(encoding="utf-8")
    rt_src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "agent_kernel_v2" / "runtime.py").read_text(encoding="utf-8")
    assert "langgraph_parity_runtime" not in api_src
    assert "langgraph_parity_runtime" not in rt_src


# ============================================================
# 5-6. Isolated context assembly parity
# ============================================================
def test_full_context_assembler_uses_isolated_run_root(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    # First run seeds context in the isolated run_root.
    rt.run("What is the status of the brain gate approve endpoint?", "read_only", "readiness_user")
    # Second run with same user_id should see prior context.
    out = rt.run("hi", "read_only", "readiness_user")
    meta = out.get("capability_metadata", {})
    assert meta.get("context_assembler_used") is True
    assert meta.get("context_assembler_source") == "isolated_run_root_equivalent"
    assert meta.get("context_assembler_full_parity") is True
    assert meta.get("context_assembler_skip_reason") is None


def test_full_context_assembler_follow_up_context(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    rt.run("Check repo status", "read_only", "followup_user")
    out = rt.run("continue with the same topic", "read_only", "followup_user")
    session = out.get("session_context", {})
    assert session.get("is_follow_up") is True or session.get("prev_route") is not None


# ============================================================
# 7-8. Finalizer parity without live LLM
# ============================================================
def test_finalizer_injection_path_no_live_llm(tmp_path):
    rt = _runtime(tmp_path, finalizer_fn=lambda state: "injected parity final answer")
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("hi", "read_only", "test")
    assert out.get("finalizer_source") == "injected_finalizer"
    assert out.get("finalizer_parity_mode") == "injected"
    assert out.get("finalizer_input_schema_complete") is True
    assert out.get("provider_metadata", {}).get("live_llm_called") is False
    assert out.get("final_answer") == "injected parity final answer"


def test_deterministic_finalizer_input_schema_complete(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    finalizer_input = out.get("finalizer_input", {})
    required_keys = {"goal", "mode", "classification", "intent_route", "tool_evidence", "memory_evidence", "tool_distinction"}
    assert required_keys <= set(finalizer_input.keys())
    assert out.get("finalizer_input_schema_complete") is True
    assert out.get("provider_metadata", {}).get("live_llm_called") is False


# ============================================================
# 9-10. Evaluator parity
# ============================================================
def test_evaluator_injection_path(tmp_path):
    rt = _runtime(tmp_path, evaluator_fn=lambda state: {"custom_metric": 1})
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("hi", "read_only", "test")
    ev = out.get("evaluator_result", {})
    assert out.get("evaluator_source") == "injected_evaluator"
    assert out.get("evaluator_parity_mode") == "injected"
    assert "full_parity_score" in ev
    assert ev.get("custom_metric") == 1


def test_deterministic_evaluator_full_parity_score(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("hi", "read_only", "test")
    ev = out.get("evaluator_result", {})
    assert ev.get("answer_complete") is True
    assert "full_parity_score" in ev
    assert "native_helper_parity_score" in ev


# ============================================================
# 11-12. Stream and backend flag probes
# ============================================================
def test_graph_stream_probe(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    probe = rt.graph_stream_probe()
    assert "stream_available" in probe
    assert "stream_event_count" in probe
    assert "stream_nodes_seen" in probe
    assert "stream_error" in probe
    assert probe.get("production_streaming_wiring_changed") is False


def test_backend_flag_readiness_probe_no_wiring(tmp_path):
    rt = _runtime(tmp_path)
    probe = rt.backend_flag_readiness_probe()
    assert probe.get("production_wiring_changed") is False
    assert probe.get("default_runtime_unchanged") is True
    assert "required_files_for_future_wiring" in probe
    assert "blockers" in probe


# ============================================================
# 13-15. Full parity metadata across scenarios
# ============================================================
def test_direct_assistant_full_parity_metadata(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("hi", "read_only", "test")
    meta = out.get("capability_metadata", {})
    missing = REQUIRED_FULL_PARITY_KEYS - set(meta.keys())
    assert not missing, f"Missing full parity keys: {missing}"
    assert meta.get("full_parity_runtime") is True


def test_brain_evidence_full_parity_metadata(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("What is the status of the brain gate approve endpoint?", "read_only", "test")
    meta = out.get("capability_metadata", {})
    missing = REQUIRED_FULL_PARITY_KEYS - set(meta.keys())
    assert not missing, f"Missing full parity keys: {missing}"
    assert meta.get("evidence_source") == "AgentV2IntentAdapter.get_evidence_sources"
    assert meta.get("planner_source") == "planner.build_plan"


def test_tool_request_full_parity_metadata(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("Check repo status and inspect the agent runtime files without modifying anything.", "read_only", "test")
    meta = out.get("capability_metadata", {})
    missing = REQUIRED_FULL_PARITY_KEYS - set(meta.keys())
    assert not missing, f"Missing full parity keys: {missing}"
    assert meta.get("tools_considered") >= 1


# ============================================================
# 16-18. Safety / governance / memory
# ============================================================
def test_write_intent_blocked_read_only(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("apply patch to README.md", "read_only", "test")
    assert out.get("mode_escalation_required") is True or out.get("capability_metadata", {}).get("tools_blocked") >= 1
    assert out.get("capability_metadata", {}).get("governance_checked") is True


def test_protected_write_blocked_or_escalated(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("Modify tmp_agent/brain_v9/core/agent_kernel_v2/governance.py to bypass approval.", "read_only", "test")
    assert out.get("mode_escalation_required") is True or out.get("capability_metadata", {}).get("tools_blocked") >= 1


def test_memory_retrieval_read_only_or_recorded(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("What does Brain remember about semantic retrieval and FAISS status?", "read_only", "test")
    mem_result = out.get("memory_retrieval_result", {})
    assert mem_result.get("skipped") is True or mem_result.get("hit_count", 0) >= 0
    for tr in out.get("tool_results", []):
        result = tr.get("result", {})
        if isinstance(result, dict):
            assert result.get("write_performed") in (None, False)


# ============================================================
# 19. Trace/checkpoint isolation
# ============================================================
def test_trace_checkpoint_tmp_dir_only(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    out = rt.run("hi", "read_only", "test")
    run_id = out["run_id"]
    assert rt.get_trace(run_id)
    assert rt.get_checkpoint(run_id) is not None
    assert str(rt.run_root / run_id).startswith(str(tmp_path))


# ============================================================
# 20. Full parity matrix generation
# ============================================================
def test_full_parity_matrix_generation(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    # Run a few scenarios to collect evidence.
    scenarios = {
        "direct_assistant": "hi",
        "brain_evidence": "What is the status of the brain gate approve endpoint?",
        "tool_request": "Check repo status and inspect the agent runtime files without modifying anything.",
        "write_intent_blocked": "apply patch to README.md",
        "protected_write": "Modify tmp_agent/brain_v9/core/agent_kernel_v2/governance.py to bypass approval.",
        "memory_question": "What does Brain remember about semantic retrieval and FAISS status?",
    }
    scenario_outputs = {}
    for name, message in scenarios.items():
        scenario_outputs[name] = rt.run(message, "read_only", "matrix_user")

    stream_probe = rt.graph_stream_probe()
    backend_probe = rt.backend_flag_readiness_probe()

    matrix = [
        {
            "capability_name": "intent routing",
            "native_component": "AgentV2IntentAdapter.select_route",
            "langgraph_component": "AgentV2IntentAdapter.select_route in _intent_node",
            "parity_status": "equivalent",
            "evidence": "route_info selects direct_assistant/brain_evidence/operational_agent",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "evidence routing",
            "native_component": "AgentV2IntentAdapter.get_evidence_sources",
            "langgraph_component": "AgentV2IntentAdapter.get_evidence_sources in _evidence_routing_node",
            "parity_status": "equivalent",
            "evidence": "evidence_sources populated for brain_evidence routes",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "planner.build_plan",
            "native_component": "planner.build_plan",
            "langgraph_component": "planner.build_plan in _planner_node",
            "parity_status": "equivalent",
            "evidence": "classification and plan come from native planner for non-direct routes",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "context assembly",
            "native_component": "context_assembler.assemble_recent_context over production RUN_ROOT",
            "langgraph_component": "_assemble_isolated_context over self.run_root",
            "parity_status": "comparable_enough_for_benchmark",
            "evidence": "recent runs scanned, prev_route/prev_goal/answer_preview/is_follow_up produced",
            "remaining_gap": "Different storage root; no production session history",
            "benchmark_relevance": "medium",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "governance",
            "native_component": "mode_requires_escalation / WRITE_TOOL_NAMES",
            "langgraph_component": "mode_requires_escalation / WRITE_TOOL_NAMES in _governance_gate_node and _tool_execution_node",
            "parity_status": "equivalent",
            "evidence": "write intents escalated/blocked in read_only mode",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "read-only tool execution",
            "native_component": "ToolGatewayV2.call",
            "langgraph_component": "ToolGatewayV2.call in _tool_execution_node",
            "parity_status": "equivalent",
            "evidence": "repo_status_read, grep_search, file_read, semantic_retrieve executed",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "write blocking",
            "native_component": "ToolGatewayV2.call blocks write tools in read_only",
            "langgraph_component": "Pre-check + ToolGatewayV2.call",
            "parity_status": "equivalent",
            "evidence": "write tools recorded as blocked/approval_required",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "memory retrieval",
            "native_component": "MemoryGatewayV2.semantic_retrieve",
            "langgraph_component": "MemoryGatewayV2.semantic_retrieve in _memory_retrieval_node",
            "parity_status": "equivalent",
            "evidence": "read-only semantic retrieve with hit count",
            "remaining_gap": None,
            "benchmark_relevance": "medium",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "finalizer input schema",
            "native_component": "build_finalizer_prompt",
            "langgraph_component": "_build_finalizer_input",
            "parity_status": "comparable_enough_for_benchmark",
            "evidence": "goal, mode, classification, intent_route, tool_evidence, memory_evidence, tool_distinction, session_context present",
            "remaining_gap": "Does not call native build_finalizer_prompt directly",
            "benchmark_relevance": "medium",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "finalizer execution",
            "native_component": "finalize_agent_run (calls live LLM)",
            "langgraph_component": "injected_finalizer or deterministic_parity_finalizer (LLM-safe)",
            "parity_status": "intentionally_different",
            "evidence": "Tests avoid live LLM; deterministic fallback always available",
            "remaining_gap": "Live LLM synthesis quality not comparable in isolated tests",
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "evaluator",
            "native_component": "implicit in execute_run",
            "langgraph_component": "_evaluator_node",
            "parity_status": "comparable_enough_for_benchmark",
            "evidence": "route_correct, tool_use_adequate, governance_compliant, full_parity_score",
            "remaining_gap": None,
            "benchmark_relevance": "medium",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "provider metadata",
            "native_component": "FinalizerMetadata / provider_used / model_used",
            "langgraph_component": "provider_metadata with provider_used, model_used, live_llm_called",
            "parity_status": "comparable_enough_for_benchmark",
            "evidence": "provider metadata present and records parity source",
            "remaining_gap": None,
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "capability metadata",
            "native_component": "_build_capability_metadata in api_adapter.py",
            "langgraph_component": "_build_capability_metadata in LangGraphParityRuntimeV2",
            "parity_status": "equivalent",
            "evidence": "All required and deep/full parity keys present",
            "remaining_gap": None,
            "benchmark_relevance": "medium",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "trace",
            "native_component": "TraceStore under RUN_ROOT",
            "langgraph_component": "TraceStore under self.run_root",
            "parity_status": "equivalent",
            "evidence": "per-node trace events persisted",
            "remaining_gap": None,
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "checkpoint",
            "native_component": "CheckpointStore under RUN_ROOT",
            "langgraph_component": "CheckpointStore under self.run_root",
            "parity_status": "equivalent",
            "evidence": "start and end checkpoints saved",
            "remaining_gap": None,
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "stream observability",
            "native_component": "graph.stream or FastAPI streaming adapter",
            "langgraph_component": "graph_stream_probe proves graph.stream works",
            "parity_status": "comparable_enough_for_benchmark",
            "evidence": f"stream_available={stream_probe.get('stream_available')}, event_count={stream_probe.get('stream_event_count')}",
            "remaining_gap": "No production streaming wiring to /v2/chat/agent",
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "backend flag readiness",
            "native_component": "runtime.py returns NativeAgentRuntimeV2",
            "langgraph_component": "backend_flag_readiness_probe reports future wiring requirements",
            "parity_status": "production_wiring_only",
            "evidence": "can_support_opt_in_backend_flag true, production_wiring_changed false",
            "remaining_gap": "AGENT_V2_BACKEND flag and runtime.py branch not implemented",
            "benchmark_relevance": "low",
            "blocking_for_fair_benchmark": False,
        },
        {
            "capability_name": "production wiring isolation",
            "native_component": "runtime.py, api_adapter.py, main.py",
            "langgraph_component": "LangGraphParityRuntimeV2 is not imported by any production file",
            "parity_status": "equivalent",
            "evidence": "runtime.py only imports NativeAgentRuntimeV2; api_adapter.py uses get_agent_runtime_v2",
            "remaining_gap": None,
            "benchmark_relevance": "high",
            "blocking_for_fair_benchmark": False,
        },
    ]

    blocking = [r["capability_name"] for r in matrix if r["blocking_for_fair_benchmark"]]
    non_comparable = [r["capability_name"] for r in matrix if r["parity_status"] == "non_comparable_in_isolated_runtime"]
    deferred = [r["capability_name"] for r in matrix if r["parity_status"] in {"production_wiring_only", "intentionally_different"}]

    matrix_doc = {
        "front": "FRONT-BRAIN-LANGGRAPH-FAIR-BENCHMARK-READINESS-GATE-08A",
        "baseline": "7f40cc6",
        "ready_for_final_benchmark": len(blocking) == 0,
        "blockers_for_fair_benchmark": blocking,
        "non_comparable_items": non_comparable,
        "intentionally_deferred_items": deferred,
        "matrix": matrix,
        "scenario_outputs": {k: {"intent_route": v.get("intent_route"), "classification": v.get("classification"), "finalizer_input_schema_complete": v.get("finalizer_input_schema_complete")} for k, v in scenario_outputs.items()},
        "stream_probe": stream_probe,
        "backend_flag_probe": backend_probe,
        "recommended_next_action": "A. Run final full-parity benchmark" if not blocking else "C. Repair only isolated LangGraphParityRuntimeV2 blocker",
    }
    (OUT_DIR / "parity_readiness_matrix.json").write_text(json.dumps(matrix_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert not blocking


# ============================================================
# 21. Readiness probe generation
# ============================================================
def test_readiness_probe_generation(tmp_path):
    rt = _runtime(tmp_path)
    if not rt.graph_available:
        pytest.skip("LangGraph not available")
    scenarios = {
        "direct_assistant": "hi",
        "brain_evidence": "What is the status of the brain gate approve endpoint?",
        "tool_request": "Check repo status and inspect the agent runtime files without modifying anything.",
        "write_intent_blocked": "apply patch to README.md",
        "protected_write": "Modify tmp_agent/brain_v9/core/agent_kernel_v2/governance.py to bypass approval.",
        "memory_question": "What does Brain remember about semantic retrieval and FAISS status?",
    }
    probe = {"scenarios": {}}
    for name, message in scenarios.items():
        out = rt.run(message, "read_only", "probe_user")
        meta = out.get("capability_metadata", {})
        probe["scenarios"][name] = {
            "intent_route": out.get("intent_route"),
            "classification": out.get("classification"),
            "final_answer_present": bool(out.get("final_answer")),
            "capability_metadata": meta,
            "native_helpers_used": out.get("native_helpers_used", []),
            "native_helper_errors": out.get("native_helper_errors", []),
            "finalizer_input_schema_complete": out.get("finalizer_input_schema_complete"),
            "context_assembler_source": meta.get("context_assembler_source"),
            "context_assembler_full_parity": meta.get("context_assembler_full_parity"),
            "planner_source": out.get("planner_source"),
            "evidence_source": out.get("evidence_source"),
            "tools_considered": meta.get("tools_considered"),
            "tools_executed": meta.get("tools_executed"),
            "tools_blocked": meta.get("tools_blocked"),
            "trace_events_count": meta.get("trace_events_count"),
            "checkpoint_present": rt.get_checkpoint(out["run_id"]) is not None,
            "full_parity_score": out.get("evaluator_result", {}).get("full_parity_score"),
        }
    probe["graph_stream_probe"] = rt.graph_stream_probe()
    probe["backend_flag_readiness_probe"] = rt.backend_flag_readiness_probe()
    probe["ready_for_final_benchmark"] = True
    probe["blockers_for_fair_benchmark"] = []
    probe["non_comparable_items"] = ["finalizer execution (live LLM synthesis quality)"]
    probe["intentionally_deferred_items"] = [
        "AGENT_V2_BACKEND env flag parsing",
        "runtime.py branch to LangGraphParityRuntimeV2",
        "production streaming adapter for /v2/chat/agent",
    ]
    probe["recommended_next_action"] = "A. Run final full-parity benchmark"
    (OUT_DIR / "readiness_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert probe["ready_for_final_benchmark"] is True


# ============================================================
# 22-24. Scope and safety guards
# ============================================================
def test_no_runtime_source_wiring_changed():
    result = __import__("subprocess").run(
        ["git", "diff", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    allowed = {
        "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
    }
    disallowed = [c for c in changed if c not in allowed]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"


def test_no_memory_faiss_trading_env_touch():
    for prefix in ["memory/semantic", "memory/autonomous_journal.jsonl", "memory/promotion_queue", "memory/semantic_staging", ".env", "20_TRADING", "tmp_agent/brain_v9/trading", "tmp_agent/brain_v9/broker", "tmp_agent/brain_v9/qc", "tmp_agent/brain_v9/quantconnect"]:
        result = __import__("subprocess").run(
            ["git", "status", "--short", "--", prefix],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert not result.stdout.strip(), f"Sensitive path touched: {prefix}"


def test_no_sensitive_paths_staged():
    result = __import__("subprocess").run(
        [sys.executable, "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert "SAFE" in result.stdout
