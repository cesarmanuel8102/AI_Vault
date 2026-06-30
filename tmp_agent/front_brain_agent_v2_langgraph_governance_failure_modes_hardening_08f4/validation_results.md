# PHASE 14 - Validation summary

**Status:** PASS_WITH_BASELINE_CAVEAT

## Checks performed

### 1. py_compile on core runtime/API/dashboard modules
- **Command:** `python -m py_compile tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py langgraph_parity_runtime.py governance.py native_runtime.py response_normalizer.py api_adapter.py tmp_agent/brain_v9/api_security.py main.py dashboard/dashboard_routes.py`
- **Result:** PASS — all targeted modules compile without syntax errors.

### 2. Relevant smoke tests
- **Command:** `python -m pytest tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py -q`
- **Result:** PASS — 10 passed, 0 failed.
- **Notes:** 08F1 contract tests confirm runtime metadata parity and backend fallback fields.

### 3. Native-default benchmark regression check
- **Command:** `python -m pytest tests/smoke/test_brain_native_vs_langgraph_fair_full_parity_benchmark_08b.py::test_production_route_still_native -q`
- **Result:** KNOWN_FAIL_BASELINE
- **Details:** The 08b test asserts `langgraph_parity_runtime` does not appear anywhere in `runtime.py` source. Current `runtime.py` legitimately references the string in `LANGGRAPH_BACKEND_VALUES` and the `_try_build_langgraph_runtime` import while keeping Native the default. This is a stale, overly strict assertion, not a 08F4 regression. Not patched per reports-only scope.

### 4. Git hygiene guard
- **Result:** PASS
- **Findings:** No tracked source, test, runtime, dashboard, frontend/static, api_security, main, api_adapter, native_runtime, or response_normalizer files are modified. Only new untracked report files exist under `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4/`.

## Conclusion
Core modules compile cleanly, the relevant 08F1 contract smoke passes, and repository hygiene is clean. The single 08b failure is a pre-existing stale test assertion and is documented as a baseline caveat.
