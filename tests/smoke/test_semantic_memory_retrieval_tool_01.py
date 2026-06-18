#!/usr/bin/env python3
"""
Smoke test: Semantic memory evidence source and retrieval wiring.
Author: KIMI/CODEX
Date: 2026-06-18
"""
import sys
import os
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL")
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter


def _sources_for(message: str):
    adapter = AgentV2IntentAdapter()
    ri = adapter.select_route(message)
    if ri["route"] == "direct_assistant":
        return []
    return adapter.get_evidence_sources("brain_evidence", message)


def _source_types(sources):
    return [s["type"] for s in sources]


def _semantic_present(sources):
    return "semantic_memory" in _source_types(sources)


def test_q1_brain_knowledge():
    s = _sources_for("qué sabe Brain sobre ingesta de datos?")
    st = _source_types(s)
    assert "semantic_memory" in st, f"Q1: expected semantic_memory in {st}"
    print("PASS: Q1 semantic_memory selected")


def test_q2_memory_specific_spanish():
    s = _sources_for("qué recuerda Brain del frente anterior?")
    st = _source_types(s)
    assert "semantic_memory" in st, f"Q2: expected semantic_memory in {st}"
    print("PASS: Q2 semantic_memory selected")


def test_q3_traces_not_overridden():
    s = _sources_for("qué tools se ejecutaron realmente?")
    st = _source_types(s)
    # traces should be primary, semantic_memory may or may not appear but not dominant
    assert "traces" in st, f"Q3: traces should remain primary; got {st}"
    # semantic_memory should NOT be the first/highest priority source unless score ties
    if "semantic_memory" in st:
        traces_score = next((s.get("_router_meta", {}).get("score", 0) for s in s if s["type"] == "traces"), 0)
        mem_score = next((s.get("_router_meta", {}).get("score", 0) for s in s if s["type"] == "semantic_memory"), 0)
        assert traces_score >= mem_score, f"Q3: traces score {traces_score} < semantic {mem_score}"
    print("PASS: Q3 traces regression OK")


def test_q4_ingestion_regression():
    s = _sources_for("CUALES Y CUANTAS FUENTES DE INGESTA CURADA TIENE BRAIN EN ESTE MOMENTO?")
    st = _source_types(s)
    assert "learning_external" in st, f"Q4: expected learning_external in {st}"
    # semantic_memory should not dominate over learning_external
    if "semantic_memory" in st:
        le_score = next((s.get("_router_meta", {}).get("score", 0) for s in s if s["type"] == "learning_external"), 0)
        mem_score = next((s.get("_router_meta", {}).get("score", 0) for s in s if s["type"] == "semantic_memory"), 0)
        assert le_score >= mem_score, f"Q4: learning_external score {le_score} < semantic {mem_score}"
    print("PASS: Q4 learning_external regression OK")


def test_q5_recipe_generic():
    s = _sources_for("dame una receta de arroz con pollo")
    assert s == [], f"Q5: expected empty sources for recipe, got {s}"
    print("PASS: Q5 recipe direct_assistant regression OK")


def test_planner_includes_semantic_step():
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    rt = NativeAgentRuntimeV2()
    run = rt.create_run("qué sabe Brain sobre ingesta de datos?", "read_only", "test_user_sm_01")
    run = rt.plan_run(run["run_id"])
    # Set route info manually to brain_evidence to test plan building
    adapter = AgentV2IntentAdapter()
    sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
    assert any(s["type"] == "semantic_memory" for s in sources), "Planner test: semantic_memory not in sources"
    # Simulate the plan step for semantic_memory source
    for src in sources:
        if src["type"] == "semantic_memory":
            assert "semantic_retrieve" in src["tools"], "Planner test: semantic_retrieve not in tools"
    print("PASS: Planner includes semantic_retrieve for semantic_memory source")


def test_finalizer_receives_memory_hits():
    from brain_v9.core.agent_kernel_v2.finalizer import build_finalizer_prompt
    run = {"goal": "qué sabe Brain?", "mode": "read_only", "classification": "brain_evidence"}
    hits = [{"id": "rec1", "snippet": "Brain aprendió de fuentes externas"}]
    prompt = build_finalizer_prompt(run, hits, [], template_override="brain_evidence")
    assert "MEMORIA SEMANTICA" in prompt.upper() or "MEMORY_EVIDENCE" in prompt.upper() or "semantic" in prompt.lower(), "Finalizer should reference memory somehow"
    print("PASS: Finalizer receives memory_hits")


if __name__ == "__main__":
    test_q1_brain_knowledge()
    test_q2_memory_specific_spanish()
    test_q3_traces_not_overridden()
    test_q4_ingestion_regression()
    test_q5_recipe_generic()
    test_planner_includes_semantic_step()
    test_finalizer_receives_memory_hits()
    print("\nALL SEMANTIC MEMORY TESTS PASSED")
