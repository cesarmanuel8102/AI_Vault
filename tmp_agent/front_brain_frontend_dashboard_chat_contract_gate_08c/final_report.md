# Final Report — FRONT-BRAIN-FRONTEND-DASHBOARD-CHAT-CONTRACT-GATE-08C

**Baseline:** `979c277`

**Branch:** `codex/own-capital-sustainable-return`

**Status:** `validated`

**Final head:** `7976ba4`

This front is a **report-only audit**. No source files, frontend files, dashboard files, runtime files, or production wiring were modified.

## Purpose

Front 08B approved `LangGraphParityRuntimeV2` as a backend candidate, but it did not validate frontend/dashboard/chat endpoint contracts. This front formally inventories those contracts and determines what must be preserved before any `AGENT_V2_BACKEND` opt-in wiring.

## Prior context

- **Front 08B decision:** `A — opt-in_backend_blueprint`
- **Native core score:** 850 / 900
- **LangGraph core score:** 880 / 900
- **LangGraph with architecture bonus:** 930 / 950
- **Caveat:** frontend/dashboard/chat contracts were not validated.

## Findings

### Endpoint inventory

- **38 endpoints** inventoried.
- Only **14 endpoints touch `NativeAgentRuntimeV2`** (including `/v2/chat/agent` and the 8092 dashboard proxy endpoints).
- Legacy `/chat` and `/v1/chat/completions` do **not** use Agent V2 runtime.
- Visual trace endpoints (`/brain/agent-trace/*`) are independent of the runtime.
- Approval/gate endpoints (`/gate/*`, `/tool01/*`) are independent of the runtime.
- The embedded dashboard on `/dashboard` and `/dashboard-v2` is almost entirely independent of Agent V2 runtime.

### Frontend call map

- `ui/index.html` calls `POST /v2/chat/agent` directly.
- `dashboard/static/app.js` calls `POST /brain-dashboard/chat`, which proxies to `127.0.0.1:8091/v2/chat/agent`.
- `dashboard/static/app.js` also fetches traces through the 8092 proxy.
- `ui/index.html` visual trace uses `/brain/agent-trace/latest` and `/brain/agent-trace/stream`.
- `ui/dashboard_*.js` calls many `/brain/*`, `/trading/*`, `/autonomy/*` endpoints, none of which depend on Agent V2.

### LangGraph opt-in impact matrix

| Status | Count |
|--------|-------|
| compatible | 7 |
| compatible_with_adapter | 7 |
| incompatible | 3 |
| not_applicable | 4 |

**Incompatible items:**
1. Dashboard trace view event types — LangGraph emits node-based events, dashboard expects `plan_created` / `tool_call_*`.
2. Mode `build` handling — LangGraph lacks `expected_write_scope` and may skip unsupported write tools.
3. `run_root` mismatch — Native uses `RUN_ROOT`; LangGraph defaults to isolated `runs_parity`.

**Blocking item:**
- Error handling when LangGraph is unavailable — `run()` can return a dict without `run_id`/`trace_url`, breaking `api_adapter.py`.

### Contract requirements before wiring

1. `/v2/chat/agent` response normalization (`expected_write_scope`, `auto_decision`, `provider_metadata`).
2. Trace storage root unification or dual-root lookup.
3. Trace event type adapter for dashboard compatibility.
4. Mode `build` `expected_write_scope` generation.
5. Runtime selector guard against missing `langgraph` package.
6. Endpoint contract tests before blueprint.

## Decision

`opt_in_blueprint_ready` is set to **true** because:

- The endpoint inventory is complete enough.
- All high-risk impacts are identified.
- No unknown blocking frontend contract remains.
- Required adapters/tests are explicitly listed.
- No source changes were made in this front.

**Recommended next action:** `B. Add endpoint contract tests before blueprint`

**Suggested next front name:** `FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D`

## Source changes

- **None.**

## Report files created

- `endpoint_inventory.json`
- `endpoint_inventory.md`
- `frontend_call_map.json`
- `frontend_call_map.md`
- `langgraph_opt_in_impact_matrix.json`
- `langgraph_opt_in_impact_matrix.md`
- `contract_requirements.json`
- `contract_requirements.md`
- `final_report.json`
- `final_report.md`

## Guard

- `memory_touched`: false
- `faiss_touched`: false
- `trading_touched`: false
- `env_touched`: false
- `guard_result`: SAFE

## Port map

| Port | App | Purpose |
|------|-----|---------|
| 8090 | `brain_v9.main:app` | Main Brain Chat V9 (UI, chat, dashboard HTML, /v2/*, /brain/*, /trading/*, /autonomy/*) |
| 8091 | Agent V2 backend | Exposed by main app or worker; dashboard 8092 proxies here |
| 8092 | `brain_v9.dashboard.dashboard_app:app` | Persistent autonomy dashboard with chat proxy |
