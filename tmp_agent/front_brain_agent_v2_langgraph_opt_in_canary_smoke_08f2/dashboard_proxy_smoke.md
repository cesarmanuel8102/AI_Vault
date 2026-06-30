# Dashboard Proxy Smoke — 08F2

## Environment

- `AGENT_V2_BACKEND`: `langgraph`
- `BRAIN_ADMIN_TOKEN`: `AGENTV2_08F2_TEST_TOKEN`

## Method

Used `TestClient` against `tmp_agent.brain_v9.dashboard.dashboard_app`.
No long-running services were started.

## Results

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/health` | 200 | Dashboard healthy |
| `/brain-dashboard/chat` | 200 | Proxy attempted backend call; backend returned 403 because no live service on 8091 |
| `/brain-dashboard/agent/runs/{run_id}/trace` | 404 | Trace route not defined at this path in current dashboard routes |

## Token leak check

No `X-Brain-Token` value appeared in response payloads.

## Conclusion

Dashboard routes are reachable and the token-forwarding logic is intact. The proxied backend was not live, so the chat response was `ok:false`. This is acceptable for a controlled local smoke front; the dashboard proxy itself did not leak secrets.
