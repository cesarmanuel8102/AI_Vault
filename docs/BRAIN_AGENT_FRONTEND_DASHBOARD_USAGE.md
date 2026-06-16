# Brain Agent Frontend Dashboard Usage

Backend status: `GET http://127.0.0.1:8091/v2/agent/status`. Capabilities: `/v2/agent/capabilities`. Dashboard bridge: `/brain-dashboard/agent-v2/status`. Agentic chat path: `POST /v2/chat/agent` with `{ "message": "...", "mode": "read_only" }`. 8091 `/ui/` and `/dashboard` are preserved. 8092 `/brain-dashboard/status` reports Agent V2 when the dashboard process is loaded from the current canonical code.
