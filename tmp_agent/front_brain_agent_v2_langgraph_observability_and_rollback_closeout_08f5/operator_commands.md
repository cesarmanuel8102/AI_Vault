# Operator Commands — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Purpose

Quick-reference operator commands for observing, selecting, and rolling back the Agent V2 backend.

## Environment and inspection

| Command | PowerShell |
|---|---|
| Show current `AGENT_V2_BACKEND` | `$env:AGENT_V2_BACKEND` |
| Opt in to LangGraph (session only) | `$env:AGENT_V2_BACKEND = 'langgraph'` |
| Return to Native (session only) | `$env:AGENT_V2_BACKEND = 'native'` |
| Remove env var (Native default) | `Remove-Item Env:\AGENT_V2_BACKEND` |

## Runtime probes

| Command | PowerShell |
|---|---|
| Instantiate selector and print backend + fallback | `python -c "from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2; rt=get_agent_runtime_v2(); print(rt.backend, getattr(rt, 'backend_selected', 'n/a'), getattr(rt, 'backend_fallback_used', 'n/a'), getattr(rt, 'backend_fallback_reason', 'n/a'))"` |
| Resolved backend name only | `python -c "from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_backend_name; print(get_agent_runtime_backend_name())"` |

## Server startup

| Command | PowerShell |
|---|---|
| Start with Native default | `python -m tmp_agent.brain_v9.main` |
| Start with LangGraph opt-in | `$env:AGENT_V2_BACKEND='langgraph'; python -m tmp_agent.brain_v9.main` |

## Endpoint checks

| Command | PowerShell |
|---|---|
| `/v2/agent/status` | `Invoke-RestMethod -Uri http://127.0.0.1:8091/v2/agent/status -UseBasicParsing` |
| `/v2/chat/agent` chat probe | `Invoke-RestMethod -Uri http://127.0.0.1:8091/v2/chat/agent -Method POST -Body '{\"message\":\"status check\",\"mode\":\"read_only\",\"user_id\":\"operator\"}' -ContentType 'application/json' -UseBasicParsing` |
| Dashboard agent-v2 status | `Invoke-RestMethod -Uri http://127.0.0.1:8090/brain-dashboard/agent-v2/status -UseBasicParsing` |

## Smoke tests

| Command | PowerShell |
|---|---|
| Selector guard (Native default) | `pytest tests/smoke/test_brain_agent_v2_runtime_selector_guard_08e.py -v` |
| LangGraph contract | `$env:AGENT_V2_BACKEND='langgraph'; pytest tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py -v` |
| LangGraph failure modes | `$env:AGENT_V2_BACKEND='langgraph'; pytest tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py -v` |
| Dashboard chat proxy token | `pytest tests/smoke/test_brain_dashboard_chat_proxy_token_fix_08e_r3.py -v` |

## Git / hygiene

| Command | PowerShell |
|---|---|
| Hygiene dry-run | `python scripts/git_hygiene/check_no_sensitive_paths_staged.py --dry-run` |
| Git status | `git status --short` |
| Recent commits | `git log --oneline -10` |

## Phase result

PHASE 5 — Operator commands: **COMPLETED**

## Recorded

`2026-06-30T17:00:00+00:00`
