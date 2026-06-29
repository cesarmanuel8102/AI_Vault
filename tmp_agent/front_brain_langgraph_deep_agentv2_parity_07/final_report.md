# Final Report: FRONT-BRAIN-LANGGRAPH-DEEP-AGENTV2-PARITY-07

## Summary

Deepened `LangGraphParityRuntimeV2` from a deterministic shim prototype to real Agent V2 parity by reusing `AgentV2IntentAdapter.select_route()`, `AgentV2IntentAdapter.get_evidence_sources()`, `planner.build_plan()`, `ToolGatewayV2.call()`, `MemoryGatewayV2.semantic_retrieve()`, `TraceStore`, and `CheckpointStore` inside LangGraph nodes. Production wiring, runtime selector, and `/v2/chat/agent` route remain unchanged.

## Files changed

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` (modified)
- `tests/smoke/test_brain_langgraph_deep_agentv2_parity_07.py` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/deep_parity_probe.json` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/deep_parity_probe.md` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/implementation_summary.json` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/implementation_summary.md` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/final_report.json` (created)
- `tmp_agent/front_brain_langgraph_deep_agentv2_parity_07/final_report.md` (created)

## Native V2 helpers integrated

- `AgentV2IntentAdapter.select_route()` — active
- `AgentV2IntentAdapter.get_evidence_sources()` — active
- `planner.build_plan()` — active
- `context_assembler` pure helpers (`_is_follow_up`, `_has_generic_override`) — active
- `ToolGatewayV2.call()` — active with improved skip/block logging
- `MemoryGatewayV2.semantic_retrieve()` — active read-only

## Validation

- Front 07 tests: 23 passed, 0 failed
- Core security unit tests: 3 passed
- Guard: SAFE
- py_compile: passed for `langgraph_parity_runtime.py` and test file
- No memory, FAISS, trading, or .env writes
- No production wiring changes

## Known strict-scope regressions

Two older tests fail because they enforce stricter assumptions than Front 07 permits:

1. `test_brain_langgraph_parity_prototype_05.py::test_langgraph_parity_brain_evidence_path` expects `classification == "brain_evidence"`. With `planner.build_plan()` the classification becomes `endpoint_probe` / `repo_audit` / `memory_question`. This is correct real-planner behavior.
2. `test_brain_native_vs_langgraph_parity_benchmark_06.py::test_no_runtime_source_modified` flags `langgraph_parity_runtime.py` as disallowed because from Front 06's perspective it should not change. Front 07 explicitly allows this modification.

## Recommended next action

**A. Run deep parity benchmark against Native V2**

The runtime is now ready for a new benchmark to measure the reduced gap versus Native V2.

## Remaining gaps

- Full `context_assembler` reuse requires isolated `run_root` support.
- Finalizer parity with native `finalize_agent_run` needs an injectable LLM-safe path.
- No `graph.stream` usage yet.
- No `AGENT_V2_BACKEND` flag wiring yet.
