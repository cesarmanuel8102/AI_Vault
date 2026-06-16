# Live Baseline Verification

- 8091 /health: ok=True status=200 error=
- 8091 /v2/agent/status: ok=True status=200 error=
- 8091 /v2/agent/capabilities: ok=True status=200 error=
- 8091 /brain-dashboard/agent-v2/status: ok=True status=200 error=
- 8091 /ui/: ok=True status=200 error=
- 8091 /dashboard: ok=True status=200 error=
- 8091 POST /v2/agent/runs: ok=True status=200 error=
- 8091 POST /plan: ok=True status=200 error=
- 8091 POST /execute: ok=True status=200 error=
- 8091 GET /trace: ok=True status=200 error=
- 8092 /: ok=True status=200 error=
- 8092 /brain-dashboard/status: ok=True status=200 error=
- 8092 /brain-dashboard/agent-v2/status: ok=False status=None error=HTTP Error 404: Not Found
- direct_import: {'ok': True, 'needed_registered': True, 'matched_routes': ['/agent', '/brain-dashboard/agent-v2/status', '/brain/agent-trace/event', '/brain/agent-trace/latest', '/brain/agent-trace/stream', '/dashboard', '/dashboard-v2', '/v1/agent/healthz', '/v1/agent/status', '/v2/agent/capabilities', '/v2/agent/runs', '/v2/agent/runs/{run_id}', '/v2/agent/runs/{run_id}/cancel', '/v2/agent/runs/{run_id}/execute', '/v2/agent/runs/{run_id}/pause', '/v2/agent/runs/{run_id}/plan', '/v2/agent/runs/{run_id}/resume', '/v2/agent/runs/{run_id}/trace', '/v2/agent/status']}
