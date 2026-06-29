:# FRONT-BRAIN-DASHBOARD-CHAT-MANUAL-LIVE-SMOKE-AFTER-08E-R2 — Live Smoke Matrix

## Summary
| Check | Result | Notes |
|-------|--------|-------|
| Backend /health | PASS | 200 healthy |
| Backend /status | PASS | 200 ready |
| Backend /ui/index.html | PASS | 200 HTML |
| Backend /ui | PASS | 200 HTML |
| /v2/chat/agent native default | PASS | backend=native_runtime, run_id/trace present |
| /v2/chat/agent invalid_backend env | PASS | backend=native_runtime, fallback_used=true |
| /v2/chat/agent langgraph env | PASS | backend=native_runtime, fallback reason mentions missing create_run/execute_run |
| /chat legacy | PASS | 200 response |
| /v1/chat/completions | PASS | 200 chat.completion |
| Dashboard /health | PASS | 200 ok |
| Dashboard /brain-dashboard/status | PASS | brain healthy |
| Dashboard /brain-dashboard/agent-v2/status | PASS | backend=native_runtime |
| Dashboard static / | PASS | 200 HTML |
| Dashboard /brain-dashboard/chat | **FAIL** | 403 because proxy omits X-Brain-Token |
| Dashboard trace proxy | **FAIL** | 403 because proxy omits X-Brain-Token |
| Browser manual | SKIP | not executed in automation |

## Detailed failure
**Dashboard chat proxy** (`tmp_agent/brain_v9/dashboard/dashboard_routes.py:313-328`):
- Sends `POST http://127.0.0.1:8091/v2/chat/agent` with `Content-Type: application/json` only.
- Backend endpoint is protected by `require_strict_operator_access`, which requires `BRAIN_ADMIN_TOKEN` to be set and a matching `X-Brain-Token` header.
- Dashboard does not forward the token, so backend returns 403.
- Dashboard catches the 403 and returns `{ok:false, error:"HTTP Error 403: Forbidden", content:"Brain API unreachable."}`.

**Dashboard trace proxy** (`tmp_agent/brain_v9/dashboard/dashboard_routes.py:361-369`):
- Sends `GET http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace` with no headers.
- Same strict-operator protection causes 403.

## Classification
This is a **code defect** in `tmp_agent/brain_v9/dashboard/dashboard_routes.py`, not a service-startup/port/env issue. The fix requires the dashboard proxy to include the `X-Brain-Token` header when `BRAIN_ADMIN_TOKEN` is configured.
