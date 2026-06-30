# Service Recovery Diagnostics — 08F8

## Date
2026-06-30T20:10:00+00:00

## Components inspected
- `brain_v9/main.py`: OK
- `chat_ui_server.py`: FILE_NOT_FOUND
- `dashboard/dashboard_routes.py`: OK
- `dashboard/dashboard_app.py`: OK

## Expected ports
- Brain chat/API: 8091
- Dashboard UI: 8091
- Trace endpoint: 8091

## Failure modes found
- **Agent V2 strict endpoints**: Require X-Brain-Token because BRAIN_ADMIN_TOKEN was not set in server env → Restarted safe server with BRAIN_ADMIN_TOKEN exported in process env
- **/v2/agent/capabilities**: HTTP 500 AttributeError: LangGraphParityRuntimeV2 missing list_capabilities → Documented as gap; no source patch applied
- **Roadmap governance initializer**: Warning during startup: 'NoneType' object has no attribute 'lower' → Non-fatal; documented as observability gap

## Processes
- Started: Brain V9 safe server on 127.0.0.1:8091 (PID noted in startup log)
- Stopped: Stale Brain server PID 60500 on port 8091
- Ports used: 8091

## Safety
- No memory/FAISS/trading/env touched: True

