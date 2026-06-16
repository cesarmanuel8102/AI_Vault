# API Integration Summary

```json
{
  "direct_import_ok": true,
  "endpoints": [
    "GET /v2/agent/capabilities",
    "GET /v2/agent/status",
    "GET /v2/agent/runs",
    "POST /v2/agent/runs",
    "GET /v2/agent/runs/{run_id}",
    "POST /v2/agent/runs/{run_id}/plan",
    "POST /v2/agent/runs/{run_id}/execute",
    "POST /v2/agent/runs/{run_id}/pause",
    "POST /v2/agent/runs/{run_id}/resume",
    "POST /v2/agent/runs/{run_id}/cancel",
    "GET /v2/agent/runs/{run_id}/trace",
    "GET /brain-dashboard/agent-v2/status"
  ],
  "server_restart_required_for_live_routes": true
}
```
