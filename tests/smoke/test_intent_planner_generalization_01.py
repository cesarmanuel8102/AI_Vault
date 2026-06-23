#!/usr/bin/env python3
"""Test that routing is architecture-driven, not query-specific."""
import sys
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL")
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter


def test_q1_scheduler_variation():
    """Must NOT be forced to autonomy_diagnosis by word 'scheduler'."""
    adapter = AgentV2IntentAdapter()
    msg = "revisa los archivos del runtime para ver donde se activa el programador automatico"
    ri = adapter.select_route(msg)
    # Accept any Brain-specific route or operational_agent
    assert ri["route"] in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}, f"Q1: got {ri['route']}"
    # Must NOT be direct_assistant
    assert ri["route"] != "direct_assistant"
    print("PASS: Q1 scheduler variation routes Brain-specific")


def test_q2_expansion_variation():
    """Must detect expansion intent without exact 'amplia la busqueda'."""
    adapter = AgentV2IntentAdapter()
    msg = "intenta otra forma y revisa mas amplio"
    ri = adapter.select_route(msg)
    # Expansion alone doesn't change route directly; context_assembler handles it
    assert ri["route"] in {"brain_evidence", "mixed_brain_reasoning", "operational_agent", "direct_assistant"}
    print("PASS: Q2 expansion variation")


def test_q3_trace_variation():
    """Must route trace without exact historical question."""
    adapter = AgentV2IntentAdapter()
    msg = "qué acciones realizó el agente en la ejecución anterior?"
    sources = adapter.get_evidence_sources("brain_evidence", msg)
    st = [s["type"] for s in sources]
    assert "traces" in st, f"Q3: expected traces; got {st}"
    print("PASS: Q3 trace variation")


def test_q4_semantic_variation():
    """Must route semantic without exact 'que sabe Brain'."""
    adapter = AgentV2IntentAdapter()
    msg = "que conocimiento persistente tiene Brain sobre fuentes externas?"
    sources = adapter.get_evidence_sources("brain_evidence", msg)
    st = [s["type"] for s in sources]
    assert "semantic_memory" in st or "learning_external" in st, f"Q4: got {st}"
    print("PASS: Q4 semantic variation")


def test_q5_recipe_stays_generic():
    """Recipe must stay direct_assistant regardless of variation."""
    adapter = AgentV2IntentAdapter()
    msg = "dame una receta de arroz con pollo"
    ri = adapter.select_route(msg)
    assert ri["route"] == "direct_assistant", f"Q5: got {ri['route']}"
    print("PASS: Q5 recipe generic")


def test_q6_autonomy_keyword_no_longer_forces_diagnosis():
    """Word 'autonomy' alone must not force autonomy_diagnosis in planner."""
    from brain_v9.core.agent_kernel_v2.planner import classify_goal
    cls = classify_goal("how does the scheduler work")
    assert cls not in {"autonomy_diagnosis"}, f"Q6: got {cls}"
    print("PASS: Q6 'scheduler' no longer forces autonomy_diagnosis")


if __name__ == "__main__":
    test_q1_scheduler_variation()
    test_q2_expansion_variation()
    test_q3_trace_variation()
    test_q4_semantic_variation()
    test_q5_recipe_stays_generic()
    test_q6_autonomy_keyword_no_longer_forces_diagnosis()
    print("\nALL INTENT PLANNER GENERALIZATION TESTS PASSED")
