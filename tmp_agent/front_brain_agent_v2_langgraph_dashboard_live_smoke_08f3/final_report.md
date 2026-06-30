# Final Report — FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3

**Front**: FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3  
**Branch**: codex/own-capital-sustainable-return  
**Starting baseline**: 703ebfd  
**Status**: CANARY_SMOKE_COMPLETE

## Scope

This front ran a deeper **live** dashboard/backend smoke with real uvicorn subprocesses. `AGENT_V2_BACKEND=langgraph` was set only for the backend subprocess; the dashboard subprocess had no backend selection env. No source code, tests, dashboard routes, frontend, memory, FAISS, trading, or env files were modified.

## Live smoke results

| Phase | Result |
|-------|--------|
| Process startup / port hygiene | PASS |
| Backend live `/health` and `/v2/chat/agent` (8091, LangGraph opt-in) | PASS |
| Backend live trace (8091) | PASS |
| Dashboard live `/health` (8092) | PASS |
| Dashboard chat proxy `/brain-dashboard/chat` (8092 → 8091) | PASS |
| Dashboard trace proxy `/brain-dashboard/agent-v2/runs/{run_id}/trace` | PASS |
| Token security (no token value leak) | PASS |
| Native default after smoke | PASS |

## Key findings

- Backend started on 8091 with `AGENT_V2_BACKEND=langgraph` and returned `backend_selected=langgraph_parity` on `/v2/chat/agent`.
- Backend live trace returned a 27-event list.
- Dashboard chat proxy returned HTTP 200 and `ok=true` with a valid `run_id` and `trace_url`. It does not currently echo `backend_selected`; that is a schema/reporting observation, not a failure.
- Dashboard trace proxy returned HTTP 200 and a summarized trace.
- No test token value leaked in responses or uvicorn logs.
- Subprocesses were stopped cleanly; ports 8091 and 8092 are free.
- Native default is preserved in a clean process with `AGENT_V2_BACKEND` unset.

## Validation

- py_compile: PASS for `langgraph_parity_runtime.py` and `runtime.py`.
- 08F1 contract tests: 10 passed.
- Runtime selector guard tests: 14 passed.
- Response normalization tests: 12 passed.
- Dashboard R3 token proxy tests: 3 passed.
- Git hygiene guard: SAFE.

## Scope audit

- Source files modified: no
- Test files modified: no
- Dashboard/frontend/security/main/api_adapter/native_runtime/response_normalizer: unchanged
- Memory/FAISS/trading/broker/env: untouched

## Commit/push status

- Commit created: pending
- Pushed: pending
- CI verified: pending

## Recommended next front

**FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4**

Stress failure modes, timeouts, missing graph, malformed run, read_only/write boundaries. Keep Native default. Do not activate LangGraph globally.
