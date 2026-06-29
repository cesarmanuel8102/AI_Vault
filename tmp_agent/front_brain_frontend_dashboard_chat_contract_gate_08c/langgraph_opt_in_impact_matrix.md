# LangGraph Opt-In Impact Matrix — FRONT-BRAIN-FRONTEND-DASHBOARD-CHAT-CONTRACT-GATE-08C

**Baseline:** `979c277`

**Assumption:** `LangGraphParityRuntimeV2` becomes opt-in backend via `AGENT_V2_BACKEND` flag; `get_agent_runtime_v2()` returns `LangGraphParityRuntimeV2` only when the flag is set; default remains `NativeAgentRuntimeV2`.

## Compatibility summary

| Status | Count |
|--------|-------|
| compatible | 7 |
| compatible_with_adapter | 7 |
| incompatible | 3 |
| not_applicable | 4 |
| unknown | 0 |
| **blocking** | 1 |

## High-risk items

1. `/v2/chat/agent` response schema
2. `ui/index.html` chat rendering
3. Dashboard `/brain-dashboard/chat` proxy
4. Dashboard trace view
5. `trace_url` compatibility / run_root mismatch
6. Mode `build` handling
7. Error handling when LangGraph is unavailable

## Detailed matrix

### `/v2/chat/agent` response schema

- **Native behavior:** returns full schema including `expected_write_scope`, `auto_decision`.
- **LangGraph behavior:** deterministic finalizer; missing `expected_write_scope` and `auto_decision`.
- **Status:** `compatible_with_adapter`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** add response normalization in `api_adapter.py` or runtime selector.

### `ui/index.html` chat rendering

- **Native behavior:** consumes all response fields to render metadata, escalation panel, trace.
- **LangGraph behavior:** final answer is parity summary; metadata line shows `parity_v1_full`.
- **Status:** `compatible_with_adapter`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** schema parity tests via TestClient.

### Dashboard `/brain-dashboard/chat` proxy

- **Native behavior:** proxies to `8091/v2/chat/agent` and maps response to dashboard fields.
- **LangGraph behavior:** proxy still works if schema is normalized.
- **Status:** `compatible_with_adapter`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** dashboard proxy contract tests.

### Dashboard trace view

- **Native behavior:** fetches trace and filters by `plan_created`, `tool_call_started`, `tool_call_completed`.
- **LangGraph behavior:** emits node-based events (`intent_node`, `tool_execution_node`, ...).
- **Status:** `incompatible`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** add trace event type adapter in LangGraph runtime or teach dashboard to render node events.

### `agent_trace_console`

- **Native behavior:** consumes `/brain/agent-trace/latest` and `/brain/agent-trace/stream`.
- **LangGraph behavior:** endpoints are runtime-independent.
- **Status:** `not_applicable`
- **Risk:** low
- **Required before wiring:** no
- **Recommendation:** regression test only.

### `trace_url` compatibility

- **Native behavior:** trace stored under `RUN_ROOT`.
- **LangGraph behavior:** default trace store under `tmp_agent/agent_kernel_v2/runs_parity`.
- **Status:** `compatible_with_adapter`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** use same `run_root` for opt-in backend or dual-root lookup.

### `run_id` compatibility

- **Native behavior:** `agv2_` prefix.
- **LangGraph behavior:** same prefix and hash scheme.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### `capability_metadata` compatibility

- **Native behavior:** derived in `api_adapter.py`.
- **LangGraph behavior:** superset with extra parity keys; all required keys present.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### `provider_metadata` compatibility

- **Native behavior:** live LLM provider/model.
- **LangGraph behavior:** deterministic finalizer source, `model_used='parity_v1_full'`.
- **Status:** `compatible_with_adapter`
- **Risk:** medium
- **Required before wiring:** no
- **Recommendation:** document parity labels or inject production-like finalizer.

### Mode `read_only`

- **Native behavior:** blocks write tools.
- **LangGraph behavior:** same governance helpers.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### Mode `build`

- **Native behavior:** generates `expected_write_scope`, `required_permission='build'`, `confirmation_id`.
- **LangGraph behavior:** marks write tools as blocked/unsupported but lacks `expected_write_scope`; write tools outside `SUPPORTED_READ_TOOLS` are skipped.
- **Status:** `incompatible`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** implement `expected_write_scope` or restrict opt-in to read-only until build mode parity is added.

### Mode `auto`

- **Native behavior:** `infer_auto_decision` returns `auto_decision` field.
- **LangGraph behavior:** no `auto_decision` field.
- **Status:** `compatible_with_adapter`
- **Risk:** medium
- **Required before wiring:** yes
- **Recommendation:** add `auto_decision='n/a'` fallback in response normalization.

### `approval_required`

- **Native behavior:** escalation panel receives `expected_write_scope` and `confirmation_id`.
- **LangGraph behavior:** sets `mode_escalation_required=True` and `confirmation_id`, but no `/gate` integration.
- **Status:** `compatible_with_adapter`
- **Risk:** medium
- **Required before wiring:** yes
- **Recommendation:** ensure `expected_write_scope` is populated for UI display.

### `confirmation_id`

- **Native behavior:** `confirm_{run_id}`.
- **LangGraph behavior:** same format.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### `required_permission`

- **Native behavior:** `'build'` for escalation.
- **LangGraph behavior:** `'build'` in `_governance_gate_node`.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### Tool results

- **Native behavior:** stored in run plan and finalizer.
- **LangGraph behavior:** stored in state; UI does not directly consume raw array today.
- **Status:** `compatible_with_adapter`
- **Risk:** low
- **Required before wiring:** no

### Blocked tools

- **Native behavior:** returned as list.
- **LangGraph behavior:** same list shape.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### Streaming / progress

- **Native behavior:** `/v2/chat/agent` is synchronous JSON; visual trace via independent SSE.
- **LangGraph behavior:** no production streaming wiring.
- **Status:** `not_applicable`
- **Risk:** low
- **Required before wiring:** no

### Health / status panels

- **Native behavior:** `/v2/agent/status` returns `backend='native_runtime'`.
- **LangGraph behavior:** returns `backend='langgraph_parity'`.
- **Status:** `compatible`
- **Risk:** low
- **Required before wiring:** no

### Error handling

- **Native behavior:** catches exceptions and returns run dict with `status='failed'`.
- **LangGraph behavior:** if `langgraph` not installed, `run()` returns dict without `run_id`/`trace_url`, which can break `api_adapter.py` response construction.
- **Status:** `incompatible`
- **Risk:** **blocking**
- **Required before wiring:** yes
- **Recommendation:** runtime selector must never return LangGraph backend unless package is available and flag is explicitly set; add graceful fallback.

### `/chat` legacy

- **Native behavior:** routes through `handle_user_message` → `BrainSession.chat`.
- **LangGraph behavior:** unchanged.
- **Status:** `not_applicable`
- **Risk:** none
- **Required before wiring:** no

### `/v1/chat/completions`

- **Native behavior:** routes through `handle_user_message` → `BrainSession.chat`.
- **LangGraph behavior:** unchanged.
- **Status:** `not_applicable`
- **Risk:** none
- **Required before wiring:** no

### Dashboard 8092 → 8091 proxy assumption

- **Native behavior:** dashboard 8092 proxies chat and trace to 8091.
- **LangGraph behavior:** proxy still works if 8091 uses same backend and schema is preserved.
- **Status:** `compatible_with_adapter`
- **Risk:** medium
- **Required before wiring:** yes
- **Recommendation:** document that 8091 must use same backend selection as 8090.

### `run_root` differences

- **Native behavior:** `RUN_ROOT`.
- **LangGraph behavior:** isolated `runs_parity` by default.
- **Status:** `incompatible`
- **Risk:** high
- **Required before wiring:** yes
- **Recommendation:** use production `RUN_ROOT` for opt-in backend.

### Checkpoint / trace storage differences

- **Native behavior:** `TraceStore` / `CheckpointStore` under `RUN_ROOT`.
- **LangGraph behavior:** same classes but different default root.
- **Status:** `compatible_with_adapter`
- **Risk:** medium
- **Required before wiring:** yes
- **Recommendation:** unify storage root.

## Blocking conclusion

The only **blocking** item is **error handling when LangGraph is unavailable**. The runtime selector must never expose LangGraph as the active backend unless the package is installed and `AGENT_V2_BACKEND=langgraph` is explicitly set.

Three additional items are **incompatible** and require adapters/tests before opt-in wiring:

1. Dashboard trace view event types.
2. Mode `build` handling / `expected_write_scope`.
3. `run_root` mismatch.

Seven items are `compatible_with_adapter` and can be resolved with response normalization or lightweight tests.

## Next front recommendation

Recommended next action: **B — Add endpoint contract tests before blueprint** (or **A with adapter requirements** if contract tests are created immediately after).
