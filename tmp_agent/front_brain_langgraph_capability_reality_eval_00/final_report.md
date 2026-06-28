# FRONT-BRAIN-LANGGRAPH-CAPABILITY-REALITY-EVAL-00 — Final Report

**Front:** FRONT-BRAIN-LANGGRAPH-CAPABILITY-REALITY-EVAL-00  
**Baseline:** 1fb1383e  
**Branch:** codex/own-capital-sustainable-return  
**Date:** 2026-06-28  
**Classification:** PARTIAL_CAPABILITY_USE

---

## Executive Summary

The evaluation confirms that **LangGraph is NOT the active production runtime** for chat/agent paths. The active V2 runtime is `NativeAgentRuntimeV2`, a native Python orchestration layer that provides durable execution, governance, tool gateway, and evidence routing — but final synthesis is a single LLM call (finalizer with linear fallback). Legacy `/chat` and OpenAI-compatible `/v1/chat/completions` bypass V2 entirely.

**Key Finding:** Code for LangGraph exists (`langgraph_runtime.py`) but is a dead/optional backend. No `graph.invoke/stream/astream` or LangGraph checkpointer runs in production.

---

## What Each Path Actually Uses

| Path | Runtime | LangGraph | Memory/FAISS | Tools | Governance | Trace |
|------|---------|-----------|--------------|-------|------------|-------|
| `POST /chat` | Legacy (BrainSession) | ❌ | Opt-in only (curated lookup) | Tool01, GAK, AgentLoop | ExecutionGate (P2/P3) | ✅ 7 events/req |
| `POST /v2/chat/agent` | NativeAgentRuntimeV2 | ❌ | Via ToolGatewayV2 (semantic_retrieve) | ToolGatewayV2 | ToolGatewayV2 → governance.py | ✅ TraceStore per run |
| `POST /agent` (legacy) | AgentLoop | ❌ | SemanticMemory (if available) | ToolExecutor | Tool wrappers → ExecutionGate | ❌ |
| `POST /v1/chat/completions` | Legacy (handle_user_message) | ❌ | Blocked | Blocked | Blocked | ❌ |

---

## Capability Scorecard

| Dimension | Score | Evidence |
|-----------|-------|----------|
| capability_wired_score | 75 | V2 components exist and wired in api_adapter |
| runtime_activation_score | 55 | Only V2 agent path activates them; chat does not |
| traceability_score | 70 | Custom trace events in both paths; not LangGraph streaming |
| memory_use_score | 55 | Short-term in both; long-term only in V2 agent routes |
| retrieval_use_score | 55 | FAISS via semantic_retrieve tool only in V2 operational_agent |
| tool_use_score | 70 | Real tools with governance in both paths |
| governance_score | 90 | ExecutionGate + signed approvals (06C) active everywhere |
| **LangGraph_real_use_score** | **0** | LangGraphAgentRuntimeV2 never instantiated |
| chat_quality_score | 45 | Fastpath-heavy; most queries skip tools/memory |
| reliability_score | 60 | Timeouts, fallbacks exist but no evaluator |

---

## Evidence for Classification: PARTIAL_CAPABILITY_USE

**Why not FULLY_USES:**
- LangGraph is 0% active (scorecard 0)
- Legacy `/chat` (primary UI path) skips V2, LangGraph, auto-FAISS
- OpenAI-compatible endpoint is legacy-only
- No evaluator, no LLM-based planner, no model arbitration

**Why not THIN_WRAPPER:**
- V2 agent path (`/v2/chat/agent`, `/v2/agent/*`) has real durable execution, governance, tool gateway, evidence routing, per-run artifacts
- Signed approvals work (06C hardened)
- Trace infrastructure exists and emits

**Why not NOT_TESTABLE:**
- All probes ran successfully via static analysis + module imports
- No server required; read-only probes only

---

## Static Inventory Summary (16 capabilities)

| Capability | Wired | Chat Activated | Agent Activated |
|------------|-------|----------------|-----------------|
| LangGraph orchestration | ✅ code | ❌ | ❌ |
| Durable execution/checkpointing | ✅ | ❌ | ✅ (file-based) |
| Short-term conversation state | ✅ | ✅ | ✅ |
| Long-term semantic memory | ✅ | ⚠️ opt-in | ✅ |
| FAISS retrieval | ✅ | ❌ | ✅ (via tool) |
| Evidence/source routing | ✅ | ❌ | ✅ (intent adapter) |
| Planner/evaluator | ✅ planner | ❌ | ⚠️ deterministic only |
| Tool execution | ✅ | ✅ | ✅ |
| Governance gate | ✅ | ✅ | ✅ |
| Signed approvals | ✅ | ✅ | ✅ |
| Model fallback/arbitration | ✅ linear | ✅ linear | ✅ linear |
| Visual trace | ✅ | ✅ | ✅ |
| Streaming | ⚠️ legacy only | ⚠️ SSE | ❌ |
| UI chat path | ✅ | ✅ | N/A |
| API agent path | ✅ | N/A | ✅ |
| OpenAI-compatible API | ✅ | ⚠️ legacy | N/A |

---

## Runtime Probe Results (12/12 passed)

All read-only probes passed:
- Main app imports, 251 routes enumerated
- LangGraph file exists with StateGraph but not instantiated
- Runtime selector returns `NativeAgentRuntimeV2`
- Legacy `/chat` calls `handle_user_message` → `BrainSession`
- `/v2/chat/agent` uses `NativeAgentRuntimeV2.execute_run()`
- OpenAI-compatible delegates to legacy path
- `/gate/approve` hardened (06C): token, fail-closed, signed validation, token stripping
- `MemoryGatewayV2`, `ToolGatewayV2` (call method), signed approvals, trace infra all importable
- Probe functions contain no mutation patterns

---

## Comparison to Baselines

| System | Capability Score | Notes |
|--------|------------------|-------|
| Direct LLM (OpenAI-compat) | 30 | Legacy path only; no tools, memory, governance |
| Standard Tool Agent (Legacy `/agent`) | 50 | AgentLoop + tools + governance; no durable state |
| **Current V2 Agent Path** | **75** | Durable runs, governance, tool gateway, evidence; single-LLM synthesis |
| LangGraph Ideal | 100 | StateGraph, checkpointer, streaming, HITL, evaluator nodes |

---

## LangSmith / LangGraph Evaluation Suite

**Status: ABSENT**
- No LangSmith tracing integration
- No LangGraph evaluation suite (no `langsmith.evaluation`, no dataset runs)
- No CI integration for agent quality regression
- Custom trace events exist but not compatible with LangSmith schema

---

## Recommended Next Action: **B. pause roadmap and wire missing runtime capabilities**

### Priority Wiring Tasks:
1. **Activate V2 runtime for `/chat`** — Replace legacy `BrainSession.chat` with `NativeAgentRuntimeV2` path so UI users get durable runs, auto-FAISS, evidence routing
2. **Wire LangGraph as default backend** — Make `LangGraphAgentRuntimeV2` the default return of `get_agent_runtime_v2()` with real StateGraph (plan→retrieve→tools→final), checkpointer, streaming
3. **Add evaluator node** — LLM-based verification step in graph
4. **Integrate LangSmith** — Tracing + evaluation datasets for regression testing
5. **Fix OpenAI-compatible path** — Optionally route `/v1/chat/completions` through V2 for parity

### Remaining Gaps (for 06D+):
- `AGENTV2_APPROVED_` weak prefix hardening (06D)
- promote/rollback `change_id` path resolution (06E)
- LLM-based planner (currently deterministic keyword)
- Per-thread checkpointing with `thread_id`/`configurable`

---

## Git Safety

- Only evaluation files created/modified:
  - `tests/smoke/test_brain_langgraph_capability_reality_eval_00.py`
  - `tmp_agent/front_brain_langgraph_capability_reality_eval_00/*.{json,md}` (6 files)
- No source runtime modifications
- No memory/FAISS/trading/.env changes
- Guard: SAFE
- `git diff --name-status`: only new eval files

---

## Validation Status

| Check | Status |
|-------|--------|
| py_compile test file | ✅ |
| pytest smoke test | ✅ 12/12 passed |
| py_compile main.py | ✅ |
| py_compile execution_gate.py | ✅ |
| pytest 06c gate tests | ✅ |
| git_hygiene guard | ✅ SAFE |

---

**Decision:** Do NOT continue to 06D. Pause roadmap and wire V2/LangGraph capabilities into primary chat/agent paths first.