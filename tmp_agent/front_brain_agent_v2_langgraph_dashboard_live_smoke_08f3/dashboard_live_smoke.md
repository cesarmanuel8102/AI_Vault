# Dashboard Live Smoke — 08F3

## Goal
Verify dashboard starts, is healthy, and the `/brain-dashboard/chat` proxy can reach the live Agent V2 backend on 8091.

## Results

| Check | Result |
|-------|--------|
| Dashboard started on 127.0.0.1:8092 | PASS |
| `/health` reachable | PASS (HTTP 200) |
| `/brain-dashboard/chat` reachable | PASS (HTTP 200) |
| Chat proxy `ok` == true | PASS |
| Chat proxy returned `run_id` | PASS (`agv2_6cf111b5fbf3b588`) |
| Chat proxy returned `trace_url` | PASS |
| Chat proxy `mode_effective` == `read_only` | PASS |
| Token leak in dashboard chat response | None |

## Observations
- The dashboard chat proxy successfully forwards the request to backend `8091` and returns a sanitized response.
- The dashboard response does **not** currently include `backend_selected` or `backend_fallback_used` from the backend. Therefore the dashboard response alone cannot prove LangGraph selection; proof comes from the backend direct smoke (which confirmed `backend_selected=langgraph_parity`) plus the fact that the dashboard proxy is talking to the same live backend.
- No 403 / missing token / "Brain API unreachable" errors.

## Conclusion
Dashboard live chat proxy connectivity and token handling PASS. Backend selection transparency in dashboard response is a schema/reporting observation, not a live smoke failure.
