# Defect Confirmation: UI Canonical Path Mismatch

## Commit
46f344a290c6974665ae6303f6889233ee221b3b

## Defect Found
`tmp_agent/brain_v9/dashboard/static/app.js` contained hardcoded `http://127.0.0.1:8091` prefix when building trace URLs for the canonical Agent V2 response.

## Evidence
- Line 252 (before fix): `const traceUrl = j.trace_url.startsWith('/') ? 'http://127.0.0.1:8091' + j.trace_url : j.trace_url;`
- Line 288 (before fix): `const fullTraceLink = traceUrl.startsWith('/') ? ('http://127.0.0.1:8091' + traceUrl) : traceUrl;`
- This caused trace links in the 8092 dashboard UI to open on 8091 instead of staying on the canonical 8092 surface.

## Same-Origin Proxy Available
`GET /brain-dashboard/agent-v2/runs/{run_id}/trace` exists on 8092 (dashboard_routes.py:361) and proxies to 8091 internally.

## Trace URL from Chat
The chat response returns `trace_url` as `/v2/agent/runs/{run_id}/trace` (relative path starting with `/v2/`).

## Classification
- defect_confirmed: true
- hardcoded_8091_in_ui: true
- same_origin_trace_proxy_exists: true
- trace_url_from_chat_is_relative: true
- 8092_direct_v2_trace_available_before_fix: false
- dashboard_proxy_trace_available_before_fix: true
