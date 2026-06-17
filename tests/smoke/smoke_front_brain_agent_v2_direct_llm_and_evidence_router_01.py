"""
Smoke test for FRONT-BRAIN-AGENT-V2-DIRECT-LLM-AND-EVIDENCE-ROUTER-01
Tests intent-based routing in Agent V2.
"""
import sys
from pathlib import Path

# Ensure imports resolve
sys.path.insert(0, str(Path(__file__).parents[2]))

from tmp_agent.brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter


def test_generic_conversation_routes_to_direct_assistant():
    adapter = AgentV2IntentAdapter()
    
    generic_queries = [
        "Hola, como estas?",
        "What's the weather like?",
        "Tell me a joke",
        "How do I cook pasta?",
        "What is the capital of France?",
    ]
    
    for q in generic_queries:
        result = adapter.select_route(q)
        assert result["route"] == "direct_assistant", f"Expected direct_assistant for: {q}, got: {result['route']}"
        assert result["confidence"] >= 0.5
        print(f"  PASS: {q} -> {result['route']} (intent={result['intent']}, conf={result['confidence']:.2f})")


def test_brain_questions_routes_to_brain_evidence():
    adapter = AgentV2IntentAdapter()
    
    brain_queries = [
        "What is the current status of the Brain agent?",
        "Show me the latest front_brain traces",
        "What did we do in the last ledger entry?",
        "How does the agent kernel v2 router work?",
        "Show evidence from tmp_agent directory",
    ]
    
    for q in brain_queries:
        result = adapter.select_route(q)
        assert result["route"] in {"brain_evidence", "mixed_brain_reasoning"}, f"Expected brain route for: {q}, got: {result['route']}"
        assert result["has_brain_signals"] is True
        print(f"  PASS: {q} -> {result['route']} (intent={result['intent']}, conf={result['confidence']:.2f})")


def test_mixed_queries_routes_correctly():
    adapter = AgentV2IntentAdapter()
    
    mixed_queries = [
        "Why is the Brain agent slow and how can I fix it?",
        "Explain the agent kernel and give me a summary of recent changes",
    ]
    
    for q in mixed_queries:
        result = adapter.select_route(q)
        # Mixed queries may go to brain_evidence or mixed_brain_reasoning
        assert result["route"] in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}, f"Unexpected route for: {q}, got: {result['route']}"
        assert result["has_brain_signals"] is True
        print(f"  PASS: {q} -> {result['route']} (intent={result['intent']}, conf={result['confidence']:.2f})")


def test_evidence_source_mapping():
    adapter = AgentV2IntentAdapter()
    
    # Front brain query
    sources = adapter.get_evidence_sources("brain_evidence", "Show me front_brain traces")
    assert len(sources) > 0
    assert any(s["type"] == "front_brain" for s in sources)
    print(f"  PASS: front_brain sources mapped")
    
    # Ledger query
    sources = adapter.get_evidence_sources("brain_evidence", "What is in the migration ledger?")
    assert any(s["type"] == "ledgers" for s in sources)
    print(f"  PASS: ledger sources mapped")
    
    # Trace query
    sources = adapter.get_evidence_sources("brain_evidence", "Show me run traces")
    assert any(s["type"] == "traces" for s in sources)
    print(f"  PASS: trace sources mapped")


def test_direct_assistant_skips_tools():
    """Verify that direct_assistant route does not require tool execution."""
    adapter = AgentV2IntentAdapter()
    result = adapter.select_route("Hello!")
    assert result["route"] == "direct_assistant"
    sources = adapter.get_evidence_sources(result["route"], "Hello!")
    assert sources == []
    print(f"  PASS: direct_assistant has no evidence sources")


if __name__ == "__main__":
    print("Running smoke tests for FRONT-BRAIN-AGENT-V2-DIRECT-LLM-AND-EVIDENCE-ROUTER-01")
    print()
    
    print("Test 1: Generic conversation routes to direct_assistant")
    test_generic_conversation_routes_to_direct_assistant()
    print()
    
    print("Test 2: Brain questions routes to brain_evidence")
    test_brain_questions_routes_to_brain_evidence()
    print()
    
    print("Test 3: Mixed queries route correctly")
    test_mixed_queries_routes_correctly()
    print()
    
    print("Test 4: Evidence source mapping")
    test_evidence_source_mapping()
    print()
    
    print("Test 5: Direct assistant skips tools")
    test_direct_assistant_skips_tools()
    print()
    
    print("All smoke tests passed.")
