# Trace Contract Results

**Front:** FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D  
**Test File:** `tests/smoke/test_brain_agent_v2_trace_contracts_08d.py`  
**Backend:** `native_runtime`  
**Result:** **7 passed, 0 failed**

## Verified Contracts

1. **`trace_url` resolves** — The URL returned by `POST /v2/chat/agent` resolves to `{ok, run_id, trace, event_count}` via `GET /v2/agent/runs/{run_id}/trace`.
2. **Trace event schema** — Every event has `event_type` and at least one content key (`message`, `data`, `step_id`, `run_id`, `ts`).
3. **Dashboard trace filters** — `run_completed` is required and present. `plan_created` and `tool_call_*` are route-dependent; in the test run the evidence route emitted tool events but not `plan_created`. This is recorded as a contract note for the LangGraph adapter.
4. **Visual trace latest** — `GET /brain/agent-trace/latest` returns `{success, events}` with `events` as a list.
5. **Visual trace stream route** — `/brain/agent-trace/stream` is registered in the main app routes. The actual SSE connection is not opened in tests because it blocks indefinitely on heartbeats.
6. **Trace run_root consistency** — Native trace resolves under the current `RUN_ROOT`; `event_count` equals `len(trace)`.
7. **Scope guard** — No source or frontend files were modified.

## LangGraph Compatibility Notes

- LangGraph emits node-based events (`intent_node`, `planner_node`, `tool_execution_node`, `finalizer_node`, etc.) instead of Native event types.
- Before wiring `AGENT_V2_BACKEND`, a trace event type adapter must be added so that dashboard filters for `plan_created`, `tool_call_started`, and `tool_call_completed` continue to match.
- The `run_root` used by LangGraph must match Native `RUN_ROOT`, or `api_adapter.py` trace resolution must search both roots.
