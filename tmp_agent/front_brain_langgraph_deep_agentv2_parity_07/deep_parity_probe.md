# Deep Parity Probe: FRONT-BRAIN-LANGGRAPH-DEEP-AGENTV2-PARITY-07

## Summary

Deep parity probe for `LangGraphParityRuntimeV2` after integrating Native V2 helpers. All scenarios run isolated with `tmp_path` run_root.

## Scenarios

| Scenario | Intent Route | Classification | Tools Considered | Tools Executed | Tools Blocked | Native Helpers Used |
|----------|--------------|----------------|------------------|----------------|---------------|---------------------|
| direct_assistant | direct_assistant | direct_assistant | 0 | 0 | 0 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers |
| brain_evidence | brain_evidence | endpoint_probe | 12 | 12 | 1 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers, MemoryGatewayV2.semantic_retrieve, AgentV2IntentAdapter.get_evidence_sources, planner.build_plan |
| tool_specific_request | brain_evidence | repo_audit | 10 | 10 | 1 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers, MemoryGatewayV2.semantic_retrieve, AgentV2IntentAdapter.get_evidence_sources, planner.build_plan |
| write_intent_blocked | operational_agent | approval_required_write | 1 | 1 | 1 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers, MemoryGatewayV2.semantic_retrieve, planner.build_plan |
| protected_governance_write | brain_evidence | memory_question | 9 | 9 | 0 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers, MemoryGatewayV2.semantic_retrieve, AgentV2IntentAdapter.get_evidence_sources, planner.build_plan |
| mixed_reasoning | brain_evidence | general_reasoning | 11 | 11 | 1 | AgentV2IntentAdapter.select_route, context_assembler.pure_helpers, MemoryGatewayV2.semantic_retrieve, AgentV2IntentAdapter.get_evidence_sources, planner.build_plan |

## Key findings

- Intent routing now uses `AgentV2IntentAdapter.select_route()` for every scenario.
- Evidence routing uses `AgentV2IntentAdapter.get_evidence_sources()` for brain evidence routes.
- Planning uses `planner.build_plan()` for non-direct routes.
- Context assembly uses safe pure helpers only; full `assemble_recent_context` is skipped because it scans production RUN_ROOT.
- Tool execution uses `ToolGatewayV2.call()` with explicit unknown-tool skip.
- Memory retrieval uses `MemoryGatewayV2.semantic_retrieve()` read-only.
- Governance correctly escalates/blocks write intents.
- No live LLM called in tests.
- No production wiring, runtime selector, API adapter, or default route changed.
