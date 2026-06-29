# Frontend Call Map — FRONT-BRAIN-FRONTEND-DASHBOARD-CHAT-CONTRACT-GATE-08C

**Baseline:** `979c277`

This document maps every real frontend caller to its backend endpoint, and identifies which parts of the UI would be affected if `LangGraphParityRuntimeV2` became the opt-in backend behind `AGENT_V2_BACKEND`.

## Key finding

Only two frontend surfaces are coupled to the Agent V2 runtime:

1. **Main chat UI** (`ui/index.html`) → `POST /v2/chat/agent`.
2. **Persistent dashboard chat + trace** (`dashboard/static/app.js`) → `POST /brain-dashboard/chat` → proxy to `8091/v2/chat/agent`, plus `GET /brain-dashboard/agent-v2/runs/{run_id}/trace`.

Everything else (embedded dashboard `/dashboard`, visual trace console, `/chat` legacy, `/v1/chat/completions`, `/gate/*`, `/tool01/*`) is either independent or routes through `BrainSession.chat` / `handle_user_message`.

## Main chat UI (`ui/index.html`)

### `sendMessage()` — line 1331

- **Endpoint:** `POST /v2/chat/agent`
- **Request:** `{message, mode: read_only|build|auto, user_id}`
- **Response fields consumed:**
  - `ok`, `canonical_agent_v2`, `route`, `final_answer`
  - `provider_metadata.model_used`, `classification`, `status`
  - `mode_effective`, `mode_requested`, `auto_decision`
  - `mode_escalation_required`, `expected_write_scope`, `required_permission`, `confirmation_id`
  - `trace_url`, `blocked_tools`
  - `permission_required`, `permission_id`, `tool_name`, `tool_result`, `pending_action`
- **UI behavior:** renders the agent response, a metadata line, the escalation panel, the execution trace panel, and legacy tool/approval cards.
- **LangGraph impact:** **high**. Response schema must be preserved.

### `init()` — line 2634

- **Endpoint:** `GET /health`
- **Impact:** none.

### `handleGateAction()` — line 1452

- **Endpoint:** `POST /gate/{approve|reject}/{pending_id}`
- **Impact:** none; legacy execution gate.

### `handleTool01PermissionAction()` — line 1511

- **Endpoint:** `POST /tool01/permission/approve`
- **Impact:** none; TOOL-01B permission gate.

### `initAw()` / `connectAw()` — lines 2593, 2601

- **Endpoints:** `GET /brain/agent-trace/latest`, `GET /brain/agent-trace/stream`
- **Impact:** none on transport. If LangGraph starts emitting different internal trace events, those would need to be bridged separately, but the endpoints themselves do not depend on the runtime.

## Persistent dashboard 8092 (`dashboard/static/app.js`)

### `chat()` — line 210

- **Endpoint:** `POST /brain-dashboard/chat`
- **Proxy target:** `http://127.0.0.1:8091/v2/chat/agent`
- **Response fields consumed:** same as `ui/index.html`, plus `content`, `provider_used`, `raw_cot_exposed`, `fallback_reason`.
- **UI behavior:** renders chat output, canonical badge, metadata line, trace link, and execution trace panel.
- **LangGraph impact:** **high**. Schema and trace path must be preserved. The dashboard also rewrites `trace_url` from `/v2/agent/runs/` to `/brain-dashboard/agent-v2/runs/` for same-origin access.

### `renderExecutionTrace()` — line 279

- **Endpoint:** `GET /brain-dashboard/agent-v2/runs/{run_id}/trace` → proxy to `8091/v2/agent/runs/{run_id}/trace`
- **Response fields consumed:** `trace[{event_type, message, data{tool, ok, blocked}}]`, `event_count`
- **UI behavior:** renders Plan, Tools, Evidence, Governance, Provider sections.
- **LangGraph impact:** **high**. The dashboard filters on `event_type` values produced by Native V2 (`plan_created`, `tool_call_started`, `tool_call_completed`). LangGraph emits node-based events (`start_node`, `intent_node`, `planner_node`, `tool_execution_node`, `finalizer_node`, etc.).

### `refresh()` — line 7

- **Endpoints:** `GET /brain-dashboard/status`, `GET /brain-dashboard/activity`, `GET /brain-dashboard/scheduler`, `GET /brain-dashboard/safety`, `GET /brain-dashboard/promotion-queue`
- **Impact:** **low**. Only `/brain-dashboard/status` contains `agent_v2` metadata from `get_agent_runtime_v2()`, and only the `backend` field changes.

### `control(action)` — line 184

- **Endpoints:** `POST /brain-dashboard/control/{run-once|pause|resume|stop}`
- **Impact:** none.

## Visual trace console (`ui/agent_trace_console.html`)

- **Endpoints:** `GET /brain/agent-trace/latest`, `GET /brain/agent-trace/stream`
- **Impact:** none on endpoints. Event schema is the only coupling, and it is independent of the runtime.

## Embedded dashboard 8090 (`ui/dashboard_*.js`)

- **Endpoints:** `/brain/*`, `/trading/*`, `/autonomy/*`, `/brain/maintenance/*`
- **Impact:** **none**. None of these endpoints use `get_agent_runtime_v2()`.

## Legacy / OpenAI-compatible chat

- `/chat` and `/v1/chat/completions` route through `handle_user_message` → `BrainSession.chat`.
- **Impact:** none.

## Port assumptions

| Port | Service | Frontend callers |
|------|---------|------------------|
| 8090 | Main Brain Chat V9 | `ui/index.html`, `ui/dashboard_*.js`, `ui/agent_trace_console.html` |
| 8091 | Agent V2 backend (same or separate worker) | Proxied by 8092 dashboard |
| 8092 | Persistent autonomy dashboard | `dashboard/static/app.js` |

## Summary table

| Frontend file | Endpoint | LangGraph impact | Reason |
|---------------|----------|------------------|--------|
| `ui/index.html` | `POST /v2/chat/agent` | high | Direct Agent V2 runtime |
| `ui/index.html` | `GET /brain/agent-trace/*` | none | Runtime-independent SSE |
| `ui/index.html` | `POST /gate/*`, `/tool01/*` | none | Legacy execution gate |
| `ui/index.html` | `GET /health` | none | General health |
| `dashboard/static/app.js` | `POST /brain-dashboard/chat` | high | Proxy to 8091 `/v2/chat/agent` |
| `dashboard/static/app.js` | `GET /brain-dashboard/agent-v2/runs/{run_id}/trace` | high | Proxy to 8091 trace |
| `dashboard/static/app.js` | `/brain-dashboard/status` | low | `agent_v2.backend` only |
| `dashboard/static/app.js` | Other `/brain-dashboard/*` | none | Autonomy/memory/scheduler |
| `ui/agent_trace_console.html` | `/brain/agent-trace/*` | none | Runtime-independent |
| `ui/dashboard_*.js` | `/brain/*`, `/trading/*`, `/autonomy/*` | none | No runtime dependency |

## Conclusion

The frontend/dashboard/chat surface is mostly decoupled from the Agent V2 runtime. The only high-risk coupling is the chat response + trace path. Before opt-in wiring, contract tests must cover:

1. `/v2/chat/agent` response schema.
2. `/v2/agent/runs/{run_id}/trace` event schema and storage resolution.
3. Dashboard 8092 proxy compatibility.
4. Mode switch `read_only` / `build` / `auto` behavior.
5. Build-escalation UI fields (`expected_write_scope`, `confirmation_id`, `required_permission`).
