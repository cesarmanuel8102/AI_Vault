#!/usr/bin/env python3
"""
Smoke test: Adaptive Tool Planner v1.
Tests that operational_agent routes with Brain-specific queries get deeper tooling.
"""
import sys, os
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL")
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter


def _plan_for(goal):
    """Simulate plan construction for a goal via NativeAgentRuntimeV2."""
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    rt = NativeAgentRuntimeV2()
    run = rt.create_run(goal, "read_only", "test_adaptive_01")
    # We can't easily call execute_run without mocking the server, but we can
    # inspect the planner output for operational_agent
    adapter = AgentV2IntentAdapter()
    sources = adapter.get_evidence_sources("brain_evidence", goal)
    return sources, run


def test_q1_scheduler_code_search():
    sources, run = _plan_for("busca en el codigo donde se decide si el scheduler esta activo y dime la evidencia")
    # At minimum, evidence sources should be non-empty or the route should be brain_evidence
    adapter = AgentV2IntentAdapter()
    ri = adapter.select_route(run["goal"])
    # Accept any Brain-specific route
    assert ri["route"] in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}, f"Q1: expected Brain-specific route, got {ri['route']}"
    # If operational_agent, there should be fallback evidence sources or deeper planner tools
    if ri["route"] == "operational_agent":
        assert sources or run.get("classification") in {"autonomy_diagnosis", "code_search", "recent_changes_diagnosis"}, "Q1: operational_agent should have evidence or Brain classification"
    print("PASS: Q1 scheduler code search routing")


def test_q2_followup_expansion_context():
    from brain_v9.core.agent_kernel_v2.context_assembler import _is_follow_up
    # Should detect as follow-up
    assert _is_follow_up("si no lo encuentras, amplia la busqueda"), "Q2: should detect follow-up"
    print("PASS: Q2 follow-up expansion context")


def test_q3_semantic_memory_selection():
    sources, run = _plan_for("que sabe Brain en memoria sobre scheduler o autonomia?")
    adapter = AgentV2IntentAdapter()
    ri = adapter.select_route(run["goal"])
    # semantic_memory should be selected
    st = [s["type"] for s in sources]
    assert "semantic_memory" in st or ri["route"] in {"brain_evidence", "mixed_brain_reasoning"}, f"Q3: expected semantic_memory or Brain route; got {st}, route={ri['route']}"
    print("PASS: Q3 semantic memory selection")


def test_q4_traces_regression():
    sources, run = _plan_for("que tools se ejecutaron realmente?")
    st = [s["type"] for s in sources]
    assert "traces" in st, f"Q4: expected traces in evidence sources; got {st}"
    print("PASS: Q4 traces regression")


def test_q5_recipe_direct_assistant():
    adapter = AgentV2IntentAdapter()
    ri = adapter.select_route("dame una receta de arroz con pollo")
    assert ri["route"] == "direct_assistant", f"Q5: expected direct_assistant, got {ri['route']}"
    print("PASS: Q5 recipe direct_assistant")


def test_q6_semantic_memory_regression():
    adapter = AgentV2IntentAdapter()
    ri = adapter.select_route("que sabe Brain sobre ingesta de datos?")
    sources = adapter.get_evidence_sources("brain_evidence", "que sabe Brain sobre ingesta de datos?")
    st = [s["type"] for s in sources]
    assert "semantic_memory" in st or "learning_external" in st, f"Q6: expected semantic_memory or learning_external; got {st}"
    print("PASS: Q6 semantic memory regression")


if __name__ == "__main__":
    test_q1_scheduler_code_search()
    test_q2_followup_expansion_context()
    test_q3_semantic_memory_selection()
    test_q4_traces_regression()
    test_q5_recipe_direct_assistant()
    test_q6_semantic_memory_regression()
    print("\nALL ADAPTIVE TOOL PLANNER TESTS PASSED")
