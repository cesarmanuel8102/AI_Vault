# Rollback Runbook — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Purpose

How an operator safely returns to the Native default backend when the LangGraph opt-in experiment needs to be aborted.

## Rollback triggers

- `backend_fallback_used` is `true` and `backend_fallback_reason` indicates LangGraph unavailable.
- LangGraph runs time out or fail repeatedly.
- Smoke tests fail under `AGENT_V2_BACKEND=langgraph`.
- Dashboard shows unexpected backend or provider degradation.
- Operator decides to exit LangGraph opt-in experiment.

## Rollback steps

### 1. Stop the Brain V9 server

```powershell
Get-Process python | Where-Object { $_.CommandLine -like '*tmp_agent.brain_v9.main*' } | Stop-Process -Force
```

### 2. Unset `AGENT_V2_BACKEND` in the current session

```powershell
Remove-Item Env:\AGENT_V2_BACKEND
```

### 3. Clear it at process level

```powershell
[Environment]::SetEnvironmentVariable('AGENT_V2_BACKEND', $null, 'Process')
```

### 4. Clear it at machine level if applicable (requires admin)

```powershell
[Environment]::SetEnvironmentVariable('AGENT_V2_BACKEND', $null, 'Machine')
```

### 5. Restart the server

```powershell
python -m tmp_agent.brain_v9.main
```

### 6. Verify backend is Native

```powershell
python -c "from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_backend_name; print(get_agent_runtime_backend_name())"
```

Expected output: `native_runtime`

### 7. Run the Native smoke guard

```powershell
pytest tests/smoke/test_brain_agent_v2_runtime_selector_guard_08e.py -v
```

## Post-rollback verification

| Check | Expected |
|---|---|
| `GET /v2/agent/status` | `backend: native_runtime` |
| `POST /v2/chat/agent` | `backend_selected: native_runtime` |
| `/brain-dashboard/agent-v2/status` | `backend: native_runtime` |
| CI workflows | `phase1-ci` and `nontrading-smoke-regression` green |

## Notes

- No source code changes are required for rollback; the selector guard already falls back to Native when `AGENT_V2_BACKEND` is unset or invalid.
- Run artifacts from LangGraph opt-in sessions are isolated to their caller-provided `run_root` and do not corrupt production `RUN_ROOT`.
- Native runtime is the only production-supported backend at the 08F5 closeout stage.

## Phase result

PHASE 4 — Rollback runbook: **COMPLETED**

## Recorded

`2026-06-30T16:55:00+00:00`
