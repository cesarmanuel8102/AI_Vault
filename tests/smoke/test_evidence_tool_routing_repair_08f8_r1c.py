"""Regression test for evidence tool routing repair (08F8 R1C).

Verifies that the problem prompt triggers brain_evidence routing and
executes read-only evidence tools instead of falling to direct_assistant.
"""
from __future__ import annotations
import sys, os, json, re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, str(REPO_ROOT))

from tmp_agent.brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

PROBLEM_PROMPT = (
    "en que mejoraste despues de empezar a usar langraph? "
    "tienes algun modo de aprendizaje guiado por un maestro, especificamente codex, "
    "creo que era modo teacher? Necesito que busques informacion de la memoria persistente, "
    "como esta estructurada y que falta para que funcione. jecute la herramienta necesaria para eso. "
    "ejecuta la herramienta necesaria."
)


def test_problem_prompt_routes_to_brain_evidence():
    runtime = LangGraphParityRuntimeV2()
    result = runtime.run(message=PROBLEM_PROMPT, mode="read_only", user_id="test_evidence_v2")

    assert result["intent_route"] == "brain_evidence", (
        f"Expected intent_route='brain_evidence', got '{result.get('intent_route')}'"
    )
    assert result.get("classification") is not None
    assert result.get("classification") != "direct_assistant"


def test_problem_prompt_executes_tools():
    runtime = LangGraphParityRuntimeV2()
    result = runtime.run(message=PROBLEM_PROMPT, mode="read_only", user_id="test_evidence_v2")

    executed = result.get("executed_tools", [])
    assert len(executed) > 0, "Expected at least one tool to be executed"
    # All executed tools should be read-only
    from tmp_agent.brain_v9.core.agent_kernel_v2.governance import READ_ONLY_TOOL_NAMES
    for tool in executed:
        assert tool in READ_ONLY_TOOL_NAMES, f"Tool '{tool}' is not in READ_ONLY_TOOL_NAMES"


def test_problem_prompt_produces_evidence_finalizer():
    runtime = LangGraphParityRuntimeV2()
    result = runtime.run(message=PROBLEM_PROMPT, mode="read_only", user_id="test_evidence_v2")

    answer = result.get("final_answer", "")
    # Should NOT contain the old generic fallback message
    assert "No hay evidencia de herramientas" not in answer, (
        "Finalizer still producing old generic fallback for evidence route"
    )
    # Should contain structured sections
    assert any(s in answer for s in ["Summary", "Evidence", "Actions", "Risks"]), (
        f"Final answer missing structured evidence sections. Snippet: {answer[:200]}"
    )


def test_new_evidence_tools_registered():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    tg = ToolGatewayV2()
    cap_names = {c["name"] for c in tg.list_capabilities()}
    evidence_tools = {
        "repo_file_search", "repo_file_read", "memory_structure_inspect",
        "semantic_memory_status", "promotion_queue_status", "capability_registry_read",
    }
    for tool in evidence_tools:
        assert tool in cap_names, f"Evidence tool '{tool}' not registered in ToolGatewayV2"


def test_evidence_tools_are_read_only():
    from tmp_agent.brain_v9.core.agent_kernel_v2.governance import READ_ONLY_TOOL_NAMES
    evidence_tools = {
        "repo_file_search", "repo_file_read", "memory_structure_inspect",
        "semantic_memory_status", "promotion_queue_status", "capability_registry_read",
    }
    for tool in evidence_tools:
        assert tool in READ_ONLY_TOOL_NAMES, f"Evidence tool '{tool}' not in READ_ONLY_TOOL_NAMES"


if __name__ == "__main__":
    test_problem_prompt_routes_to_brain_evidence()
    test_problem_prompt_executes_tools()
    test_problem_prompt_produces_evidence_finalizer()
    test_new_evidence_tools_registered()
    test_evidence_tools_are_read_only()
    print("All evidence routing regression tests passed.")
