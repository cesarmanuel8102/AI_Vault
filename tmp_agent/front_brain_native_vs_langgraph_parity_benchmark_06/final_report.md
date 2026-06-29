# Final Report: FRONT-BRAIN-NATIVE-VS-LANGGRAPH-PARITY-BENCHMARK-06

## Summary

Benchmarked the canonical `NativeAgentRuntimeV2` against the isolated `LangGraphParityRuntimeV2` (created in Front 05) using six orchestration scenarios. Both runtimes passed all governance and write-block safety checks. Native V2 scored marginally higher (585 vs 580 out of 600), mainly because the parity runtime still uses deterministic intent/planner shims rather than the full native helpers.

## Scores

| Runtime | Total | Max |
|---------|-------|-----|
| NativeAgentRuntimeV2 | 585 | 600 |
| LangGraphParityRuntimeV2 | 580 | 600 |

## Scenario winners

| Scenario | Winner |
|----------|--------|
| direct_assistant | tie |
| brain_evidence | tie |
| write_intent_blocked | tie |
| mixed_reasoning | tie |
| tool_specific_request | native |
| unsafe_or_protected_write | langgraph_parity |

## Key findings

- No production wiring was changed. `/v2/chat/agent` still routes to `NativeAgentRuntimeV2`.
- LangGraph parity graph executes all 14 nodes and produces metadata, trace, and checkpoint artifacts.
- The parity runtime correctly blocks unsafe writes via its governance gate.
- Native V2 routes tool-specific and mixed-reasoning queries more accurately because it uses `AgentV2IntentAdapter`, `planner.build_plan`, and the native finalizer.
- Native V2 loses points on `unsafe_or_protected_write` because it routes the message to `brain_evidence` rather than treating it as a blocked operational write.

## Decision

**A. Continue toward deeper LangGraph parity**

## Recommended next action

Reuse the full `AgentV2IntentAdapter`, `context_assembler`, and `planner.build_plan` inside LangGraph nodes without switching the default runtime. Future work should also evaluate `graph.stream` and an opt-in backend flag.

## Files created

- `tests/smoke/test_brain_native_vs_langgraph_parity_benchmark_06.py`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/native_results.json`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/langgraph_parity_results.json`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/comparison_scorecard.json`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/comparison_scorecard.md`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/final_report.json`
- `tmp_agent/front_brain_native_vs_langgraph_parity_benchmark_06/final_report.md`

## Validation

- Tests run: 21 (all passed)
- Unit/security tests: 3 (all passed)
- Guard result: SAFE
- Source files modified: none
- Production wiring changed: false
