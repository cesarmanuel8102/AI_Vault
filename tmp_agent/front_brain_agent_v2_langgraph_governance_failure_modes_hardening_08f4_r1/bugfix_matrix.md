# Bugfix Matrix — 08F4-R1

| ID | Severity | Symptom | Root cause | Fix | Test evidence |
|---|---|---|---|---|---|
| BUG-08F4-03 | Blocking / High | Graph invocation could hang the caller thread forever | `_graph.invoke()` called directly with no bounded wait | Wrap invocation in `ThreadPoolExecutor(max_workers=1)` with `future.result(timeout=...)`; on timeout return a safe failed state and shutdown executor without waiting for the worker | `test_execute_run_returns_failed_state_on_timeout`, `test_run_method_returns_failed_state_on_timeout` |
| BUG-08F4-01 | Medium | Partial `run.json` was accepted and the graph produced a misleading `completed` result | `execute_run()` loaded the run via `get_run()` which returned a stub but `execute_run()` did not validate required fields | Added `_REQUIRED_RUN_FIELDS` and `_is_run_state_valid()`; `execute_run()` now rejects invalid state and `_load_run_or_raise()` returns a `_malformed` marker for unparseable JSON | `test_execute_run_rejects_missing_required_fields`, `test_execute_run_rejects_invalid_json_run_state`, `test_get_run_returns_failed_stub_for_malformed_state` |
| BUG-08F4-02 | Medium | `mode=auto` + write intent escalated internally but the run state still reported `mode_effective=auto` | Governance escalation set flags but did not update `mode_effective` | Added `escalate_auto_mode_effective()` to `governance.py` and applied it in `_governance_gate_node()` when `mode_requested == "auto"` | `test_auto_mode_write_intent_escalates_to_approval_required`, `test_auto_mode_harmless_query_does_not_escalate` |

## Regression matrix

| Concern | Test | Result |
|---|---|---|
| Native default preserved | `test_native_default_unchanged` | PASS |
| LangGraph opt-in still works | `test_langgraph_opt_in_still_selects_langgraph` | PASS |
| 08F1 runtime contract methods | `test_langgraph_runtime_has_required_methods` | PASS |
| 08F1 create/execute run schema | `test_create_run_returns_native_style_run`, `test_execute_run_returns_native_style_run` | PASS |
| 08F1 read-only governance | `test_read_only_blocks_write_intent` | PASS |
| Scope guard | `test_only_allowed_source_files_modified` (08F4 suite) | PASS |
