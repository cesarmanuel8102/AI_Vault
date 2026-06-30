# Service Startup Plan — 08F8

## Startup command
```bash
python tmp_agent/brain_v9/start_safe_server.py
```

## Required environment
```
BRAIN_PORT=8091
BRAIN_ADMIN_TOKEN=AGENTV2_TEST_ADMIN_TOKEN_08F8
AGENT_V2_BACKEND=unset (defaults to langgraph_parity)
```

## Expected ports
8091

## Health endpoints
/health, /v2/agent/status

## Rollback / cleanup
- taskkill //PID <PID> //F
- Verify port 8091 free before starting; kill stale Brain PID if needed

## Verification steps
- LangGraph default: GET /v2/agent/status returns backend_default=langgraph_parity
- Native rollback: Set AGENT_V2_BACKEND=native and restart, or resolve via runtime selector
- Dashboard/trace: GET /ui/ returns HTML; GET /v2/agent/runs/<id>/trace returns trace events

## Source patch needed
False

