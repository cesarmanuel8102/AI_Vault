# Brain Agent Frontend Dashboard Usage

## Canonical Endpoints for Agent V2

### 8091 (Brain API + Agent V2 Backend) — CANONICAL
- **Health:** `GET http://127.0.0.1:8091/health`
- **Agent V2 Status:** `GET http://127.0.0.1:8091/v2/agent/status`
- **Agent V2 Capabilities:** `GET http://127.0.0.1:8091/v2/agent/capabilities`
- **Agent V2 Dashboard Status:** `GET http://127.0.0.1:8091/brain-dashboard/agent-v2/status`
- **Agent V2 Chat:** `POST http://127.0.0.1:8091/v2/chat/agent`

### 8092 (Dashboard Frontend)
- **Dashboard:** `GET http://127.0.0.1:8092/`
- **Dashboard Status:** `GET http://127.0.0.1:8092/brain-dashboard/status`
- **Agent V2 Dashboard Status:** `GET http://127.0.0.1:8092/brain-dashboard/agent-v2/status` ❌ Blocked by Windows TCP zombie (PID 183024)

## Usage Examples

### Chat with Agent V2
```bash
curl -X POST http://127.0.0.1:8091/v2/chat/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Your task here", "mode": "read_only", "user_id": "your_name"}'
```

### Check Agent V2 Status
```bash
curl http://127.0.0.1:8091/v2/agent/status
```

### Legacy Chat (still works)
```bash
curl -X POST http://127.0.0.1:8091/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "mode": "read_only"}'
```

## Important Notes
- **8091 is canonical** for Agent V2 today.
- **8092 Agent V2 route** is blocked by a Windows TCP socket zombie (PID 183024).
- Use 8091 for all Agent V2 operations until the zombie is resolved.
- To resolve: reboot Windows, then run `scripts/brain/restart_dashboard_8092_agent_v2.ps1`.
- 8091 `/ui/` and `/dashboard` are preserved for legacy compatibility.
