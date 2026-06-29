# FRONT-BRAIN-DASHBOARD-CHAT-MANUAL-LIVE-SMOKE-AFTER-08E-R2 — Final Report

## Status: DASHBOARD_PROXY_LIVE_FAILURE

- **Front:** FRONT-BRAIN-DASHBOARD-CHAT-MANUAL-LIVE-SMOKE-AFTER-08E-R2
- **Baseline / starting head:** 65d4f7c
- **Branch:** codex/own-capital-sustainable-return
- **Final head:** 9525823
- **Acceptance decision:** REJECTED_LIVE_SMOKE

## What worked
| Check | Result |
|-------|--------|
| Service startup (8091 backend, 8092 dashboard) | SUCCESS |
| Backend /health | PASS |
| Backend /status | PASS |
| Backend /ui and /ui/index.html | PASS |
| /v2/chat/agent with Native default | PASS |
| /v2/chat/agent with AGENT_V2_BACKEND=invalid_backend | PASS fallback to native_runtime |
| /v2/chat/agent with AGENT_V2_BACKEND=langgraph | PASS fallback to native_runtime with reason citing missing create_run/execute_run |
| Legacy /chat | PASS |
| /v1/chat/completions | PASS |
| Dashboard /health | PASS |
| Dashboard /brain-dashboard/status | PASS |
| Dashboard /brain-dashboard/agent-v2/status | PASS |
| Dashboard static / | PASS |

## What failed
| Check | Result | Root cause |
|-------|--------|------------|
| Dashboard /brain-dashboard/chat | FAIL | Dashboard proxy omits X-Brain-Token header when calling backend /v2/chat/agent. Backend strict-operator access returns 403. |
| Dashboard trace proxy | FAIL | Same missing-token issue on /v2/agent/runs/{run_id}/trace. |

## Code defect details
- **File:** tmp_agent/brain_v9/dashboard/dashboard_routes.py
- **Lines:** 313-328 (chat proxy), 361-369 (trace proxy)
- **Issue:** The dashboard constructs urllib.request.Request to http://127.0.0.1:8091 with only Content-Type: application/json. It does not forward the X-Brain-Token header required by require_strict_operator_access on the backend.
- **Evidence:**
  - Direct backend call with X-Brain-Token returns 200.
  - Dashboard proxy call returns {ok:false, error:'HTTP Error 403: Forbidden', content:'Brain API unreachable.'}.

## Scope respected
- No source files modified.
- No LangGraph wiring or default activation.
- No memory/FAISS/trading/env changes.
- No amend, no force push, no force-with-lease.
- Guard SAFE.

## Browser manual checklist
Not executed in automation environment. If run manually:
1. Open http://127.0.0.1:8091/ui/ and send 'native live smoke check after 08e r2' — expect response.
2. Open http://127.0.0.1:8092/ and send 'dashboard live smoke check after 08e r2' — currently fails due to missing token header; fix required first.
3. Open trace link if visible.
4. Confirm no browser console fatal errors.

## Recommended next action
Create follow-up front to patch tmp_agent/brain_v9/dashboard/dashboard_routes.py so that dashboard chat and trace proxy requests include the configured X-Brain-Token header. Then rerun this live smoke. Do not proceed to controlled backend opt-in readiness until dashboard proxy is green.

## Next front name
FRONT-BRAIN-DASHBOARD-CHAT-PROXY-TOKEN-FIX-08E-R3