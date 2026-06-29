# Parity Readiness Matrix: FRONT-BRAIN-LANGGRAPH-FAIR-BENCHMARK-READINESS-GATE-08A

## Decision

**ready_for_final_benchmark: true**

There are no blockers for a fair benchmark of comparable Agent V2 functionality.

## Summary

| Category | Count |
|----------|-------|
| Equivalent | 9 |
| Comparable enough for benchmark | 5 |
| Intentionally different | 1 |
| Production-wiring only | 1 |
| Non-comparable in isolated runtime | 1 |
| Blocking for fair benchmark | 0 |

## Matrix

| Capability | Native Component | LangGraph Component | Status | Blocking |
|------------|------------------|---------------------|--------|----------|
| intent routing | AgentV2IntentAdapter.select_route | AgentV2IntentAdapter.select_route in _intent_node | equivalent | no |
| evidence routing | AgentV2IntentAdapter.get_evidence_sources | AgentV2IntentAdapter.get_evidence_sources in _evidence_routing_node | equivalent | no |
| planner.build_plan | planner.build_plan | planner.build_plan in _planner_node | equivalent | no |
| context assembly | context_assembler.assemble_recent_context over production RUN_ROOT | _assemble_isolated_context over self.run_root | comparable_enough_for_benchmark | no |
| governance | mode_requires_escalation / WRITE_TOOL_NAMES | mode_requires_escalation / WRITE_TOOL_NAMES in graph nodes | equivalent | no |
| read-only tool execution | ToolGatewayV2.call | ToolGatewayV2.call in _tool_execution_node | equivalent | no |
| write blocking | ToolGatewayV2.call blocks write tools | Pre-check + ToolGatewayV2.call | equivalent | no |
| memory retrieval | MemoryGatewayV2.semantic_retrieve | MemoryGatewayV2.semantic_retrieve in _memory_retrieval_node | equivalent | no |
| finalizer input schema | build_finalizer_prompt | _build_finalizer_input | comparable_enough_for_benchmark | no |
| finalizer execution | finalize_agent_run (calls live LLM) | injected_finalizer or deterministic_parity_finalizer (LLM-safe) | intentionally_different | no |
| evaluator | implicit in execute_run | _evaluator_node | comparable_enough_for_benchmark | no |
| provider metadata | FinalizerMetadata / provider_used / model_used | provider_metadata with parity source and live_llm_called | comparable_enough_for_benchmark | no |
| capability metadata | _build_capability_metadata in api_adapter.py | _build_capability_metadata in LangGraphParityRuntimeV2 | equivalent | no |
| trace | TraceStore under RUN_ROOT | TraceStore under self.run_root | equivalent | no |
| checkpoint | CheckpointStore under RUN_ROOT | CheckpointStore under self.run_root | equivalent | no |
| stream observability | graph.stream or FastAPI streaming adapter | graph_stream_probe proves graph.stream works | comparable_enough_for_benchmark | no |
| backend flag readiness | runtime.py returns NativeAgentRuntimeV2 | backend_flag_readiness_probe reports future wiring requirements | production_wiring_only | no |
| production wiring isolation | runtime.py, api_adapter.py, main.py | LangGraphParityRuntimeV2 is not imported by any production file | equivalent | no |

## Scenario evidence

| Scenario | Intent Route | Classification | Finalizer Input Complete |
|----------|--------------|----------------|--------------------------|
| direct_assistant | direct_assistant | direct_assistant | true |
| brain_evidence | brain_evidence | endpoint_probe | true |
| tool_request | brain_evidence | repo_audit | true |
| write_intent_blocked | operational_agent | approval_required_write | true |
| protected_write | brain_evidence | memory_question | true |
| memory_question | brain_evidence | memory_question | true |

## Stream probe

- stream_available: true
- stream_event_count: 15
- production_streaming_wiring_changed: false

## Backend flag readiness

- can_support_opt_in_backend_flag: true
- production_wiring_changed: false
- default_runtime_unchanged: true
- risk_level: medium
- blockers:
  - No AGENT_V2_BACKEND env flag parsing implemented
  - No runtime.py branch to LangGraphParityRuntimeV2
  - No streaming response adapter for /v2/chat/agent

## Recommended next action

**A. Run final full-parity benchmark**

## Remaining non-blocking items

- Non-comparable: finalizer execution (live LLM synthesis quality not comparable in isolated tests)
- Deferred: AGENT_V2_BACKEND flag parsing, runtime.py branch, production streaming adapter
