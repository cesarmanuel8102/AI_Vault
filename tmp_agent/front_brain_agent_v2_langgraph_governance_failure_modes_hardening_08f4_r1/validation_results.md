# Validation Results — 08F4-R1

## Commands run

### 1. Compile checks

```text
python -m py_compile tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py tmp_agent/brain_v9/core/agent_kernel_v2/governance.py tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py
```

Result: PASS (no output)

### 2. New focused failure-mode smoke tests

```text
python -m pytest tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py -v --timeout=120
```

Result: **10 passed, 0 failed, 0 skipped**

Tests:

- test_execute_run_returns_failed_state_on_timeout
- test_run_method_returns_failed_state_on_timeout
- test_execute_run_rejects_missing_required_fields
- test_execute_run_rejects_invalid_json_run_state
- test_get_run_returns_failed_stub_for_malformed_state
- test_auto_mode_write_intent_escalates_to_approval_required
- test_auto_mode_harmless_query_does_not_escalate
- test_native_default_unchanged
- test_langgraph_opt_in_still_selects_langgraph
- test_only_allowed_source_files_modified

### 3. 08F1 regression contract tests

```text
python -m pytest tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py -k "not test_only_allowed_source_files_modified" -v --timeout=120
```

Result: **9 passed, 0 failed, 1 deselected**

The scope guard in 08F1 was intentionally deselected because it is frozen to 08F1's allowed prefixes and does not include the new `governance.py` and 08F4 test file. The 08F4 smoke suite has its own up-to-date scope guard.

### 4. Hygiene guard

```text
python scripts/git_hygiene/check_no_sensitive_paths_staged.py
```

Result: **SAFE: no sensitive/runtime content staged as added/modified/copied.**

## Scope audit

Changed tracked files (excluding untracked workspace artifacts):

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`
- `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py`
- `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4_r1/*`

Allowed per front rules. No forbidden files touched.

## CI status at commit time

To be updated after push.
