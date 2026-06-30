# Diagnostic Summary - FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4

**Status:** ACCEPTED_08F4_WITH_EXPOSED_GAPS

**Scope:** reports-only. No source code, tests, runtime, dashboard, or security files were modified.

## Baseline
- **Branch:** `codex/own-capital-sustainable-return`
- **Starting baseline:** `0105ed2`
- **Previous front:** FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3 (accepted at `e96d62d`)

## What was verified
| Phase | Topic | Result |
|-------|-------|--------|
| 0 | State lock at `0105ed2` | PASS |
| 1 | Confirm 08F3 baseline evidence | PASS |
| 2 | Create report directory | PASS |
| 3 | Native default guard (unset `AGENT_V2_BACKEND`) | PASS |
| 4 | Missing LangGraph fallback smoke | PASS |
| 5 | Incompatible runtime fallback smoke | PASS |
| 6 | Graph execution failure smoke | PASS |
| 7 | Malformed run state smoke | **FAIL - bug exposed** |
| 8 | Trace failure mode smoke | PASS |
| 9 | Read-only governance boundaries | PASS |
| 10 | Write intent escalation smoke | **FAIL - bug exposed** |
| 11 | Token/security failure mode smoke | **FAIL - test harness artifact** |
| 12 | Timeout/degradation smoke | **FAIL - bug exposed** |
| 13 | Dashboard observability gap review | REVIEWED |
| 14 | Validation summary | PASS_WITH_BASELINE_CAVEAT |

## Bugs exposed (report only — no patches in 08F4)

### BUG-08F4-01: Malformed run state accepted silently
- **Location:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- **Severity:** medium
- **Description:** A `run.json` with missing required fields (`goal`, `mode`) is not rejected. `execute_run` returns `status="completed"` with no error.
- **Recommendation:** Add schema validation at create/execute time; reject incomplete runs with `status="failed"` and a clear error.

### BUG-08F4-02: Auto write-intent escalation not reflected in run state
- **Location:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- **Severity:** medium
- **Description:** `governance.mode_requires_escalation()` correctly returns `true` for `auto` + write intent, but `mode_effective` stays `auto` instead of escalating to `build_required`.
- **Recommendation:** When escalation is required, set `mode_effective="build_required"` and block or escalate before any write tool is scheduled.

### BUG-08F4-03: No internal timeout around graph invocation
- **Location:** `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- **Severity:** high
- **Description:** `execute_run` has no internal timeout. A stalled graph node hangs the call until the external client times out.
- **Recommendation:** Wrap graph invocation in a timeout (e.g., `asyncio.wait_for`) and return `status="failed"` with a timeout/circuit-breaker response.

### BUG-08F4-04 (artifact): missing_token_header synchronous invocation
- **Location:** test harness only
- **Severity:** low / test artifact
- **Description:** Calling the async FastAPI dependency `require_strict_operator_access` directly from synchronous code returns a coroutine rather than raising 401/403. Under real FastAPI request handling it is awaited and behaves correctly.

## Scope compliance
All report-only constraints were respected:
- No source, test, runtime, dashboard, frontend/static, API security, main, api_adapter, native_runtime, response_normalizer, memory, FAISS, trading, or env files modified.
- Native default remains the default.
- LangGraph is only selected when `AGENT_V2_BACKEND=langgraph`.

## Validation
- `py_compile` on core modules: clean.
- Relevant smoke (`test_brain_agent_v2_langgraph_backend_contract_08f1.py`): 10 passed.
- 08b `test_production_route_still_native`: known baseline failure due to stale string-match assertion (not a regression).
- Git hygiene: clean.

## Recommendations for follow-up fronts
1. Fix BUG-08F4-01 by adding run-state schema validation.
2. Fix BUG-08F4-02 by reflecting escalation in `mode_effective`.
3. Fix BUG-08F4-03 by adding an internal graph-invocation timeout.
4. Update dashboard chat proxy to include `backend_selected`/`backend_fallback_used` in its response.
5. Update or relax the 08b `test_production_route_still_native` assertion so it checks behavior rather than a literal absence of the module name in source.
