# Smoke Validation Matrix — 08F7

## Phase

6 — Smoke validation matrix

## Summary

| Metric | Value |
|---|---|
| Total tests run | 37 |
| Passed | 37 |
| Failed | 0 |
| Skipped | 0 |
| py_compile | PASSED |
| Hygiene | SAFE |

## Validations

| # | Command | Environment | Result | Pass/Fail | Blocking | Notes |
|---|---|---|---|---|---|---|
| 1 | `py_compile runtime.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 2 | `py_compile langgraph_parity_runtime.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 3 | `py_compile native_runtime.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 4 | `py_compile governance.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 5 | `py_compile api_adapter.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 6 | `py_compile response_normalizer.py` | `AGENT_V2_BACKEND` unset | PASSED | PASS | No | Syntax check only |
| 7 | `pytest test_brain_agent_v2_runtime_selector_guard_08e.py` | `AGENT_V2_BACKEND` unset | 14 passed | PASS | No | Native default and fallback behavior |
| 8 | `pytest test_brain_agent_v2_langgraph_backend_contract_08f1.py` | `AGENT_V2_BACKEND=langgraph` | 10 passed | PASS | No | LangGraph backend contract under opt-in |
| 9 | `pytest test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` | `AGENT_V2_BACKEND=langgraph` | 10 passed | PASS | No | LangGraph failure modes and governance escalation |
| 10 | `pytest test_brain_dashboard_chat_proxy_token_fix_08e_r3.py` | `AGENT_V2_BACKEND` unset | 3 passed | PASS | No | Dashboard chat/trace proxy token handling |
| 11 | `pytest test_brain_agent_v2_runtime_selector_guard_08e.py` | `AGENT_V2_BACKEND` unset (post-rollback) | 14 passed | PASS | No | Rollback to Native verified |
| 12 | `python scripts/git_hygiene/check_no_sensitive_paths_staged.py` | `AGENT_V2_BACKEND` unset | SAFE | PASS | No | No sensitive/runtime content staged |

## Result

All 37 smoke tests passed. No failures, no blockers.

## Phase result

PHASE 6 — Smoke validation matrix: **COMPLETED**

## Recorded

`2026-06-30T19:30:00+00:00`
