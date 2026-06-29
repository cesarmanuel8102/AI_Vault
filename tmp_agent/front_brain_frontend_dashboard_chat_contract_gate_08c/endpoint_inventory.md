# Endpoint Inventory — FRONT-BRAIN-FRONTEND-DASHBOARD-CHAT-CONTRACT-GATE-08C

**Baseline:** `979c277`

This document inventories the real frontend, dashboard, chat, trace, approval, status, and proxy endpoints that exist today in `tmp_agent/brain_v9`.

## Executive summary

- **38 endpoints** were inventoried.
- Only **8 endpoints touch NativeAgentRuntimeV2** directly.
- The two highest-impact paths are:
  1. `POST /v2/chat/agent` (used by `ui/index.html` and dashboard 8092 proxy).
  2. `GET /v2/agent/runs/{run_id}/trace` and its 8092 proxy `/brain-dashboard/agent-v2/runs/{run_id}/trace`.
- Legacy `/chat`, `/v1/chat/completions`, `/gate/*`, and `/tool01/permission/approve` do **not** use Agent V2 runtime.
- The visual trace endpoints `/brain/agent-trace/latest` and `/brain/agent-trace/stream` are independent of the runtime.
- The embedded dashboard served on `/dashboard` and `/dashboard-v2` is almost entirely independent of Agent V2 runtime.

## Native V2 touched endpoints

| Method | Path | File | Port | Risk |
|--------|------|------|------|------|
| POST | `/v2/chat/agent` | `api_adapter.py:172` | 8090 | high |
| GET | `/v2/agent/capabilities` | `api_adapter.py:63` | 8090 | low |
| GET | `/v2/agent/status` | `api_adapter.py:80` | 8090 | low |
| GET | `/v2/agent/runs` | `api_adapter.py:100` | 8090 | low |
| POST | `/v2/agent/runs` | `api_adapter.py:104` | 8090 | low |
| GET | `/v2/agent/runs/{run_id}` | `api_adapter.py:110` | 8090 | medium |
| POST | `/v2/agent/runs/{run_id}/plan` | `api_adapter.py:115` | 8090 | medium |
| POST | `/v2/agent/runs/{run_id}/execute` | `api_adapter.py:120` | 8090 | high |
| GET | `/v2/agent/runs/{run_id}/trace` | `api_adapter.py:140` | 8090 | high |
| POST | `/brain-dashboard/chat` | `dashboard_routes.py:313` | 8092 | high |
| GET | `/brain-dashboard/agent-v2/runs/{run_id}/trace` | `dashboard_routes.py:361` | 8092 | high |
| GET | `/brain-dashboard/status` | `dashboard_routes.py:215` | 8092 | low |
| GET | `/brain-dashboard/agent-v2/status` | `dashboard_routes.py:372` | 8092 | low |
| GET | `/brain-dashboard/agent-v2/status` | `main.py:1125` | 8090 | low |

## Static / HTML routes

| Method | Path | File | Port |
|--------|------|------|------|
| GET | `/ui` | `main.py:213` | 8090 |
| GET | `/ui/index.html` | static mount | 8090 |
| GET | `/ui/agent_trace_console.html` | static mount | 8090 |
| GET | `/dashboard` | `main.py:242` | 8090 |
| GET | `/dashboard-v2` | `main.py:252` | 8090 |
| GET | `/` (dashboard app) | `dashboard_app.py:19` | 8092 |
| GET | `/static/*` | `dashboard_app.py:16` | 8092 |

## Legacy chat endpoints (not Agent V2)

| Method | Path | File | Port |
|--------|------|------|------|
| POST | `/chat` | `main.py:1438` | 8090 |
| POST | `/v1/chat/completions` | `openai_compat.py:136` | 8090 |

Both route through `handle_user_message` -> `BrainSession.chat`, not through `get_agent_runtime_v2()`.

## Visual trace endpoints (not Agent V2)

| Method | Path | File | Port |
|--------|------|------|------|
| POST | `/brain/agent-trace/event` | `main.py:4523` | 8090 |
| GET | `/brain/agent-trace/latest` | `main.py:4552` | 8090 |
| GET | `/brain/agent-trace/stream` | `main.py:4564` | 8090 |

These endpoints use `main.py` in-memory queues and state, not the Agent V2 `TraceStore`. The UI uses them for live visual trace rendering.

## Approval / gate endpoints (not Agent V2)

| Method | Path | File | Port |
|--------|------|------|------|
| POST | `/gate/approve/{pending_id}` | `main.py:1934` | 8090 |
| POST | `/gate/reject/{pending_id}` | `main.py:1974` | 8090 |
| POST | `/tool01/permission/approve` | `main.py:1985` | 8090 |

These operate on `execution_gate` / `active_sessions`, not on Agent V2 runtime.

## Dashboard 8092 chat proxy flow

```
dashboard/static/app.js
  POST /brain-dashboard/chat
    dashboard_routes.py chat()
      POST http://127.0.0.1:8091/v2/chat/agent
        (expects Agent V2 service on port 8091)
    returns content + trace_url
  GET /brain-dashboard/agent-v2/runs/{run_id}/trace
    dashboard_routes.py agent_v2_trace()
      GET http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace
```

## Embedded dashboard 8090 endpoints

All `/brain/*`, `/trading/*`, `/autonomy/*`, and `/brain/maintenance/*` endpoints consumed by `ui/dashboard_*.js` are independent of Agent V2 runtime. They read from state, trading, strategy engine, and autonomy modules.

## Open questions / risks

1. **run_root mismatch**: Native V2 stores traces in `RUN_ROOT` (`tmp_agent/brain_v9/state.py`); LangGraph parity runtime defaults to `tmp_agent/agent_kernel_v2/runs_parity` (`langgraph_parity_runtime.py:107`). If 8092 proxy queries 8091 for a trace and the active backend is LangGraph, the proxy must know which run_root to read.
2. **Response schema drift**: `api_adapter.py` expects fields like `expected_write_scope`, `auto_decision`, and `blocked_tools` in the response. LangGraph `run()` does not currently return `expected_write_scope` or `auto_decision`.
3. **Trace event types**: `dashboard/static/app.js` filters trace events by `event_type === 'plan_created'`, `tool_call_started`, `tool_call_completed`, etc. LangGraph emits node-based events (`start_node`, `intent_node`, `planner_node`, `tool_execution_node`, `finalizer_node`, ...). The dashboard trace panel may render empty sections.
4. **Dashboard mode switch**: `dashboard/static/app.js` supports `read_only`, `build`, `auto`. LangGraph handles `read_only` and `build` via `validate_mode` + `mode_requires_escalation`, but `auto` semantics (`infer_auto_decision`) are missing.
5. **Approvals integration**: LangGraph can block a write tool with `approval_required: true` and generate `confirmation_id`, but there is no mechanism linking `confirmation_id` back to `/gate/approve` or `/tool01/permission/approve`.

## Port assumptions

| Port | App | Purpose |
|------|-----|---------|
| 8090 | `brain_v9.main:app` | Main Brain Chat V9 (UI, chat, dashboard HTML, /v2/*, /brain/*, /trading/*, /autonomy/*) |
| 8091 | `brain_v9.main:app` (or separate worker) | Agent V2 canonical backend. Dashboard 8092 proxies here. |
| 8092 | `brain_v9.dashboard.dashboard_app:app` | Persistent autonomy dashboard with its own static UI and chat proxy. |

## Recommendation

Before any `AGENT_V2_BACKEND` opt-in wiring, the following contracts must be hardened:

1. `/v2/chat/agent` response schema parity.
2. Trace storage path unification or proxy-aware resolution.
3. Trace event schema alignment with dashboard expectations.
4. Mode `auto` contract and `expected_write_scope` contract.
5. Approval `confirmation_id` actionability contract.
