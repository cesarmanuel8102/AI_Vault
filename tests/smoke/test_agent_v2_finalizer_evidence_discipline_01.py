# Finalizer Evidence Discipline Smoke Tests for Agent V2
import sys
sys.path.insert(0, "C:/AI_VAULT_CANONICAL")

from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
from tmp_agent.brain_v9.core.agent_kernel_v2.finalizer import _structured_fallback, build_finalizer_prompt, finalize_agent_run

runtime = NativeAgentRuntimeV2()

def test_direct_assistant_does_not_claim_tools():
    """Direct assistant queries should not claim tool evidence."""
    run = runtime.create_run("dame una receta de arroz con pollo", mode="read_only", user_id="test_finalizer_da")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    assert result["intent_route"] == "direct_assistant", f"Route: {result['intent_route']}"
    assert len(result.get("plan", [])) == 0, f"Plan should be empty: {result.get('plan')}"
    final = result.get("final_answer", "").lower()
    # Should not claim tools executed, evidence used, repo checked, memory retrieved in a tool context
    # Use regex to detect explicit tool claims, not natural language words
    import re
    tool_claim_patterns = [
        r'\btool\b.*\b(executed|ran|used|invoked)\b',
        r'\bexecuted\b.*\btool\b',
        r'\b(searched|checked|retrieved)\b.*\b(repo|file|memory|semantic)\b',
        r'\b(grep|file_read|semantic_retrieve)\b',
        r'\bevidence\b.*\b(found|shows|indicates)\b',
    ]
    for pattern in tool_claim_patterns:
        if re.search(pattern, final, re.IGNORECASE):
            assert False, f"Direct assistant claimed tool usage: pattern '{pattern}' matched in: {final[:200]}"
    print(f"PASS: direct_assistant_no_tool_claims - run_id={run_id}")

def test_tool_evidence_is_listed():
    """Brain evidence queries should list executed tools in final answer."""
    run = runtime.create_run("revisa los archivos del runtime para ver donde se activa el programador automatico", mode="read_only", user_id="test_finalizer_be")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    assert result["intent_route"] in ("brain_evidence", "operational_agent", "mixed_brain_reasoning"), f"Route: {result['intent_route']}"
    tools = [s.get("tool_name") for s in result.get("plan", []) if s.get("tool_name")]
    assert len(tools) > 0, f"Should have tools: {tools}"
    final = result.get("final_answer", "")
    # Should mention at least one executed tool or evidence
    # Check that executed tools are mentioned (case-insensitive)
    found = any(t.lower() in final.lower() for t in tools if t)
    assert found, f"Final answer should mention executed tools: {tools}. Final: {final[:200]}"
    print(f"PASS: tool_evidence_listed - run_id={run_id}, tools={tools}")

def test_memory_labeled_as_memory():
    """Semantic memory queries should label memory as memory/persistent context."""
    run = runtime.create_run("que conocimiento persistente tiene Brain sobre fuentes externas?", mode="read_only", user_id="test_finalizer_sm")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    sources = [s.get("type") for s in result.get("evidence_sources", [])]
    assert "semantic_memory" in sources or "learning_external" in sources, f"Sources: {sources}"
    tools = [s.get("tool_name") for s in result.get("plan", []) if s.get("tool_name")]
    assert "semantic_retrieve" in tools, f"semantic_retrieve not in tools: {tools}"
    final = result.get("final_answer", "").lower()
    # Should label memory as memory/persistent context
    assert "memory" in final or "persistent" in final or "context" in final, f"Memory should be labeled as memory/persistent context: {final[:200]}"
    print(f"PASS: memory_labeled_as_memory - run_id={run_id}, sources={sources}")

def test_blocked_or_failed_tool_visible():
    """Test that fallback lists blocked/failed tools."""
    # Test via _structured_fallback directly
    tool_results = [
        {"tool_name": "grep_search", "ok": True, "blocked": False, "approval_required": False, "error": ""},
        {"tool_name": "file_read", "ok": False, "blocked": True, "approval_required": False, "error": "path blocked"},
        {"tool_name": "semantic_retrieve", "ok": False, "blocked": False, "approval_required": False, "error": "timeout"},
    ]
    fallback = _structured_fallback("test goal", "read_only", [], tool_results, "test_reason")
    assert "Executed tools:" in fallback, "Should list executed tools"
    assert "Blocked tools:" in fallback, "Should list blocked tools"
    assert "Failed tools:" in fallback, "Should list failed tools"
    print("PASS: blocked_or_failed_tool_visible")

def test_provider_fallback_note():
    """Fallback should include provider fallback note and no raw CoT."""
    fallback = _structured_fallback("test goal", "read_only", [], [], "primary_failed:timeout")
    assert "Provider status: degraded fallback" in fallback, "Should mention provider fallback"
    assert "Inference boundary:" in fallback, "Should have inference boundary"
    assert "chain-of-thought" not in fallback.lower(), "Should not leak CoT"
    print("PASS: provider_fallback_note")

def test_inference_boundary():
    """Fallback should label inference as inference."""
    fallback = _structured_fallback("test goal", "read_only", [], [], "test_reason")
    assert "Inference boundary:" in fallback, "Should have inference boundary"
    assert "inference" in fallback.lower(), "Should mention inference"
    print("PASS: inference_boundary")

def test_direct_assistant_fallback_no_tool_claims():
    """Direct assistant fallback should not claim tool evidence."""
    # direct_assistant has no tools
    fallback = _structured_fallback("dame una receta", "read_only", [], [], "test_reason")
    # Should say no tools executed
    assert "No tools executed and no memory hits" in fallback or "No tools executed" in fallback
    print("PASS: direct_assistant_fallback_no_tool_claims")

if __name__ == "__main__":
    from tmp_agent.brain_v9.core.agent_kernel_v2.finalizer import _structured_fallback
    test_direct_assistant_does_not_claim_tools()
    test_tool_evidence_is_listed()
    test_memory_labeled_as_memory()
    test_blocked_or_failed_tool_visible()
    test_provider_fallback_note()
    test_inference_boundary()
    test_direct_assistant_fallback_no_tool_claims()
    print("ALL FINALIZER EVIDENCE DISCIPLINE TESTS PASSED")
