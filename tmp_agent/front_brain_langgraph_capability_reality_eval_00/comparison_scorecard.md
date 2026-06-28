# Comparison Scorecard — FRONT-BRAIN-LANGGRAPH-CAPABILITY-REALITY-EVAL-00

**Baseline:** 1fb1383e  
**Branch:** codex/own-capital-sustainable-return

---

## Score Summary

| Dimension | Score (0-100) | Status |
|-----------|---------------|--------|
| capability_wired_score | 75 | Code exists for most capabilities |
| runtime_activation_score | 55 | Only partially activated at runtime |
| traceability_score | 70 | Visual trace active in both paths |
| memory_use_score | 55 | Short-term yes; long-term route-dependent |
| retrieval_use_score | 55 | FAISS only in V2 operational_agent |
| tool_use_score | 70 | Tools real and governed in both paths |
| governance_score | 90 | Gate enforced, signed approvals working |
| **LangGraph_real_use_score** | **0** | **LangGraph NOT active at runtime** |
| chat_quality_score | 45 | Fastpath-heavy, limited reasoning depth |
| reliability_score | 60 | Timeouts, fallback chains present |
| latency_observed_seconds | N/A | Not measured |
| failure_rate | N/A | Not measured |
| timeout_rate | N/A | Not measured |

---

## Classification: **PARTIAL_CAPABILITY_USE**

### Reason
- **Not FULL**: LangGraph is not active at runtime; V2 agent uses native runtime with single-LLM-call synthesis
- **Not THIN_WRAPPER**: NativeAgentRuntimeV2, ToolGatewayV2, MemoryGatewayV2, governance, signed approvals, traces, and durable artifacts are real and active
- **Not NOT_TESTABLE**: All probes ran successfully; endpoints present
- **Not UNSAFE**: No mutations performed

---

## Evidence for Classification

### What Is Wired and Activated

| Capability | Active In | Notes |
|------------|-----------|-------|
| Durable execution/checkpointing | V2 (`/v2/chat/agent`, `/v2/agent/*`) | Per-run JSON artifacts (run.json, checkpoint.json, trace.jsonl) |
| Short-term conversation state | Legacy `/chat`, V2 | Token-aware truncation in both |
| Long-term semantic memory | V2 (`operational_agent`, `brain_evidence`) | Via `MemoryGatewayV2.semantic_retrieve()` |
| FAISS retrieval | V2 only | `semantic_retrieve` tool in `ToolGatewayV2` |
| Evidence/source routing | V2 (`brain_evidence`, `mixed_brain_reasoning`) | `AgentV2IntentAdapter.get_evidence_sources()` |
| Planner | V2 (`operational_agent`) | Deterministic keyword-based (`planner.py`) |
| Tool execution | Legacy + V2 | `ToolExecutor` / `ToolGatewayV2` with governance |
| Governance gate | Legacy + V2 | `ExecutionGate.check()` in tool wrappers |
| Signed approvals | Legacy + V2 | P3/protected paths require token (06C) |
| Visual trace | Legacy + V2 | 7 events/request in legacy; `TraceStore` per run in V2 |
| Streaming | Legacy `/chat/stream` only | V2 agent path has no streaming |
| OpenAI-compatible API | Legacy only | Thin wrapper over `handle_user_message` |

### What Is Wired But Not Activated at Runtime

| Capability | Code Location | Why Not Active |
|------------|---------------|----------------|
| LangGraph graph orchestration | `langgraph_runtime.py` | `LangGraphAgentRuntimeV2` never instantiated; `runtime.py` returns `NativeAgentRuntimeV2` |
| LangGraph checkpointing | `checkpoints.py` (file-based) | Per-run JSON, not LangGraph checkpointer |
| Per-thread checkpointing | N/A | No `thread_id`/`configurable` mechanism |
| LLM-based planner | `planner.py` | Deterministic keyword classification |
| LLM-based evaluator | N/A | No separate evaluator node |
| Model arbitration | `finalizer.py` linear fallback | Simple chain: KIMI → DeepSeek → gpt-oss → KIMI-k2.5 |
| Streaming in V2 | N/A | `api_adapter.py` has no streaming endpoints |
| FAISS in legacy chat | N/A | Only opt-in curated lookup |

### What Is Missing vs LangGraph Ideal

- No `StateGraph` with `graph.invoke/stream/astream`
- No `MemorySaver`/`SqliteSaver`/`PostgresSaver` checkpointer
- No `thread_id` / `configurable` for conversation resumption
- No human-in-the-loop interrupts (`interrupt()`)
- No evaluator/judge nodes in graph
- No LangSmith tracing integration

---

## Comparison Against Baselines

| System | Score | Notes |
|--------|-------|-------|
| **Direct LLM** (OpenAI-compat path) | 30 | Delegates to legacy; no tools/memory/governance |
| **Standard Tool Agent** (Legacy `/agent`) | 50 | AgentLoop + tools + governance; no durable state |
| **V2 Native Agent** (`/v2/chat/agent`) | 75 | Durable runs, governance, tool gateway, evidence routing; single-LLM synthesis |
| **LangGraph Ideal** | 100 | Full orchestration, checkpointer, streaming, HITL, evaluator |

---

## Detailed Score Justifications

### capability_wired_score: 75
Most components exist in code: V2 runtime, tool gateway, memory gateway, planner, finalizer, governance, trace. Missing: LLM planner, evaluator, LangGraph orchestration.

### runtime_activation_score: 55
Legacy `/chat` resolves ~70% via fastpaths (no tools, no retrieval). V2 activates tools/evidence only for `operational_agent`/`brain_evidence` routes. OpenAI-compat bypasses V2 entirely.

### traceability_score: 70
Legacy emits 7 events/request. V2 writes `trace.jsonl` per run. No LangSmith export.

### memory_use_score: 55
Short-term works in both. Long-term (FAISS) only in V2 specific routes. Not auto-injected in legacy chat.

### retrieval_use_score: 55
FAISS retrieval callable via `semantic_retrieve` tool but only in V2 `operational_agent`/`brain_evidence`. Legacy chat has no auto-retrieval.

### tool_use_score: 70
100+ tools real and governed. V2 gateway validates capabilities. Legacy uses direct `ToolExecutor`.

### governance_score: 90
`ExecutionGate` enforced in all paths. Signed approvals for P3/protected. 06C hardened `/gate/approve`.

### LangGraph_real_use_score: 0
**LangGraph is NOT used at runtime.** Code exists but dead. Active runtime is `NativeAgentRuntimeV2`.

### chat_quality_score: 45
Legacy chat fastpath-heavy; limited reasoning depth. V2 agent single-LLM synthesis.

### reliability_score: 60
Timeout guards (30s chat, 35s agent). Fallback chains in finalizer. AgentLoop has retry logic.

---

## Recommended Next Action

**B. pause roadmap and wire missing runtime capabilities**

Priority fixes before 06D:
1. Wire `LangGraphAgentRuntimeV2` as default in `runtime.py` (or remove dead code)
2. Add LangGraph checkpointer (SQLite/Postgres) for durable thread resumption
3. Implement LLM-based planner node in graph
4. Add evaluator/judge node for output quality
5. Enable streaming in V2 agent path
6. Auto-inject FAISS retrieval in legacy `/chat` (opt-out)
7. Integrate LangSmith tracing

---

## Remaining Gaps

1. LangGraph not active at runtime (dead code in `langgraph_runtime.py`)
2. No per-thread checkpointing/resumption
3. No human-in-the-loop interrupts
4. No evaluator node
5. Model fallback is linear chain, not arbitration
6. V2 agent path has no streaming
7. Legacy `/chat` does not auto-retrieve FAISS
8. OpenAI-compatible endpoint bypasses V2 entirely
9. No LangSmith evaluation suite integration