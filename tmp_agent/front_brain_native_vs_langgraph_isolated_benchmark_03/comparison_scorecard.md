# Comparison Scorecard: Native V2 vs LangGraph (Isolated Benchmark)

**Date:** 2026-06-29  
**Branch:** `codex/own-capital-sustainable-return`  
**Baseline:** `c58e2a6`

## Summary

| Runtime | Normalized Score | Classification | Decision |
|---------|------------------|----------------|----------|
| Native V2 | 80 / 100 | `PRODUCTION_CANONICAL` | **KEEP_NATIVE_V2_AND_IMPROVE** |
| LangGraph | 19 / 100 | `LANGGRAPH_EXECUTABLE_ISOLATED` | Not production-ready |

## Dimension scores

| Dimension | Native V2 | LangGraph |
|-----------|-----------|-----------|
| Runtime importability | 100 | 70 |
| Route integration | 100 | 0 |
| Production readiness | 85 | 20 |
| Capability metadata | 100 | 0 |
| Traceability | 80 | 10 |
| Checkpointing | 75 | 10 |
| MemoryGatewayV2 use | 90 | 0 |
| ToolGatewayV2 use | 90 | 0 |
| Governance preservation | 95 | 0 |
| Testability | 90 | 60 |
| Operational risk | 85 | 30 |
| Implementation cost | 90 | 25 |
| Expected agent quality gain | 60 | 20 |
| **Total** | **1040 / 1300** | **245 / 1300** |

## Evidence

### Native V2

- Active backend for `POST /v2/chat/agent` (`NativeAgentRuntimeV2`).
- Returns `capability_metadata` with all 14 required keys.
- Enforces governance for write intents in `read_only` mode.
- Uses `MemoryGatewayV2`, `ToolGatewayV2`, `TraceStore`, and per-run checkpoint files.

### LangGraph

- `LangGraphAgentRuntimeV2` exists in `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_runtime.py`.
- `langgraph` package is installed; class imports and instantiates successfully.
- Toy `StateGraph` with `plan/retrieve/tools/final` nodes compiles and executes via `graph_probe()`.
- **No production wiring**: `runtime.py` does not import it; `/v2/chat/agent` does not use it.
- **No subsystems wired**: no `MemoryGatewayV2`, `ToolGatewayV2`, governance, trace, checkpointer, or streaming.
- **No capability metadata** produced.

## Decision rationale

1. Native V2 already satisfies the production path and exposes observable capability metadata.
2. LangGraph runs only in isolation; it is not integrated with any production route or subsystem.
3. LangGraph does not exceed Native V2 on any measured dimension.
4. Wiring LangGraph now would require substantial new code, risk governance regression, and offer no proven quality improvement.

## Abstract potential

LangGraph's theoretical potential for cyclic graphs, human-in-the-loop, and streaming is acknowledged as ~70/100, but it is **not realized** in the current codebase and therefore does not affect the production decision.

## Decision

**`KEEP_NATIVE_V2_AND_IMPROVE`**
