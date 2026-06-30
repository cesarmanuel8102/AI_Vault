# Diagnostic Summary — 08F3

## Front
**FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3**

## Baseline
- Branch: `codex/own-capital-sustainable-return`
- Starting HEAD: `703ebfd`
- Previous accepted front: FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2

## State lock
- Branch matches: yes
- HEAD matches origin: yes
- Tracked diffs: none
- Staged diffs: none
- Guard: SAFE

## Phase results

| Phase | Result |
|-------|--------|
| Process startup / port hygiene | PASS |
| Backend live smoke (8091, LangGraph opt-in) | PASS |
| Trace proxy smoke (backend + dashboard) | PASS |
| Dashboard live chat proxy smoke (8092) | PARTIAL |
| Token security smoke | PASS |
| Native default after smoke | PASS |

## Key findings

- Backend process started with `AGENT_V2_BACKEND=langgraph` and served `/health` and `/v2/chat/agent` successfully.
- Direct backend chat returned `backend_selected=langgraph_parity` and `backend_fallback_used=false`.
- Live backend trace returned 27 events; dashboard trace proxy returned 2 events (summary) with HTTP 200.
- Dashboard chat proxy returned HTTP 200 and `ok=true`, but the dashboard response schema does not expose `backend_selected` or `backend_fallback_used`. This is a transparency/reporting observation, not a live smoke failure.
- Token value was not leaked in any response payload or subprocess log.
- Subprocesses stopped cleanly; ports 8091/8092 are free.
- Native default is preserved in a clean process (`AGENT_V2_BACKEND` unset).

## Scope
No source code, tests, dashboard routes, frontend, memory, FAISS, trading, or env files were modified.
