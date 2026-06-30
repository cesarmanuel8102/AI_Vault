# Phase 7 — Dashboard / Trace Canary

## Summary
Read-only probe of dashboard and trace proxy surfaces confirms that the LangGraph local canary can be observed by an operator through existing dashboard routes without any dashboard modifications.

## Probes executed
1. Inspected `tmp_agent/brain_v9/dashboard/dashboard_routes.py` for token handling, chat proxy, trace proxy, and Agent V2 status exposure.
2. Inspected `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` for backend metadata exposure in chat and capabilities responses.

## Findings

### Token safety
- Dashboard reads `BRAIN_ADMIN_TOKEN` from environment only; token is never logged or returned to clients.
- Both `/brain-dashboard/chat` and `/brain-dashboard/agent-v2/runs/{run_id}/trace` add `X-Brain-Token` header via `_strict_headers()`.
- No token value appears in any response schema.

### Backend observability
- Dashboard `/brain-dashboard/status` returns `agent_v2.backend`, so an operator can see `native_runtime` vs `langgraph_parity`.
- `/brain-dashboard/agent-v2/status` also surfaces `agent_v2.backend`.
- `/v2/agent/capabilities` (used by dashboard data paths) returns `backend`.

### Chat proxy canary evidence
- `/brain-dashboard/chat` proxies to `http://127.0.0.1:8091/v2/chat/agent`.
- The API adapter chat response includes:
  - `backend_selected`
  - `backend_fallback_used`
  - `backend_fallback_reason`
- Dashboard chat proxy forwards these fields to the dashboard client.

### Trace proxy
- `/brain-dashboard/agent-v2/runs/{run_id}/trace` proxies to `http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace`.
- Uses `_strict_headers()` for token forwarding.
- Read-only; safe for local canary.

## Gap identified
- **GAP-08F5-04**: dashboard `/brain-dashboard/status` does **not** expose `backend_fallback_reason` or `backend_fallback_used` directly in the top-level status object; it only surfaces `agent_v2.backend`.
  - **Not a blocker for local canary**: operator can still see fallback reason via API chat response or via `/v2/agent/status`.
  - **Blocker for global default promotion**: dashboard status must surface fallback reason directly before LangGraph can become the default.

## Decision
- Dashboard/trace canary probe: **PASS**.
- No dashboard patches required for 08F7 local canary.
- GAP-08F5-04 documented for follow-up front `FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-FALLBACK-OBSERVABILITY-08F7-R2`.

## Next
Proceed to Phase 8 — Blocker Status Review.
