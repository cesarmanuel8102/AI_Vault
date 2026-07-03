# Phase 2 — UX Specification

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-01`

## 1. Current UI problems

- Single long stacked page, no navigation.
- Chat is a tiny inline panel, not a workspace.
- No markdown / code-block rendering.
- No message bubbles or user/assistant distinction.
- No empty / loading / error states.
- Status scattered; no cohesive top status bar; no safety locks card.
- No ops panel (8091/8092/8070/runbook).
- Trace data buried.

## 2. Target UI structure

A **single-page app with hash-routed views** (no backend route changes):
- Persistent **top status bar** + **left navigation** + **main content** that swaps per view.
- Views: `#/overview`, `#/agent`, `#/chat`, `#/tools`, `#/memory`, `#/traces`, `#/safety`, `#/ops`, `#/roadmap`.

## 3. Dashboard layout

- **Top status bar:** Brain API, Dashboard, Backend, Provider/Model, Read-only lock, Memory/FAISS lock, Trading lock, Autonomy state, Last refresh.
- **Left nav:** Overview, Agent, Chat, Tools, Memory, Traces, Safety, Ops, Roadmap.
- **Overview:** cards for Service health, Agent status, Capabilities, Recent runs, Provider health, Safety locks, Memory status, Promotion queue, Endpoint status.
- **Agent panel:** backend, capability summary, tools available/blocked, read-only, governance, caveats.
- **Safety panel:** memory/FAISS/trading/real-money/code-write/git-commit locks.
- **Ops panel:** 8091/8092/8070 status, PID (UNKNOWN/NOT EXPOSED), runbook link, start/stop/restart as **disabled placeholders** only.

## 4. Chat layout

- **Left sidebar:** New chat, recent conversations (**PLACEHOLDER** — no backend persistence), system status compact card, mode badge READ_ONLY.
- **Main conversation:** message bubbles (user right / assistant left), markdown rendering, code blocks with copy button, empty state, loading state, error state.
- **Composer:** large textarea, Enter=send / Shift+Enter=newline, mode badge, send button with busy state, attachments placeholder disabled.
- **Right inspector:** run id, model/provider, classification, tools used, evidence summary, trace summary, blocked tools, safety locks, provider-degraded warning.

## 5. Data sources / endpoints (existing, read-only)

| Source | Endpoint |
|--------|----------|
| Aggregate status | `GET /brain-dashboard/status` |
| Activity | `GET /brain-dashboard/activity` |
| Promotion queue | `GET /brain-dashboard/promotion-queue` |
| Scheduler | `GET /brain-dashboard/scheduler` |
| Safety | `GET /brain-dashboard/safety` |
| Agent V2 status | `GET /brain-dashboard/agent-v2/status` |
| Trace | `GET /brain-dashboard/agent-v2/runs/{id}/trace` |
| Chat | `POST /brain-dashboard/chat` |

## 6. Components to add

- SPA shell + hash router
- Top status bar
- Left nav
- Overview cards grid
- Agent panel
- Safety locks panel
- Ops panel
- Chat workspace (sidebar + conversation + composer + inspector)
- Markdown renderer (lightweight, dependency-free, escapes HTML)
- Code block component with copy button
- Status polling (10s) with graceful error cards

## 7. Components to defer

- Conversation persistence / history sidebar → **DEFERRED_BACKEND_REQUIRED**
- Attachments → **DEFERRED_BACKEND_REQUIRED**
- Live stop/restart buttons → **DEFERRED_BACKEND_REQUIRED** (disabled placeholders only this front)
- Branch/head display → **DEFERRED_BACKEND_REQUIRED** (endpoint not exposed)
- Real tools list / blocked tools live → partial (only what chat response returns)

## 8. Safety boundaries

- UI never handles tokens.
- No new write/mutation endpoints called.
- Existing control endpoints (run-once/pause/resume/stop) are **not wired to new buttons** in this front.
- All safety locks default to **LOCKED / UNKNOWN** unless endpoint proves otherwise.
- No dangerous controls enabled; placeholders are disabled with tooltips.

## 9. Files proposed for modification

- `tmp_agent/brain_v9/dashboard/static/index.html` (rewrite as SPA shell)
- `tmp_agent/brain_v9/dashboard/static/styles.css` (rewrite modern dark theme)
- `tmp_agent/brain_v9/dashboard/static/app.js` (rewrite with router + views + chat)

## 10. Files that must NOT be touched

- `dashboard_app.py`, `dashboard_routes.py` (backend)
- `api_security.py`, `start_safe_server.py`, `start_local_browser_operational.py`, `.env`
- anything under `memory/`, `semantic/`, FAISS
- Agent V2 runtime, governance, provider routing

## 11. Acceptance criteria

- Dashboard loads at `/` with top bar + left nav + overview.
- All 9 nav views render (some placeholder content allowed).
- Chat view: send message → assistant bubble with markdown + inspector updates.
- Loading / error / empty states visible.
- Provider-degraded warning shows when present.
- Safety locks card shows LOCKED by default.
- No dangerous controls enabled.
- No backend files modified.
- No tokens in frontend.

## 12. Manual test plan

1. Open `http://127.0.0.1:8092/` → modern shell loads.
2. Click each nav item → view swaps.
3. Overview cards populate from `/brain-dashboard/status`.
4. Open Chat → empty state shows.
5. Type message + Enter → user bubble + loading.
6. Response → assistant bubble (markdown rendered) + inspector fills.
7. Code block → copy button works.
8. Simulate offline (stop network) → error card.
9. Safety view → all locks show LOCKED/UNKNOWN.
10. Ops view → 8091/8092 LIVE, 8070 INACTIVE, runbook link present.
11. No enabled stop/restart/commit/trading buttons anywhere.
12. Narrow width → layout responsive.
