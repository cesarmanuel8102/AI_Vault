# Phase 3 — Implementation Notes

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-01`

## Approach

Frontend-only SPA rewrite of the three static files served by the existing FastAPI dashboard. **No backend changes.** No new routes. No build system. No external CDN. No tokens.

## Files modified

| File | Change |
|------|--------|
| `dashboard/static/index.html` | Rewritten as SPA shell (top bar + left nav + content container). 56 lines. |
| `dashboard/static/styles.css` | Rewritten modern dark professional theme. ~190 lines. |
| `dashboard/static/app.js` | Rewritten with hash router, 9 view renderers, chat workspace, markdown renderer, polling. ~370 lines. |

## What was built

### Dashboard (modern console)
- **Top status bar**: Brain API, Dashboard, Backend, Provider (with degraded state), READ-ONLY lock, MEM lock, TRADING lock, Autonomy state, last refresh. All driven by `/brain-dashboard/status` + `/safety`.
- **Left navigation**: Overview, Agent, Chat, Tools, Memory, Traces, Safety, Ops, Roadmap. Hash-routed (`#/overview`, etc.) — no backend route changes.
- **Overview**: 9 cards (service health, agent, capabilities, runs, provider, safety locks, memory, promotion queue, dashboard EPs) + "What Brain is Doing Now" + alerts/recommendations.
- **Agent panel**: backend, runtime type, provider/model, run count, capability registry placeholders, known caveats.
- **Safety panel**: memory/FAISS/trading/real-money/code/git locks — **default LOCKED** unless endpoint proves otherwise.
- **Ops panel**: 8091/8092/8070 status, PID = UNKNOWN/NOT EXPOSED, runbook link, **disabled** start/stop/restart placeholders.

### Chat (modern workspace)
- **Left sidebar**: New chat button, conversation list (**PLACEHOLDER** — labeled "NOT CONNECTED"), system status card.
- **Main conversation**: message bubbles (user right accent / assistant left), **markdown rendering** (headers, bold, italic, inline code, fenced code blocks, lists, links, blockquotes), **code blocks with copy button**, empty state, loading state, error state.
- **Composer**: auto-resizing textarea, **Enter to send / Shift+Enter newline**, mode badge READ_ONLY, send button with busy state.
- **Right inspector**: run id, classification, model/provider, mode effective, blocked tools, trace link, safety locks.
- **Warnings**: provider-degraded, fallback, raw-CoT-exposed all rendered as colored warning strips under assistant messages.

### Data integration
All via existing read-only endpoints:
- `GET /brain-dashboard/status`, `/activity`, `/scheduler`, `/safety`, `/promotion-queue`, `/agent-v2/status`
- `POST /brain-dashboard/chat`
- `GET /brain-dashboard/agent-v2/runs/{id}/trace` (linked from inspector)

Polling: every 10s via `Promise.all`. Graceful offline detection — top bar shows "✕ offline" and views keep last cached data.

### Markdown renderer
Lightweight, dependency-free, **escapes HTML first** (XSS-safe), then applies inline formatting. Fenced code blocks extracted before escaping to preserve content. Copy button via `navigator.clipboard`.

## Safety boundaries respected

- **No tokens** anywhere in frontend. Auth handled server-side by dashboard proxy.
- **No new write/mutation endpoints** called. Existing control endpoints (run-once/pause/resume/stop) **not wired** to any new buttons.
- **All safety locks default LOCKED** unless endpoint data proves otherwise (`canonical_semantic_mutated`, `faiss_mutated`).
- **No enabled dangerous controls**: start/stop/restart are `disabled` with tooltips. No commit/push/trading/memory-write buttons.
- **No backend files modified**: `dashboard_app.py`, `dashboard_routes.py` untouched.

## Deferred (marked in UI as PLACEHOLDER / NOT CONNECTED / DEFERRED)

- Conversation persistence → backend required
- Live tool registry list → endpoint not exposed
- Live service controls → approved backend front required
- Branch/head display → endpoint not exposed
