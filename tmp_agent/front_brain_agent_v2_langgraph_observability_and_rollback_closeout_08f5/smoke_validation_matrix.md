# Smoke Validation Matrix — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Purpose

Record all smoke validations executed for the 08F5 operational closeout.

## Test results

| Test file | Description | Env | Result | Passed | Failed | Skipped |
|---|---|---|---|---|---|---|
| `test_brain_agent_v2_runtime_selector_guard_08e.py` | Runtime selector guard contract (Native default, invalid fallback, LangGraph opt-in) | default / set by test | PASSED | 14 | 0 | 0 |
| `test_brain_dashboard_chat_proxy_token_fix_08e_r3.py` | Dashboard chat/trace proxy forwards `X-Brain-Token` without leaking it | default | PASSED | 3 | 0 | 0 |
| `test_brain_agent_v2_langgraph_backend_contract_08f1.py` | LangGraph parity runtime contract and `/v2/chat/agent` normalized schema | `AGENT_V2_BACKEND=langgraph` | PASSED | 10 | 0 | 0 |
| `test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` | LangGraph failure modes: timeout, malformed run state, auto escalation, default preservation | `AGENT_V2_BACKEND=langgraph` | PASSED | 10 | 0 | 0 |

## Totals

- Tests run: 37
- Passed: 37
- Failed: 0
- Skipped: 0

## Additional hygiene

| Check | Result |
|---|---|
| `py_compile` on runtime, API, dashboard, normalizer | PASSED |
| `scripts/git_hygiene/check_no_sensitive_paths_staged.py --dry-run` | SAFE |

## Phase result

PHASE 6 — Smoke validation matrix: **COMPLETED**

## Recorded

`2026-06-30T17:05:00+00:00`
