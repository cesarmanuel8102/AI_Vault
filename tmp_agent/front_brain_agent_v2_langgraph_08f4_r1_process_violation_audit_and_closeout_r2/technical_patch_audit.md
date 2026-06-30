# Technical Patch Audit — 08F4-R1 Process Violation Audit R2

## Scope

This is a read-only audit of the source changes introduced by the rejected 08F4-R1 front. No source code was modified in this audit.

## Files changed since clean baseline `d2f5737`

| File | Status | Allowed |
|---|---|---|
| `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` | Modified | Yes |
| `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py` | Modified | Yes |
| `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` | Added | Yes |
| `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4_r1/*` | Added | Yes (report directory) |

No forbidden files were modified.

## BUG-08F4-03 — Internal timeout / circuit-breaker

**Status:** Present in the patch.

Evidence in `langgraph_parity_runtime.py`:

- Class constant `DEFAULT_EXECUTE_TIMEOUT_SECONDS = 30.0` added.
- Constructor parameter `execute_timeout_seconds` added.
- `run()` now calls `_invoke_with_timeout()` instead of direct `_graph.invoke()`.
- `_invoke_with_timeout()` submits graph invocation to a single-use `ThreadPoolExecutor(max_workers=1)` and waits with `future.result(timeout=...)`.
- On `TimeoutError`, it returns `_build_timeout_state()`.
- `_build_timeout_state()` returns a Native-style terminal dict with `status="failed"`, `error="timeout"`, and a `final_answer` explaining the degradation.
- Executor shutdown uses `wait=False, cancel_futures=True` so a non-terminating node cannot trap the calling thread.

## BUG-08F4-01 — Malformed run state handling

**Status:** Present in the patch.

Evidence in `langgraph_parity_runtime.py`:

- `_REQUIRED_RUN_FIELDS = {"run_id", "goal", "mode"}` added.
- `_is_run_state_valid()` validates required fields.
- `get_run()` returns a controlled failed stub for invalid JSON or missing required fields.
- `_load_run_or_raise()` reads raw `run.json` and returns a `_malformed` marker on parse failure.
- `execute_run()` validates loaded run and calls `_create_malformed_run_response()` when invalid.
- `_create_malformed_run_response()` persists a failed run with `error="malformed_run_state"`.

## BUG-08F4-02 — Auto write-intent escalation reflection

**Status:** Present in the patch.

Evidence:

- `governance.py` adds `escalate_auto_mode_effective(mode_requested, escalation_required, goal)`.
- In `langgraph_parity_runtime.py`, `_governance_gate_node()` calls this helper when `mode_requested == "auto"`.
- `mode_effective` is updated to `"approval_required"` while `mode_requested` remains `"auto"`.
- `_translate_graph_state_to_native_run()` carries `mode_effective` forward into the returned run dict.

## Default / opt-in behavior

- `runtime.py` was not modified.
- `main.py`, `api_adapter.py`, `api_security.py`, `native_runtime.py`, and `response_normalizer.py` were not modified.
- Native remains the default runtime.
- LangGraph remains opt-in via `AGENT_V2_BACKEND=langgraph`.

## Forbidden scope check

| Area | Changed |
|---|---|
| Dashboard/frontend | No |
| `api_security.py` | No |
| `main.py` | No |
| `api_adapter.py` | No |
| `native_runtime.py` | No |
| `response_normalizer.py` | No |
| Memory/semantic files | No |
| FAISS/vector indexes | No |
| Trading/IBKR/broker/strategy/portfolio/risk | No |
| `.env` or secrets | No |
| Autonomous journal | No |
| Promotion queues | No |

## Technical patch scope verdict

**Allowed.** The three 08F4 safety gaps are addressed by the patch, and no forbidden scope changes are present.
