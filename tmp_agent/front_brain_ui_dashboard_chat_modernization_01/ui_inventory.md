# Phase 1 — UI Inventory

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-01`

## Entrypoint & structure

| Item | Value |
|------|-------|
| App | `tmp_agent/brain_v9/dashboard/dashboard_app.py` (FastAPI, port 8092) |
| Routes | `tmp_agent/brain_v9/dashboard/dashboard_routes.py` (prefix `/brain-dashboard`) |
| Static mount | `/static` → `dashboard/static/` |
| Root | `GET /` → `static/index.html` |
| Structure | **Single-page app** (one `index.html` + `app.js` + `styles.css`) |

## Static files

| File | Lines | Notes |
|------|-------|-------|
| `static/index.html` | 113 | Single stacked page; chat is an inline panel |
| `static/app.js` | 386 | Refresh loop, render funcs, chat, collapsible Execution Trace panel |
| `static/styles.css` | 76 | Dark theme already present but rustic |

## Read-only endpoints available to the UI

- `GET /health`
- `GET /brain-dashboard/status` — aggregate (brain, kimi, dashboard, scheduler, autonomy, memory, safety, watchdog, alerts, **agent_v2**)
- `GET /brain-dashboard/activity`
- `GET /brain-dashboard/promotion-queue`
- `GET /brain-dashboard/scheduler`
- `GET /brain-dashboard/safety`
- `GET /brain-dashboard/agent-v2/status`
- `GET /brain-dashboard/agent-v2/runs/{run_id}/trace`

## Chat API contract

`POST /brain-dashboard/chat {message, mode, user_id}` → returns:
`ok, content, canonical_agent_v2, run_id, trace_url, classification, status, model_used, provider_used, provider_degraded, fallback_reason, raw_cot_exposed, mode_requested, mode_effective, auto_decision, mode_escalation_*, required_permission, expected_write_scope, confirmation_id, blocked_tools`

## Auth

- Public dashboard endpoints need **no token**.
- Strict Brain API endpoints use `X-Brain-Token` — but the dashboard proxy adds this **server-side**, so the **browser never handles tokens**. UI must never reference tokens.

## Existing chat features (already present)

- Mode segment (READ / BUILD / AUTO)
- Send button; metadata line (canonical, model, classification, status, mode, auto_decision)
- Provider-degraded warning; raw-CoT-exposed warning
- Trace link; collapsible Execution Trace panel with async trace fetch (plan / tools / evidence / governance / provider)

## Current UI problems

1. Rustic dense layout — no navigation; everything stacked on one long page.
2. Chat is a small inline panel, not a workspace; no conversation history, no inspector.
3. No markdown or code-block rendering — responses shown as plain pre-wrap text.
4. No message bubbles or user/assistant distinction.
5. No empty / loading / error states beyond "Thinking…".
6. Status info scattered; no cohesive top status bar with safety locks.
7. No dedicated safety panel showing memory / FAISS / trading / real-money locks.
8. No ops panel with 8091 / 8092 / 8070 status or runbook link.
9. Trace data exists but is buried in a collapsible under chat output.

## Conclusion

**UI_INVENTORY_COMPLETED** — single-page FastAPI dashboard, dark theme already present but rustic, chat embedded inline, no nav/sidebar/inspector/markdown. Rich endpoint data already available (status, agent_v2, safety, trace). Frontend-only modernization is feasible **without backend changes**.
