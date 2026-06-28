# FRONT-BRAIN-LANGGRAPH-CAPABILITY-REALITY-EVAL-00 — Static Capability Inventory

**Baseline:** 1fb1383e  
**Front:** FRONT-BRAIN-LANGGRAPH-CAPABILITY-REALITY-EVAL-00

---

## Summary Table

| # | Capability | Code Exists | Called from Chat | Called from Agent | Risk of Facade |
|---|------------|-------------|------------------|-------------------|----------------|
| 1 | LangGraph graph/state orchestration | ✅ | ❌ | ❌ | HIGH |
| 2 | Durable execution/checkpointing | ✅ | ✅ | ✅ | LOW |
| 3 | Short-term conversation state | ✅ | ✅ | ✅ | LOW |
| 4 | Long-term semantic memory | ✅ | ✅* | ✅ | MEDIUM |
| 5 | FAISS retrieval | ✅ | ✅* | ✅ | MEDIUM |
| 6 | Evidence/source routing | ✅ | ❌ | ✅ | LOW |
| 7 | Planner/evaluator | ✅ | ✅ | ✅ | MEDIUM |
| 8 | Tool execution | ✅ | ✅ | ✅ | LOW |
| 9 | Governance gate | ✅ | ✅ | ✅ | LOW |
| 10 | Signed approvals | ✅ | ✅ | ✅ | LOW |
| 11 | Model fallback/arbitration | ✅ | ✅ | ✅ | LOW |
| 12 | Visual trace | ✅ | ✅ | ✅ | LOW |
| 13 | Streaming | ✅ | ✅ | ❌ | MEDIUM |
| 14 | UI chat path (/chat) | ✅ | ✅ | ❌ | MEDIUM |
| 15 | API agent path (/v2/*) | ✅ | ❌ | ✅ | LOW |
| 16 | OpenAI-compatible API path | ✅ | ✅ | ❌ | HIGH |

*Legacy `/chat` does NOT automatically activate FAISS/semantic memory; only opt-in via curated lookup.

---

## Detailed Findings

### 1. LangGraph Graph/State Orchestration
- **Code location**: `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_runtime.py` (lines 13-24, 32)
- **Status**: Code exists but **dead/optional**. `runtime.py` returns `NativeAgentRuntimeV2` singleton. `api_adapter.py` uses `get_agent_runtime_v2()` → `NativeAgentRuntimeV2`. `LangGraphAgentRuntimeV2` is never instantiated in production routes.
- **Evidence**: StateGraph constructed with 4 nodes (plan→retrieve→tools→final) and compiled, but `graph.invoke({"probe": True})` only runs in `graph_probe()` method which is never called.
- **Risk**: HIGH — LangGraph claims in docs/status may mislead; actual runtime is native.

### 2. Durable Execution/Checkpointing
- **Code location**: `checkpoints.py`, `state.py`, `native_runtime.py` (lines 24-44)
- **Status**: **Active** at file-system level. Per-run directories under `tmp_agent/agent_kernel_v2/runs/<run_id>/` with `run.json`, `checkpoint.json`, `trace.jsonl`.
- **Evidence**: `CheckpointStore.save()` writes status/step_index/plan. `TraceStore` appends events. Created by `NativeAgentRuntimeV2._save_run()`.
- **Note**: Not LangGraph checkpointing (no thread_id/configurable saver). Each run independent; no resume from arbitrary step.

### 3. Short-Term Conversation State
- **Code location**: `session.py` (line 306, `MemoryManager`), `context_assembler.py` (line 77)
- **Status**: **Active** in both legacy `/chat` and V2 `/v2/chat/agent`.
- **Evidence**: `BrainSession.memory.get_context()` returns recent turns. V2 uses `assemble_recent_context()`. Token-aware truncation via `_truncate_to_budget()`.

### 4. Long-Term Semantic Memory
- **Code location**: `semantic_memory.py`, `semantic_memory_faiss.py`, `memory_gateway.py`, `tool_gateway.py`
- **Status**: **Exists but partially activated**. V2 routes (`operational_agent`, `brain_evidence`) call `MemoryGatewayV2.semantic_retrieve()` via `ToolGatewayV2`. Legacy `/chat` does NOT auto-inject; only opt-in `curated_lookup_readonly` fastpath.
- **Risk**: MEDIUM — Memory exists but not automatically used in chat path.

### 5. FAISS Retrieval
- **Code location**: `semantic_memory_faiss.py`, `memory_gateway.py` (line 41), `tool_gateway.py` (lines 24, 69-71)
- **Status**: **Real and callable** via V2 tool gateway. `MemoryGatewayV2.semantic_retrieve()` wraps `SemanticMemoryFAISS.search()`.
- **Risk**: MEDIUM — Not auto-activated for legacy chat.

### 6. Evidence/Source Routing
- **Code location**: `intent_adapter.py` (lines 478-489)
- **Status**: **Active in V2**. `AgentV2IntentAdapter.get_evidence_sources()` returns typed sources for `brain_evidence` and `mixed_brain_reasoning` routes. No separate `EvidenceSourceRouter` class.
- **Note**: Not used in legacy `/chat`.

### 7. Planner/Evaluator
- **Code location**: `planner.py` (deterministic keyword-based), `finalizer.py` (LLM synthesis with fallback), `loop.py` (ReasoningResult/VerificationResult dataclasses)
- **Status**: **Active but limited**. Planner is deterministic (not LLM). Finalizer is single LLM call with linear fallback. Legacy `AgentLoop` has verification step but no separate evaluator. V2 doesn't call planner for `direct_assistant`/`brain_evidence` routes.
- **Risk**: MEDIUM — "Planner" label overstates; it's rule-based classification.

### 8. Tool Execution
- **Code location**: `tools.py` (100+ tools), `tool_gateway.py`, `governance.py`
- **Status**: **Fully active** in both legacy and V2. `build_standard_executor()` returns `ToolExecutor`. V2 `ToolGatewayV2` validates against capability list, enforces governance, executes with `_bypass_gate` for approved items. Legacy uses `ToolExecutor` directly in `AgentLoop` and `_tool01_router`. Governance integration via `ExecutionGate.check()` in tool wrappers.
- **Risk**: LOW — Real tool execution with governance.

### 9. Governance Gate
- **Code location**: `execution_gate.py`, `signed_approvals.py`, `capability_policy.py`
- **Status**: **Fully active**. `ExecutionGate` singleton enforces P0-P3 risk, god mode, signed approvals. Tool wrappers call `gate.check()`. V2 `ToolGatewayV2` calls `governance.enforce_governance()`. `/gate/approve` hardened in 06C.
- **Risk**: LOW — Governance is enforced across all paths.

### 10. Signed Approvals
- **Code location**: `signed_approvals.py`, `execution_gate.py` (line 790)
- **Status**: **Active**. HMAC tokens with actor/scope/action/target/nonce. `ExecutionGate.approve()` verifies against `BRAIN_SIGNED_APPROVAL_SECRET`. Required for P3/protected paths. 06C endpoint checks `signed_approval_validated`.
- **Risk**: LOW — Implemented and tested (05, 06B, 06C tests pass).

### 11. Model Fallback/Arbitration
- **Code location**: `finalizer.py` (lines 8-9, 189-225), `llm.py`
- **Status**: **Active**. Linear fallback: `kimi-k2.6:cloud` → `deepseek-v4-pro:cloud` → `gpt-oss:120b-cloud` → `kimi-k2.5:cloud`. V2 routes all use `finalizer`; legacy uses `LLMManager` chain. No intelligent arbitration beyond linear fallback.
- **Risk**: LOW — Fallback works but is simple chain.

### 12. Visual Trace
- **Code location**: `main.py` (lines 4437-4559), `trace.py`, `schemas.py`
- **Status**: **Active**. Legacy `/chat` emits 7 trace events per request (lines 1822-1916). V2 `NativeAgentRuntimeV2` uses `TraceStore` writing `trace.jsonl` per run. Dashboard consumes traces.
- **Risk**: LOW — Custom event stream, not LangGraph streaming.

### 13. Streaming
- **Code location**: `main.py` (`/chat/stream` SSE endpoint)
- **Status**: **Legacy only**. V2 `api_adapter.py` has no streaming endpoint. `AgentLoop.run` is blocking with `wait_for` timeout.
- **Risk**: MEDIUM — Streaming exists for `/chat` but not for V2 agent path.

### 14. UI Chat Path (`POST /chat`)
- **Code location**: `main.py` (line 1438), `router_entrypoint.py` (line 156), `session.py` (line 417)
- **Status**: **Complex multi-route pipeline**. Flow: trivial fastpath → curated lookup → Tool01 → GAK → policy gate → fastpath templates → grounded code/ui analysis → AgentLoop → direct LLM. **Does NOT use V2 runtime, LangGraph, or auto FAISS**. Emits visual traces. Tool execution real but gated.
- **Risk**: MEDIUM — Many fastpaths bypass agent/tool logic; most queries resolve via template or direct LLM.

### 15. API Agent Path (`POST /v2/*`)
- **Code location**: `api_adapter.py`, `native_runtime.py`
- **Status**: **Distinct governed runtime**. `/v2/chat/agent` → `NativeAgentRuntimeV2.execute_run()`. Routes: `direct_assistant`, `promotion_adapter_dry_run`, `brain_evidence`, `mixed_brain_reasoning`, `operational_agent` (default). Uses `MemoryGatewayV2`, `ToolGatewayV2`, `planner`, `finalizer`, `intent_adapter`. Creates per-run artifacts. **No LangGraph**.
- **Risk**: LOW — Real structured runtime but single-LLM-call synthesis.

### 16. OpenAI-Compatible API Path (`POST /v1/chat/completions`)
- **Code location**: `api/openai_compat.py` (lines 17, 160-175)
- **Status**: **Thin wrapper over legacy**. Imports `handle_user_message` from `router_entrypoint`. Delegates to legacy `BrainSession` path. **Does NOT use V2 runtime**. Blocks tools/memory/FAISS writes.
- **Risk**: HIGH — OpenAI-compatible endpoint does not expose V2 agent capabilities.

---

## Key Conclusions

1. **LangGraph is NOT used at runtime** — Code exists in `langgraph_runtime.py` but is a dead/optional backend. Active runtime is `NativeAgentRuntimeV2` with zero LangGraph imports.

2. **V2 Agent is a structured wrapper** — It adds durable execution, governance, tool gateway, and evidence routing, but final synthesis is a single LLM call (finalizer with fallback). No multi-step LLM reasoning, no LangGraph graph execution.

3. **Legacy `/chat` is a fastpath-heavy pipeline** — Most queries resolve via deterministic fastpaths or direct LLM without tool execution. AgentLoop is only invoked for complex queries.

4. **Semantic memory/FAISS is opt-in for chat** — Not automatically retrieved in legacy path. V2 routes activate it via tool gateway.

5. **Governance and signed approvals work** — Fully enforced across both paths. 06C hardening complete.

6. **OpenAI-compatible endpoint is legacy-only** — Does not benefit from V2 runtime capabilities.