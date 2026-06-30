# Backend Selection Runbook — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Purpose

How an operator selects the Agent V2 backend at runtime without modifying source code.

## Environment variable

`AGENT_V2_BACKEND`

## Default

`native_runtime`

## Allowed values

| Backend | Accepted values |
|---|---|
| Native | `""`, `"native"`, `"native_runtime"` |
| LangGraph parity | `"langgraph"`, `"langgraph_parity"`, `"langgraph_parity_runtime"` |

## Rules

1. Native is always the default when `AGENT_V2_BACKEND` is unset or empty.
2. LangGraph is **opt-in only**.
3. Any unknown value is treated as Native with `backend_fallback_used=true`.
4. If the `langgraph` package is missing or fails to initialize, the selector falls back to Native.
5. Do **not** change `runtime.py`, `api_adapter.py`, `main.py`, or `response_normalizer.py` to switch backends.
6. The backend can be observed at runtime via `/v2/agent/status`, `/v2/chat/agent` responses, and `/brain-dashboard/agent-v2/status`.

## PowerShell examples

### Check current value

```powershell
$env:AGENT_V2_BACKEND
```

### Use Native default for this session

```powershell
Remove-Item Env:\AGENT_V2_BACKEND
```

### Opt in to LangGraph for this session

```powershell
$env:AGENT_V2_BACKEND = 'langgraph'
```

### Opt in to LangGraph for the current process

```powershell
[Environment]::SetEnvironmentVariable('AGENT_V2_BACKEND', 'langgraph', 'Process')
```

### Opt in to LangGraph for the machine (requires admin)

```powershell
[Environment]::SetEnvironmentVariable('AGENT_V2_BACKEND', 'langgraph', 'Machine')
```

### Start the Brain V9 server with LangGraph

```powershell
$env:AGENT_V2_BACKEND='langgraph'
python -m tmp_agent.brain_v9.main
```

### Probe the selected backend from a Python shell

```powershell
python -c "from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_backend_name; print(get_agent_runtime_backend_name())"
```

## Verification endpoints

| Endpoint | Native indicator | LangGraph indicator |
|---|---|---|
| `GET /v2/agent/status` | `backend: native_runtime` | `backend: langgraph_parity` |
| `POST /v2/chat/agent` | `backend_selected: native_runtime` | `backend_selected: langgraph_parity` |
| `GET /brain-dashboard/agent-v2/status` | `backend: native_runtime` | `backend: langgraph_parity` |

## Cautions

- Do not set `AGENT_V2_BACKEND` at system level unless the operator explicitly intends to make LangGraph the default for all processes on that machine.
- Always confirm the backend via `/v2/agent/status` before running production smoke tests against LangGraph.
- If `backend_fallback_used` is `true`, inspect `backend_fallback_reason` for the exact cause.

## Phase result

PHASE 3 — Backend selection runbook: **COMPLETED**

## Recorded

`2026-06-30T16:50:00+00:00`
