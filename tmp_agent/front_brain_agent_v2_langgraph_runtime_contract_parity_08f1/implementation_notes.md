# Implementation Notes — FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1

## Source changes

### `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

Added production runtime contract methods:

- `create_run(goal, mode='read_only', user_id='local')` — validates mode, generates `agv2_<hash>` id, persists `run.json`, appends trace event, returns Native-style run dict.
- `execute_run(run_id)` — loads run, invokes existing LangGraph graph via `self.run()`, translates graph final state into Native-style run dict, persists, appends trace events.
- `plan_run(run_id)` — returns loaded run with graph-internal planner marker.
- `list_runs()` — scans `run_root` for `*/run.json`.
- `pause_run`, `resume_run`, `cancel_run` — safe lifecycle status updates.
- `_translate_graph_state_to_native_run(run, graph_state)` — internal helper that extracts `final_answer`, populates `provider_metadata`, `capability_metadata`, mode/governance fields, backend metadata, and `trace_url`.
- `_extract_final_answer(graph_state)` — best-effort extraction from common keys.

`runtime.py` was **not modified**. The existing fallback guard continues to select Native by default and fall back to Native if LangGraph is unavailable or incompatible.

## Test changes

- `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py` — new contract tests covering interface parity, create/execute, selector opt-in, native default, fallback, `/v2/chat/agent` normalized schema, trace contract, read-only governance, and scope guard.
- `tests/smoke/test_brain_agent_v2_backend_response_normalization_08e.py` — minimal update to remove `langgraph_parity_runtime.py` from an outdated forbidden-modification list. This was necessary because 08F1 is explicitly authorized to modify that file.

## Design principles maintained

1. NativeAgentRuntimeV2 remains default.
2. LangGraph opt-in only via `AGENT_V2_BACKEND`.
3. No dashboard/frontend/api_security/main/api_adapter/native_runtime/response_normalizer changes.
4. No memory/FAISS/trading/env changes.
5. Rollback is safe: unset env or revert `langgraph_parity_runtime.py` and the new test.

## Rollback plan

1. Unset `AGENT_V2_BACKEND` or set to `native_runtime`.
2. Revert `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`.
3. Remove `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py`.
4. Restore the 08E scope guard if fully reverting 08F1.
5. `runtime.py` fallback guard ensures Native continues to work.
