# Recommended 08F1 Implementation Plan

**Front name**: FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1  
**Derived from**: FRONT-BRAIN-AGENT-V2-CONTROLLED-BACKEND-OPT-IN-READINESS-REVIEW-08F0  
**Source head**: 883df0a

## Purpose

Implement a controlled source patch that makes `LangGraphParityRuntimeV2` satisfy the production Agent V2 runtime contract, while keeping Native as the default and only activating LangGraph when explicitly requested via `AGENT_V2_BACKEND`.

## Design Principles

1. NativeAgentRuntimeV2 remains the default backend.
2. LangGraph is opt-in only via `AGENT_V2_BACKEND` env var.
3. Do not make LangGraph the default.
4. Preserve the fallback-to-native guard in `runtime.py`.
5. Keep `/v2/chat/agent` response schema stable via `response_normalizer.py`.
6. No dashboard/frontend changes unless strictly necessary.
7. No memory/FAISS/trading/env changes.

## Allowed Source Files

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py` (only for logging/clarity; no relaxation of fallback guard)

## Allowed Test Files

- `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py`

## Prohibited Files

- `tmp_agent/brain_v9/api_security.py`
- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/dashboard/dashboard_routes.py`
- `tmp_agent/brain_v9/dashboard/dashboard_app.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py`
- `tmp_agent/brain_v9/memory/*`
- `tmp_agent/brain_v9/financial/*`
- `tmp_agent/brain_v9/strategies/*`
- `.env`
- `frontend/*`
- `tmp_agent/brain_v9/dashboard/static/*`

## Exact Changes

### `langgraph_parity_runtime.py`

Add production-runtime wrapper methods:

- `create_run(self, goal: str, mode: str = "read_only", user_id: str = "local") -> Dict[str, Any]`
  - Validate mode via `validate_mode`.
  - Generate `run_id` matching Native format: `agv2_<16-char-hex-sha256>`.
  - Persist initial `run.json` and a trace event.
  - Return a Native-compatible run dict.

- `execute_run(self, run_id: str) -> Dict[str, Any]`
  - Load run from `run.json`.
  - Invoke the existing graph via `self.run(run["goal"], run["mode"], run["user_id"])` or `_graph.invoke()`.
  - Translate graph final state into a Native-style run dict containing:
    - `run_id`, `final_answer`, `status`, `provider_metadata`, `capability_metadata`
    - `mode_requested`, `mode_effective`, `mode_escalation_required`
    - `intent_route`, `intent_detected`, `intent_confidence`, `classification`
    - `backend_selected`, `backend_fallback_used`, `backend_fallback_reason`
  - Persist updated `run.json`.
  - Append trace events.

- `plan_run(self, run_id: str) -> Dict[str, Any]`
  - For LangGraph, planning happens inside the graph. Return the loaded run (or a no-op marker).

- `list_runs(self) -> List[Dict[str, Any]]`
  - Scan `self.run_root` for `*/run.json`, same as Native.

- `pause_run`, `resume_run`, `cancel_run`
  - Safe no-op or `NotImplementedError` with graceful handling in `api_adapter` if needed.
  - Do not break `/v2/chat/agent`.

### `runtime.py`

- Preserve existing fallback guard.
- Optionally improve the warning message when `is_agent_v2_production_runtime_compatible` fails.
- Do **not** bypass or relax the compatibility check.

## Exact Tests to Add

Create `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py` with:

1. `test_langgraph_backend_selected_when_env_set` — with `AGENT_V2_BACKEND=langgraph`, verify `get_agent_runtime_v2().backend_selected == "langgraph_parity"` (when package available).
2. `test_langgraph_create_and_execute_run_return_native_style_run` — verify `create_run`/`execute_run` return dict with `run_id`, `final_answer`, `status`, `provider_metadata`, `capability_metadata`.
3. `test_langgraph_chat_agent_endpoint_normalized_response` — use `TestClient` to hit `/v2/chat/agent` and assert all required top-level/provider/capability fields are present with `backend_selected="langgraph_parity"`.
4. `test_langgraph_read_only_blocks_writes` — verify `mode_escalation_required=True` and write tools blocked when build intent detected in `read_only` mode.
5. `test_langgraph_unavailable_or_incompatible_falls_back_to_native` — verify fallback metadata when LangGraph package missing or wrapper incomplete.
6. `test_langgraph_trace_contract` — verify `/v2/agent/runs/{run_id}/trace` works after a LangGraph run.

## Validations to Run

```bash
python -m py_compile tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py
python -m py_compile tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py
python -m pytest tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py -v
python -m pytest tests/smoke/test_brain_agent_v2_runtime_selector_guard_08e.py -v
python -m pytest tests/smoke/test_brain_dashboard_chat_proxy_token_fix_08e_r3.py -v
python scripts/git_hygiene/check_no_sensitive_paths_staged.py
```

## Live Smoke Expectations

- Backend health/status PASS with default backend.
- With `AGENT_V2_BACKEND=langgraph` and valid setup, `/v2/chat/agent` returns `ok=true` and normalized schema.
- Dashboard chat and trace proxies continue to work.
- Fallback to `native_runtime` occurs if LangGraph setup is invalid.

## CI Expectations

- `phase1-ci` green
- `nontrading-smoke-regression` green

## Rollback Plan

1. Unset `AGENT_V2_BACKEND` or set it to `native_runtime` to restore Native default.
2. If needed, revert only `langgraph_parity_runtime.py` and remove the 08F1 test file.
3. The existing fallback guard in `runtime.py` ensures Native works even if LangGraph code is partially present.

## Acceptance Criteria

- LangGraph selectable only when `AGENT_V2_BACKEND=langgraph` and package is available.
- `runtime.py` production compatibility check passes (`create_run` and `execute_run` callable).
- `/v2/chat/agent` returns stable normalized response schema regardless of backend.
- Native remains default and fallback is safe.
- Dashboard proxies work for both backends.
- CI green on `phase1-ci` and `nontrading-smoke-regression`.
