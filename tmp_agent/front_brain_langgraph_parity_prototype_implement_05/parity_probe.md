# Parity Probe Report

**Front:** FRONT-BRAIN-LANGGRAPH-PARITY-PROTOTYPE-IMPLEMENT-05

## Runtime selector

- backend: native_runtime
- class: NativeAgentRuntimeV2

## Production route check

- langgraph_parity_runtime imported in api_adapter.py: false
- langgraph_parity_runtime imported in runtime.py: false
- Native V2 active in runtime selector: true

## Graph probe

```json
{
  "ok": true,
  "backend": "langgraph_parity",
  "langgraph_active": true,
  "nodes": [
    "start",
    "intent",
    "context_assembly",
    "memory_retrieval",
    "evidence_routing",
    "planner",
    "governance_gate",
    "tool_execution",
    "result_normalization",
    "finalizer",
    "evaluator",
    "repair_or_replan",
    "capability_metadata",
    "end"
  ]
}
```

## Direct assistant

- intent_route: direct_assistant
- classification: direct_assistant
- planner_used: false
- retrieval_skipped: false

## Brain evidence

- intent_route: brain_evidence
- classification: brain_evidence
- evidence_routed: true
- tools_executed: 3

## Write intent block

- mode_escalation_required: true
- tools_blocked: 1

## Sensitive path guard

- result: SAFE
