## PHASE 13 - Dashboard observability gap review

**Status:** REVIEWED (no patch)

### Gap
The dashboard chat proxy (`dashboard_routes.py`) does not forward `backend_selected` or `backend_fallback_used` from the proxied backend response. Operators viewing only the dashboard cannot directly see which Agent V2 backend handled a run or whether a fallback to Native occurred.

### Evidence
- 08F3 `dashboard_live_smoke.json` recorded that `/brain-dashboard/chat` returned `ok=true`, `run_id`, `trace_url`, and `mode_effective=read_only`, but omitted backend metadata.
- Direct backend `/v2/chat/agent` with `AGENT_V2_BACKEND=langgraph` returned `backend_selected=langgraph_parity`, confirming the backend selection path works.

### Impact
This is a reporting/observability gap, not a functional failure. The runtime selector and fallback behavior remain correct.

### Recommendation
A future front should extend the dashboard chat proxy response to include backend metadata from the proxied backend response.

### Conclusion
No source code was modified in this reports-only front. The gap is documented for tracking.
