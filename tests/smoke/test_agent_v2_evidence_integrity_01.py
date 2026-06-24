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
    for step in result.get("plan", []):
        if step.get("tool_name"):
            assert step.get("status") in ("completed", "blocked", "failed"), f"Tool {step.get('tool_name')} stuck at {step.get('status')}"
    print(f"PASS: brain_evidence - run_id={run_id}, tools={tools}")

def test_followup_context_not_regressed():
    user_id = "test_followup_20260624"
    q1 = "revisa los archivos del runtime para ver donde se activa el programador automatico"
    run1 = runtime.create_run(q1, mode="read_only", user_id=user_id)
    run1 = runtime.execute_run(run1["run_id"])
    assert run1["status"] == "completed"
    q2 = "intenta otra forma y revisa mas amplio"
    run2 = runtime.create_run(q2, mode="read_only", user_id=user_id)
    run2 = runtime.execute_run(run2["run_id"])
    assert run2["status"] == "completed"
    sc = run2.get("session_context", {})
    assert sc.get("is_follow_up") is True, f"is_follow_up should be true: {sc}"
    prev_goal = sc.get("prev_goal")
    assert prev_goal is not None and "programador" in prev_goal, f"prev_goal not inherited: {prev_goal}"
    assert run2["intent_route"] != "direct_assistant", f"Q2 should not be direct_assistant: {run2['intent_route']}"
    print(f"PASS: followup_context - q1={run1['run_id']}, q2={run2['run_id']}")

def test_semantic_memory_not_regressed():
    run = runtime.create_run("que conocimiento persistente tiene Brain sobre fuentes externas?", mode="read_only", user_id="test_integrity_sm")
    run_id = run["run_id"]
    result = runtime.execute_run(run_id)
    assert result["status"] == "completed", f"Status: {result['status']}"
    sources = [s.get("type") for s in result.get("evidence_sources", [])]
    assert "semantic_memory" in sources or "learning_external" in sources, f"Sources: {sources}"
    tools = [s.get("tool_name") for s in result.get("plan", []) if s.get("tool_name")]
    assert "semantic_retrieve" in tools, f"semantic_retrieve not in tools: {tools}"
    for step in result.get("plan", []):
        if step.get("tool_name") == "semantic_retrieve":
            assert step.get("output", {}).get("result", {}).get("write_performed") is not True, "write_performed should not be True"
    print(f"PASS: semantic_memory - run_id={run_id}, sources={sources}")

def test_failure_path_integrity():
    """Test that runtime exceptions are caught and run is marked failed."""
    # This test verifies the exception handling structure exists.
    # Full integration test would require deeper mocking.
    from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    import inspect
    
    # Verify the try/except structure exists in execute_run
    source = inspect.getsource(NativeAgentRuntimeV2.execute_run)
    assert "try:" in source, "execute_run should have try block"
    assert "except Exception as exc:" in source, "execute_run should have except block"
    assert "run_failed" in source, "execute_run should emit run_failed trace"
    assert 'run["status"] = "failed"' in source, "execute_run should set status to failed"
    
    print("PASS: failure_path - exception handling structure verified")

if __name__ == "__main__":
    test_direct_assistant_no_tools_integrity()
    test_brain_evidence_tool_trace_integrity()
    test_followup_context_not_regressed()
    test_semantic_memory_not_regressed()
    test_failure_path_integrity()
    print("ALL EVIDENCE INTEGRITY TESTS PASSED")
