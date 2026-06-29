# FRONT-BRAIN-DASHBOARD-CHAT-RECOVERY-AFTER-08E-R1 — Diagnostic Matrix

## Incident
- **Incident ID:** FRONT-BRAIN-DASHBOARD-CHAT-RECOVERY-AFTER-08E-R1
- **Baseline:** f45ad26
- **Branch:** codex/own-capital-sustainable-return
- **Workdir:** C:\AI_VAULT_CANONICAL

## Root Cause
**Code:** `LANGGRAPH_PARITY_RUNTIME_INTERFACE_MISMATCH`

`LangGraphParityRuntimeV2` instantiates successfully and reports `graph_available=True` because `langgraph` is installed. However, it does **not** implement the production runtime interface (`create_run`, `execute_run`) that `api_adapter.chat_agent` uses. When `AGENT_V2_BACKEND=langgraph`, the 08E selector returns `LangGraphParityRuntimeV2`, and `/v2/chat/agent` crashes with `AttributeError`.

## Affected Flows
- `/v2/chat/agent`
- Dashboard `/chat` proxy to 8091
- Dashboard `/trace` proxy to 8091
- `AGENT_V2_BACKEND=langgraph` request path

## Runtime Selection Matrix
| Env value | Expected | Actual | Status |
|-----------|----------|--------|--------|
| unset | NativeRuntimeV2 | NativeRuntimeV2 | PASS |
| `quantum` | NativeRuntimeV2 fallback | NativeRuntimeV2 fallback | PASS |
| `langgraph` | NativeRuntimeV2 fallback (interface missing) | NativeRuntimeV2 fallback | PASS |

## Interface Check
| Runtime | `create_run` | `execute_run` | `run` |
|---------|-------------|--------------|-------|
| NativeRuntimeV2 | yes | yes | yes |
| LangGraphParityRuntimeV2 | no | no | yes |

## Live Services
| Port | Status |
|------|--------|
| 8090 | SERVICE_NOT_RUNNING |
| 8091 | SERVICE_NOT_RUNNING |
| 8092 | SERVICE_NOT_RUNNING |

## Allowed vs Forbidden Changes
Allowed file changes:
- `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py`
- `tests/smoke/test_brain_chat_native_default_recovery_after_08e_r1.py`
- `tests/smoke/test_brain_dashboard_chat_recovery_after_08e_r1.py`
- `tmp_agent/front_brain_dashboard_chat_recovery_after_08e_r1/`

Forbidden changes (none made):
- `langgraph_parity_runtime.py`
- `native_runtime.py`
- Frontend files
- Dashboard static files
- Memory/FAISS/trading/.env files
