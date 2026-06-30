# Validation Results — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2

## Py-compile

| File | Result |
|------|--------|
| `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` | PASS |
| `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py` | PASS |

## Smoke tests

| Test | Result |
|------|--------|
| `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py` | 10 passed |
| `tests/smoke/test_brain_agent_v2_runtime_selector_guard_08e.py` | 14 passed |
| `tests/smoke/test_brain_agent_v2_backend_response_normalization_08e.py` | 12 passed |
| `tests/smoke/test_brain_dashboard_chat_proxy_token_fix_08e_r3.py` (isolated) | 3 passed |
| `tests/smoke/test_brain_dashboard_chat_proxy_token_fix_08e_r3.py` (batched with 08F1 tests) | 1 passed, 2 failed due to test isolation/state |

### R3 batched-run note

When the R3 dashboard token proxy test is executed in the same pytest session as the LangGraph opt-in contract tests, two R3 assertions fail because the dashboard route environment state (cached app import, `AGENT_V2_BACKEND`, strict-operator bypass state) differs from the isolated run. Running R3 by itself yields 3 passes. This is a known test-isolation artifact; no source code was modified to address it in this reports-only front.

## Git hygiene guard

`scripts/git_hygiene/check_no_sensitive_paths_staged.py` → SAFE

## Phase smoke results

| Phase | Result |
|-------|--------|
| Native default smoke | PASS |
| LangGraph opt-in direct runtime smoke | PASS |
| `/v2/chat/agent` schema smoke | PASS |
| Trace smoke | PASS |
| Read-only governance smoke | PASS |
| Fallback smoke | PASS |
| Dashboard proxy smoke | PASS (routes reachable, no token leak; backend not live) |

## Contract verification

- Native default preserved: yes
- LangGraph default activation: no
- LangGraph canary started: yes, controlled local smoke only
- LangGraph runtime selected when opt-in: yes
- LangGraph opt-in direct runtime OK: yes
- Normalized chat schema passed: yes
- Trace contract passed: yes
- Read-only governance passed: yes
- Fallback to Native preserved: yes
- Dashboard proxy smoke result: PASS
