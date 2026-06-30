# Trace Proxy Smoke — 08F3

## Goal
Verify both the backend live trace endpoint and the dashboard trace proxy return trace lists with no token leak.

## Results

| Check | Result |
|-------|--------|
| Backend trace HTTP status | 200 |
| Dashboard trace proxy HTTP status | 200 |
| Backend `ok` == true | PASS |
| Dashboard `ok` == true | PASS |
| Backend `trace` is list | PASS (27 events) |
| Dashboard `trace` is list | PASS (2 events) |
| Token leak in either trace body | None |

## Token security
Checked for `TEST_ADMIN_TOKEN_VALUE`, `X-Brain-Token`, `BRAIN_ADMIN_TOKEN`. No matches.

## Notes
- Backend trace endpoint `/v2/agent/runs/{run_id}/trace` is live and returns rich LangGraph trace events.
- Dashboard trace proxy `/brain-dashboard/agent-v2/runs/{run_id}/trace` forwards to the backend and returns a summarized trace (2 events) without leaking the admin token.
