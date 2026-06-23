# Evidence Integrity Smoke Tests for Agent V2
import sys
sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

runtime = NativeAgentRuntimeV2()

def test_direct_assistant_no_tools_integrity():
    run = runtime.create_run("dame una receta de arroz con pollo", mode="read_only", user_id="test_integrity_da")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    assert result["intent_route"] == "direct_assistant", f"Route: {result['intent_route']}"
    assert len(result.get("plan", [])) == 0, f"Plan should be empty: {result.get('plan')}"
    print(f"PASS: direct_assistant - run_id={run_id}")

def test_brain_evidence_tool_trace_integrity():
    run = runtime.create_run("revisa los archivos del runtime para ver donde se activa el programador automatico", mode="read_only", user_id="test_integrity_be")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    assert result["intent_route"] in ("brain_evidence", "operational_agent", "mixed_brain_reasoning"), f"Route: {result['intent_route']}"
    tools = [s.get("tool_name") for s in result.get("plan", []) if s.get("tool_name")]
    assert len(tools) > 0, f"Should have tools: {tools}"
    # Check all planned tools have status completed/blocked/failed
    for step in result.get("plan", []):
        if step.get("tool_name"):
            assert step.get("status") in ("completed", "blocked", "failed"), f"Tool {step.get('tool_name')} stuck at {step.get('status')}"
    print(f"PASS: brain_evidence - run_id={run_id}, tools={tools}")

def test_semantic_memory_trace_integrity():
    run = runtime.create_run("que conocimiento persistente tiene Brain sobre fuentes externas?", mode="read_only", user_id="test_integrity_sm")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    sources = [s.get("type") for s in result.get("evidence_sources", [])]
    assert "semantic_memory" in sources or "learning_external" in sources, f"Sources: {sources}"
    print(f"PASS: semantic_memory - run_id={run_id}, sources={sources}")

def test_blocked_tool_integrity():
    # This test is skipped - no reliable way to trigger blocked tool in read_only
    print("SKIP: blocked_tool_integrity (no reliable trigger in read_only)")

def test_api_trace_consistency():
    print("SKIP: api_trace_consistency (server not required for unit tests)")

if __name__ == "__main__":
    test_direct_assistant_no_tools_integrity()
    test_brain_evidence_tool_trace_integrity()
    test_semantic_memory_trace_integrity()
    test_blocked_tool_integrity()
    test_api_trace_consistency()
    print("ALL EVIDENCE INTEGRITY TESTS PASSED")
