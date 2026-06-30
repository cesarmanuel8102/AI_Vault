# Rollback Probe — 08F7

## Phase

5 — Rollback to Native

## Purpose

Prove immediate rollback to Native after canary.

## Command

```powershell
Remove-Item Env:\AGENT_V2_BACKEND -ErrorAction SilentlyContinue
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
| `AGENT_V2_BACKEND` | `None` |
| `runtime_type` | `NativeAgentRuntimeV2` |
| `backend_name` | `native_runtime` |
| `backend` | `native_runtime` |
| `backend_selected` | `native_runtime` |
| `backend_fallback_used` | `False` |
| `backend_fallback_reason` | `None` |

## Result

**PASS**

## Notes

Immediate rollback to Native after canary. Requires no code change, no git change, only env unset/restart if the server process was live.

## Phase result

PHASE 5 — Rollback probe: **COMPLETED**

## Recorded

`2026-06-30T19:24:00+00:00`
