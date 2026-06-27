# Semantic Retrieval Hygiene Smoke Tests for Agent V2
import sys
from tests._repo_root import REPO_ROOT
sys.path.insert(0, str(REPO_ROOT))

from tmp_agent.brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

gateway = MemoryGatewayV2()
runtime = NativeAgentRuntimeV2()

def test_no_blank_hits_returned():
    result = gateway.semantic_retrieve("que sabe Brain sobre Agent V2", top_k=5)
    hits = result.get("hits", [])
    assert result.get("filtered_empty_count", 0) >= 0
    for h in hits:
        text = h.get("text", "") or ""
        assert text.strip(), f"Hit has blank text: {h}"
    print("PASS: no_blank_hits_returned")

def test_write_performed_false():
    result = gateway.semantic_retrieve("test query", top_k=5)
    assert result.get("write_performed") is False
    print("PASS: write_performed_false")

def test_diagnostics_present():
    result = gateway.semantic_retrieve("test query", top_k=5)
    assert "raw_hit_count" in result
    assert "usable_hit_count" in result
    assert "filtered_empty_count" in result
    print("PASS: diagnostics_present")

def test_generic_query_not_memory_forced():
    runtime = NativeAgentRuntimeV2()
    run = runtime.create_run("explícame una receta de arroz con pollo", mode="read_only", user_id="test_hygiene_da")
    run = runtime.execute_run(run["run_id"])
    assert run["intent_route"] == "direct_assistant"
    assert len(run.get("plan", [])) == 0
    print("PASS: generic_query_not_memory_forced")

def test_fdot_control_not_brain_memory_grounded():
    runtime = NativeAgentRuntimeV2()
    run = runtime.create_run("FDOT concrete cylinder curing time", mode="read_only", user_id="test_hygiene_fdot")
    run = runtime.execute_run(run["run_id"])
    tools = [s.get("tool_name") for s in run.get("plan", []) if s.get("tool_name")]
    assert "semantic_retrieve" not in tools
    print("PASS: fdot_control_not_brain_memory_grounded")

def test_metadata_returned():
    result = gateway.semantic_retrieve("test query", top_k=3)
    hits = result.get("hits", [])
    if hits:
        h = hits[0]
        assert "source" in h or "kind" in h or "created_utc" in h or "metadata" in h
    print("PASS: metadata_returned")

if __name__ == "__main__":
    test_no_blank_hits_returned()
    test_write_performed_false()
    test_diagnostics_present()
    test_generic_query_not_memory_forced()
    test_fdot_control_not_brain_memory_grounded()
    test_metadata_returned()
    print("ALL SEMANTIC RETRIEVAL HYGIENE TESTS PASSED")
