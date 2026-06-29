# LangGraph Parity Prototype Blueprint

**Front:** FRONT-BRAIN-LANGGRAPH-PARITY-PROTOTYPE-BLUEPRINT-04  
**Branch:** `codex/own-capital-sustainable-return`  
**Starting HEAD:** `99d9197`  
**Status:** blueprint only — no source edits

## Goal

Design a future LangGraph-based runtime that reaches **production parity** with the current `NativeAgentRuntimeV2`, while keeping Native V2 canonical and `/v2/chat/agent` unchanged in this front.

## Context

- `NativeAgentRuntimeV2` is the active backend for `/v2/chat/agent`.
- It returns full `capability_metadata` with 14 required keys, preserves governance, uses `ToolGatewayV2`/`MemoryGatewayV2`, writes per-run traces/checkpoints, and supports adaptive expansion.
- `LangGraphAgentRuntimeV2` exists but is isolated: it compiles a toy `StateGraph` and has no production wiring, governance, memory, tools, trace, checkpointing, or capability metadata.
- Front 03 decision: `KEEP_NATIVE_V2_AND_IMPROVE` — but strategic direction is to prepare a LangGraph parity prototype blueprint.

## Design principles

1. **Native V2 remains canonical.** LangGraph is a separately compilable parity target, not a replacement.
2. **Governance, tool, memory, trace, and checkpoint contracts preserved exactly.**
3. **`capability_metadata` returned by `/v2/chat/agent` must keep the same keys and semantics.**
4. **No production wiring changes in this front.** `/v2/chat/agent` continues to call `get_agent_runtime_v2() -> NativeAgentRuntimeV2`.
5. **Future implementation is flag-gated and reversible in one commit.**

## Proposed LangGraph state graph

### State schema

```python
{
    "run_id": str,
    "goal": str,
    "mode": str,
    "user_id": str,
    "status": str,
    "classification": str | None,
    "intent_route": str | None,
    "intent_detected": str | None,
    "intent_confidence": float | None,
    "evidence_sources": list[dict] | None,
    "plan": list[dict],
    "metadata": dict,
    "results": list[dict],
    "memory_hits": list[dict],
    "blocked_tools": list[str],
    "mode_escalation_required": bool,
    "required_permission": str | None,
    "confirmation_id": str | None,
    "final_answer": str | None,
    "provider_metadata": dict | None,
    "session_context": dict | None,
    "trace_events_count": int,
    "capability_metadata": dict | None,
}
```

### Nodes

| Node | Native equivalent | Responsibility |
|------|-------------------|----------------|
| `create_run` | `runtime_core.create_run` | Validate mode, hash `run_id`, persist `run.json`, save checkpoint, emit trace. |
| `assemble_context` | `context_assembly.assemble_recent_context` | Load recent user turns and follow-up signals. |
| `select_route` | `intent_routing.select_route` | Detect intent, choose route, inherit context for follow-ups. |
| `build_plan` | `planning.build_plan` + `evidence_engineering.build_evidence_plan` | Build deterministic/evidence plan based on route. |
| `check_governance` | `governance.mode_requires_escalation` | Detect write-intent escalation, set `confirmation_id`. |
| `execute_tools` | `tool_gateway.*` + `_execute_step` | Execute planned tools, populate `results` and `memory_hits`. |
| `adaptive_expansion` | `evidence_engineering.adaptive_expansion` | Append fallback tools when grep/semantic hits are empty. |
| `finalize` | `finalization.finalize_agent_run` + `api_adapter._build_capability_metadata` | Generate final answer and identical capability metadata. |
| `persist_and_trace` | `checkpointing.save_checkpoint` + `tracing.append_trace_event` | Persist `run.json`, `checkpoint.json`, `trace.jsonl`. |

### Conditional route table

- **direct_assistant** — skip planner/tools; finalize with `template_override='direct_assistant'`.
- **promotion_adapter_dry_run** — build single `promotion_candidate_validate` step, execute, finalize.
- **brain_evidence** — build evidence plan, execute, adapt, finalize with `template_override='brain_evidence'`.
- **mixed_brain_reasoning** — add generic reasoning step + evidence plan, execute, adapt, finalize.
- **operational_agent** — use planner, optionally enrich with evidence sources, execute, adapt, finalize.

## Component wiring spec

### Memory gateway

- Use existing `MemoryGatewayV2`.
- Invoke `semantic_retrieve` inside `execute_tools` for `tool_name='semantic_retrieve'`.
- Preserve FAISS + jsonl keyword fallback, `domain_gate`, `top_k`, and `write_performed=False`.

### Tool gateway

- Use existing `ToolGatewayV2`.
- Construct `ToolCallRequest` from plan steps and call `tools.call(request, mode=state.mode)`.
- Preserve forbidden-path blocking, write-tool gating, and localhost-only route probe.

### Governance

- Call `validate_mode`, `mode_requires_escalation`, `contains_forbidden_request_fields`.
- Keep `write_allowed` check inside any write-tool execution.

### Trace

- Wrap every node with `TraceStore.append` on entry and exit.
- Sanitize payloads with `RAW_COT_MARKERS`.

### Checkpoint

- Primary persistence stays `CheckpointStore` JSON.
- LangGraph `MemorySaver`/`SqliteSaver` may be added only as a secondary resumability layer.

### Finalizer

- Reuse `finalize_agent_run` and `api_adapter._build_capability_metadata` verbatim.
- Preserve provider fallback chain, COT blocking, and template overrides.

## Capability metadata derivation

Reuse `api_adapter._build_capability_metadata` with the same mapping:

| Key | Source in LangGraph state |
|-----|----------------------------|
| `memory_used` | any plan step `tool_name == 'semantic_retrieve'` |
| `retrieval_attempted` | any plan step `tool_name == 'semantic_retrieve'` |
| `retrieval_no_results` | any semantic step has empty `hits` |
| `retrieval_skipped` | not attempted and route not direct/promotion |
| `planner_used` | `bool(plan)` with tool steps |
| `evidence_routed` | `bool(evidence_sources)` |
| `evidence_sources_count` | `len(evidence_sources or [])` |
| `tools_considered` | tool steps count |
| `tools_executed` | completed/failed/blocked steps count |
| `tools_blocked` | `len(blocked_tools)` |
| `governance_checked` | `mode_escalation_required or blocked_tools` |
| `intent_route` | `state.intent_route` |
| `classification` | `state.classification` |
| `trace_events_count` | `len(TraceStore.read(run_id))` |

## Implementation phases (future work)

1. **Flag-gated skeleton** — create `langgraph_parity_runtime.py` with a compiling `StateGraph`.
2. **Tool and memory wiring** — implement `execute_tools` with `ToolGatewayV2` and `MemoryGatewayV2`.
3. **Intent, planning, evidence parity** — wrap `AgentV2IntentAdapter`, `build_plan`, `_build_evidence_plan`, adaptive expansion.
4. **Finalizer and capability metadata parity** — reuse native finalizer and metadata builder.
5. **Trace and checkpoint parity** — persist identical `run.json`, `checkpoint.json`, `trace.jsonl`.
6. **Isolated smoke parity test** — create a smoke test comparing native and parity outputs.
7. **Optional route wiring behind flag** — allow `runtime.py` to select parity runtime only with `AGENT_V2_BACKEND=langgraph_parity`; default stays native.

## Risk analysis

| Risk | Mitigation |
|------|------------|
| LangGraph state diverges from native `run.json` schema. | Mandate native persistence after every node; LangGraph state is transient execution context only. |
| Governance bypass through node ordering. | Every tool call goes through `ToolGatewayV2.call(mode=...)`; governance checks before node entry. |
| Capability metadata drift. | Share `api_adapter._build_capability_metadata`; add smoke parity assertions. |
| Checkpointer writes to unexpected paths. | Use `MemorySaver` for prototype; `SqliteSaver` only in explicit gitignored path. |
| Adaptive expansion loops. | Mirror native single-pass expansion with bounded retries. |

## Files touched in future implementation

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` (new)
- `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py` (only for optional flag wiring)
- `tests/smoke/test_brain_langgraph_parity_runtime_05.py` (new)

## Files untouched in this front

All source files remain read-only, including `native_runtime.py`, `langgraph_runtime.py`, `runtime.py`, `api_adapter.py`, governance, memory, tool, finalizer, intent, planner, context, trace, checkpoint, and `.env`.
