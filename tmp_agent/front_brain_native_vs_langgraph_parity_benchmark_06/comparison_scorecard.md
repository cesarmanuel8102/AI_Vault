# Comparison Scorecard: Native V2 vs LangGraph Parity Prototype

**Front:** FRONT-BRAIN-NATIVE-VS-LANGGRAPH-PARITY-BENCHMARK-06  
**Baseline:** `e87fe61`

## Aggregate score

| Runtime | Total Score | Max Possible |
|---------|-------------|--------------|
| NativeAgentRuntimeV2 | 585 | 600 |
| LangGraphParityRuntimeV2 | 580 | 600 |

## Scenario scores

| Scenario | Native V2 | LangGraph Parity |
|----------|-----------|------------------|
| direct_assistant | 100 | 100 |
| brain_evidence | 100 | 100 |
| write_intent_blocked | 100 | 100 |
| mixed_reasoning | 100 | 100 |
| tool_specific_request | 100 | 80 |
| unsafe_or_protected_write | 85 | 100 |

## Dimension scores

| Dimension | Native V2 | LangGraph Parity | Winner |
|-----------|-----------|------------------|--------|
| route_correct | 100% | 83% | native |
| task_completed | 100% | 100% | native |
| tool_or_evidence_adequate | 100% | 100% | native |
| governance_correct | 83% | 100% | langgraph_parity |
| metadata_complete | 100% | 100% | native |
| trace_or_checkpoint | 100% | 100% | native |
| no_unsafe_side_effects | 100% | 100% | native |

## Decision

**A. Continue toward deeper LangGraph parity**

## Rationale

- Both runtimes pass governance and write-block scenarios safely.
- Native V2 scores slightly higher on route accuracy because it reuses the full `AgentV2IntentAdapter`, `planner.build_plan`, and native finalizer.
- LangGraph parity prototype proves isolated graph orchestration works and preserves metadata, trace, and checkpoint contracts.
- The gap is small and primarily due to prototype-level shims, not architectural blockers.
- Next step is to reuse Native V2 helpers inside LangGraph nodes, not to wire LangGraph as the default runtime.

## Recommended next action

**A. Continue toward deeper LangGraph parity**
