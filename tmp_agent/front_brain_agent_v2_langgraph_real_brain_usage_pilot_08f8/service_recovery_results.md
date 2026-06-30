# Service Recovery Results — 08F8

| Service | Restored |
|---|---|
| Chat | True |
| Agent API | True |
| Dashboard | True |
| Trace | True |

## Backend posture
- backend_selected: `langgraph_parity`
- backend_default: `langgraph_parity`
- rollback_backend: `native_runtime`
- langgraph_default_active: True
- native_rollback_preserved: True

## Known remaining issue
- /v2/agent/capabilities endpoint status: `FAIL`

