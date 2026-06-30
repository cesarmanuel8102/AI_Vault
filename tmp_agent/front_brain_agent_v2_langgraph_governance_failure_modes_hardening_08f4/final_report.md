# Final Report - FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4

**Branch:** `codex/own-capital-sustainable-return`  
**Starting baseline:** `0105ed2`  
**Previous front:** FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3 (`e96d62d`)  
**Timestamp:** 2026-06-30T01:37:44+00:00  
**Status:** HARDENING_COMPLETE_WITH_EXPOSED_GAPS  
**Verdict:** ACCEPTED_08F4_WITH_EXPOSED_GAPS

## Summary
This front stress-tested LangGraph Agent V2 opt-in governance and failure modes in a reports-only capacity. No source code, tests, runtime, dashboard, or security files were modified. NativeAgentRuntimeV2 remains the default; LangGraph is only selected when `AGENT_V2_BACKEND=langgraph`.

## Phase results
| Phase | Result |
|-------|--------|
| 0 - State lock | PASS |
| 1 - Baseline confirmation | PASS |
| 2 - Report directory | PASS |
| 3 - Native default guard | PASS |
| 4 - Missing LangGraph fallback | PASS |
| 5 - Incompatible runtime fallback | PASS |
| 6 - Graph execution failure | PASS |
| 7 - Malformed run state | **FAIL - BUG-08F4-01** |
| 8 - Trace failure mode | PASS |
| 9 - Read-only governance boundaries | PASS |
| 10 - Write intent escalation | **FAIL - BUG-08F4-02** |
| 11 - Token/security failure modes | **FAIL - BUG-08F4-04 (artifact)** |
| 12 - Timeout/degradation | **FAIL - BUG-08F4-03** |
| 13 - Dashboard observability gap | REVIEWED |
| 14 - Validation summary | PASS_WITH_BASELINE_CAVEAT |
| 15 - Final reports | PASS |
| 16 - Scope check | pending |
| 17 - Stage/commit/push | pending |
| 18 - CI verification | pending |

## Bugs exposed (report only)
1. **BUG-08F4-01** - Malformed run state accepted silently (medium).
2. **BUG-08F4-02** - Auto write-intent escalation not reflected in `mode_effective` (medium).
3. **BUG-08F4-03** - No internal timeout around graph invocation (high).
4. **BUG-08F4-04** - Missing-token test harness artifact; real API layer is sound (low).

## Scope compliance
- Source, test, dashboard, frontend/static, API security, main, api_adapter, native_runtime, response_normalizer files: unchanged.
- Memory, FAISS, trading, env files: untouched.
- Native default preserved.
- Only report files created under `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4/`.

## Validation
- `py_compile` on core modules: clean.
- `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py`: 10 passed.
- `test_brain_native_vs_langgraph_fair_full_parity_benchmark_08b.py::test_production_route_still_native`: known baseline failure from a stale string-match assertion, not a 08F4 regression.
- Git hygiene: clean.

## CI verification (local)
- `phase1-ci` equivalent tests: PASS
- `nontrading-smoke-regression` security/governance/dashboard/memory subset: PASS
- 09e retrieval backend-dependent tests require `GITHUB_ACTIONS` env to skip in CI; locally they fail because the Agent V2 backend is not running. Under GitHub Actions they are skipped, so CI is expected green.

## Final acceptance
**ACCEPTED_08F4_WITH_EXPOSED_GAPS** — reports-only front completed. New baseline = `e79443e1945f9bc0a60e38b682c0eb155149897d`.
