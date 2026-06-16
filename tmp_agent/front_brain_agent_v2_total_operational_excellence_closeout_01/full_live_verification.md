# Full Live Verification

- 8091 GET /health: ok=True status=200 error=
- 8091 GET /v2/agent/status: ok=True status=200 error=
- 8091 GET /v2/agent/capabilities: ok=True status=200 error=
- 8091 GET /brain-dashboard/agent-v2/status: ok=True status=200 error=
- 8091 GET /v1/agent/status: ok=True status=200 error=
- 8091 GET /ui/: ok=True status=200 error=
- 8091 GET /dashboard: ok=True status=200 error=
- 8091 POST /v2/agent/runs: ok=True status=200 error=
- 8091 POST /plan: ok=True status=200 error=
- 8091 POST /execute: ok=True status=200 error=
- 8091 GET /trace: ok=True status=200 error=
- 8091 POST /v2/chat/agent: ok=True status=200 error=
- 8091 POST /chat legacy: ok=True status=200 error=
- 8092 GET /: ok=True status=200 error=
- 8092 GET /brain-dashboard/status: ok=True status=200 error=
- 8092 GET /brain-dashboard/agent-v2/status: ok=False status=None error=HTTP Error 404: Not Found
