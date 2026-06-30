# Native Default Control Probe — 08F7

## Phase

3 — Native default control

## Purpose

Prove Native remains the true default when the environment variable is absent.

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

Native remains the source-code default when `AGENT_V2_BACKEND` is absent. No fallback used.

## Phase result

PHASE 3 — Native default control: **COMPLETED**

## Recorded

`2026-06-30T19:22:00+00:00`
