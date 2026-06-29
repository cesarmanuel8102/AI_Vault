# FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D — Final Report

**Front ID:** FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D  
**Branch:** `codex/own-capital-sustainable-return`  
**Baseline / Starting Head:** `af5636b`  
**Final Head:** `4adab4d`  
**Status:** `validated`

## Scope

This front executed the 08C recommendation **B: Add endpoint contract tests before blueprint**. Only tests and reports were added. No runtime selector, api_adapter.py, dashboard, frontend, memory, FAISS, trading, or `.env` files were modified. LangGraph was **not** activated.

## Test Files Added

| File | Purpose |
|------|---------|
| `tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py` | Pins `/v2/chat/agent`, `/v2/agent/*`, legacy chat, and OpenAI-compat contracts |
| `tests/smoke/test_brain_dashboard_chat_contracts_08d.py` | Pins dashboard 8092 → 8091 proxy contracts for chat and trace |
| `tests/smoke/test_brain_agent_v2_trace_contracts_08d.py` | Pins trace schema, trace_url resolution, and visual trace route registration |

## Validation Results

- `python -m py_compile` on all 3 test files: **passed**
- `pytest tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py -v --timeout=120`: **14 passed**
- `pytest tests/smoke/test_brain_dashboard_chat_contracts_08d.py -v --timeout=120`: **9 passed**
- `pytest tests/smoke/test_brain_agent_v2_trace_contracts_08d.py -v --timeout=120`: **7 passed**
- Security unit tests (`test_execution_gate_god_p3.py`, `test_dev_endpoints_default_off.py`, `test_selfdev_protected_paths.py`): **15 passed**
- `scripts/git_hygiene/check_no_sensitive_paths_staged.py`: **SAFE**

## Production Wiring State

- `runtime.py` still returns only `NativeAgentRuntimeV2`.
- `api_adapter.py` still owns `/v2/chat/agent` and `/v2/agent/*`.
- `dashboard_routes.py` still proxies chat and trace to `127.0.0.1:8091`.
- Legacy `/chat` and `/v1/chat/completions` still bypass Agent V2.
- Visual trace endpoints remain runtime-independent.

## Known 08C Gaps Recorded (Not Fixed)

1. **LangGraph `expected_write_scope` / `auto_decision`** — missing from current LangGraph runtime.
2. **Trace event type mismatch** — LangGraph node-based events vs Native `plan_created`, `tool_call_*`.
3. **Trace `run_root` mismatch** — LangGraph default differs from Native `RUN_ROOT`.
4. **LangGraph unavailable error handling** — blocking gap; runtime selector must fall back to Native.

## Source Files Modified

None.

## Next Recommended Action

Implement response normalization adapter and runtime selector guard before activating `AGENT_V2_BACKEND` flag. The contract tests added here become the regression suite that any such wiring must satisfy.
