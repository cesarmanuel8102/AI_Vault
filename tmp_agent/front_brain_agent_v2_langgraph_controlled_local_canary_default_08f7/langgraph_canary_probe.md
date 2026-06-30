# LangGraph Canary Selection Probe — 08F7

## Phase

4 — LangGraph canary selection

## Purpose

Prove isolated shell env override selects LangGraph.

## Command

```powershell
$env:AGENT_V2_BACKEND = "langgraph"
python - <<'PY'
import os, sys
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL")
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2, get_agent_runtime_backend_name
rt = get_agent_runtime_v2()
print({...})
PY
```

## Observed result

| Field | Value |
|---|---|
| `AGENT_V2_BACKEND` | `langgraph` |
| `runtime_type` | `LangGraphParityRuntimeV2` |
| `backend_name` | `langgraph_parity` |
| `backend` | `langgraph_parity` |
| `backend_selected` | `langgraph_parity` |
| `backend_fallback_used` | `False` |
| `backend_fallback_reason` | `None` |
| `graph_available` | `True` |
| `graph_error` | `None` |
| `execute_timeout_seconds` | `30.0` |

## Result

**PASS**

## Notes

Isolated shell env override selects LangGraph. Graph is available, timeout is configured to 30.0s, no fallback occurred.

## Phase result

PHASE 4 — LangGraph canary selection: **COMPLETED**

## Recorded

`2026-06-30T19:23:00+00:00`
