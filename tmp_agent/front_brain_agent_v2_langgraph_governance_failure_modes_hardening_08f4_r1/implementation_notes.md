# Implementation Notes — 08F4-R1

## Overview

This front hardens the opt-in LangGraph parity runtime against the governance and execution failure modes catalogued in the 08F4 process-violation audit. Native remains the default. Only the isolated `LangGraphParityRuntimeV2` and the shared `governance` helper were modified.

## Changes

### 1. BUG-08F4-03 — Internal timeout / circuit-breaker

**File:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

- Added class constant `DEFAULT_EXECUTE_TIMEOUT_SECONDS = 30.0` and constructor parameter `execute_timeout_seconds`.
- Replaced direct `_graph.invoke()` in `run()` with `_invoke_with_timeout()`.
- `_invoke_with_timeout()` uses a single-use `ThreadPoolExecutor(max_workers=1)` to run the graph in a separate thread.
- On `concurrent.futures.TimeoutError`, it returns a safe terminal state built by `_build_timeout_state()`.
- The executor is shut down with `wait=False, cancel_futures=True` so a non-terminating node cannot trap the calling thread during shutdown.
- `_build_timeout_state()` returns a Native-style dict with:
  - `status = "failed"`
  - `error = "timeout"`
  - `final_answer` explaining the degradation
  - `backend_selected = "langgraph_parity"`
  - Capability/provider metadata preserved
  - Persisted `run.json`

### 2. BUG-08F4-01 — Malformed run state handling

**File:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

- Added `_REQUIRED_RUN_FIELDS = {"run_id", "goal", "mode"}` and `_is_run_state_valid()`.
- `get_run()` now returns a controlled failed stub for invalid JSON or missing required fields.
- `_load_run_or_raise()` reads raw `run.json` and returns a `_malformed` marker dict on parse failure instead of raising.
- `execute_run()` validates the loaded run and calls `_create_malformed_run_response()` when invalid.
- `_create_malformed_run_response()` persists a Native-style failed run with `error = "malformed_run_state"`, provider metadata flagging degradation, and a trace event.

### 3. BUG-08F4-02 — Auto write-intent escalation reflection

**File:** `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`

- Added `escalate_auto_mode_effective(mode_requested, escalation_required, goal)`.
- When `mode_requested == "auto"` and escalation is required, returns `"approval_required"`; otherwise returns the requested mode unchanged.

**File:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

- Imported `escalate_auto_mode_effective`.
- In `_governance_gate_node()`, after computing `mode_requires_escalation`, if `mode_requested == "auto"` the node's `mode_effective` is updated to `approval_required`.
- `mode_requested` is preserved as `auto` so the caller can see both the original request and the governance decision.
- `_translate_graph_state_to_native_run()` now carries `mode_effective = "approval_required"` into the returned run dict.

### 4. Test coverage

**File:** `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` (new)

Ten focused tests covering:

- `test_execute_run_returns_failed_state_on_timeout`
- `test_run_method_returns_failed_state_on_timeout`
- `test_execute_run_rejects_missing_required_fields`
- `test_execute_run_rejects_invalid_json_run_state`
- `test_get_run_returns_failed_stub_for_malformed_state`
- `test_auto_mode_write_intent_escalates_to_approval_required`
- `test_auto_mode_harmless_query_does_not_escalate`
- `test_native_default_unchanged`
- `test_langgraph_opt_in_still_selects_langgraph`
- `test_only_allowed_source_files_modified`

## Scope discipline

- No production wiring changed in `runtime.py`, `api_adapter.py`, or `main.py`.
- No trading/broker/portfolio/risk, memory/vector-index, dashboard/frontend/api_security, or secrets files modified.
- `runtime.py` was not modified; `governance.py` was modified only because the escalation helper is shared and stateless.

## Known diagnostics

The LSP/Pylance reports type errors inside `_build_graph()` because `GRAPH_START`/`GRAPH_END` are typed as `Optional[LiteralString]` and `StateGraph(dict)` expects a TypedDict. These warnings existed before this front and do not affect runtime behavior or `py_compile`.
