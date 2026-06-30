# Observability Inventory — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Scope

Read-only inspection of the Agent V2 runtime selector, both backends, the API adapter, the response normalizer, governance, and dashboard wiring. No files were modified.

## Backend selector

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py` |
| Default | `NativeAgentRuntimeV2` |
| Opt-in env var | `AGENT_V2_BACKEND` |
| Native values | `""`, `"native"`, `"native_runtime"` |
| LangGraph values | `"langgraph"`, `"langgraph_parity"`, `"langgraph_parity_runtime"` |
| Fallback | Unknown / missing / init failure / missing production methods → Native with `backend_fallback_used=true` and a reason string |

Key functions:

- `resolve_agent_v2_backend_choice`
- `is_langgraph_backend_requested`
- `get_agent_runtime_backend_name`
- `get_agent_runtime_v2`
- `is_agent_v2_production_runtime_compatible`

## Native runtime

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py` |
| Class | `NativeAgentRuntimeV2` |
| Backend | `native_runtime` |
| Persistence | `RUN_ROOT/<run_id>/run.json` |
| Trace | `TraceStore` per run |
| Checkpoints | `CheckpointStore` |
| Mode escalation | `run["mode_escalation_required"]`, `run["required_permission"]` |

## LangGraph parity runtime

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` |
| Class | `LangGraphParityRuntimeV2` |
| Backend | `langgraph_parity` |
| Graph available at runtime | yes |
| Default timeout | 30.0 s |
| Timeout configurable | per instance via `execute_timeout_seconds` |
| Persistence | caller-provided `run_root/<run_id>/run.json` |
| Trace | `TraceStore` per run |
| Checkpoints | `CheckpointStore` at step_index 0 and 99 |
| Capability metadata | derived in `_capability_metadata_node` |

Graph nodes (observable via `node_path`):

1. start
2. intent
3. context_assembly
4. memory_retrieval
5. evidence_routing
6. planner
7. governance_gate
8. tool_execution
9. result_normalization
10. finalizer
11. evaluator
12. repair_or_replan
13. capability_metadata
14. end

Observability controls:

- Internal timeout/circuit-breaker wraps `_graph.invoke` in `ThreadPoolExecutor(max_workers=1)`.
- Malformed run state rejected with `status=failed`, `error=malformed_run_state`.
- Auto write-intent escalates `mode_effective` to `approval_required` while preserving `mode_requested=auto`.

## API adapter

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` |
| Routes | `/v2/agent/*`, `/v2/chat/agent` |
| Auth | `require_strict_operator_access` |
| Backend exposure | `backend`, `backend_selected`, `backend_fallback_used`, `backend_fallback_reason` included in `/v2/chat/agent` response |
| Normalization | `response_normalizer.normalize_agent_v2_chat_response` |

## Response normalizer

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py` |
| Purpose | guarantee stable `/v2/chat/agent` schema regardless of backend |
| Key functions | `normalize_provider_metadata`, `normalize_capability_metadata`, `normalize_agent_v2_chat_response` |

## Governance

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py` |
| Key functions | `validate_mode`, `mode_requires_escalation`, `escalate_auto_mode_effective`, `write_allowed`, `selfdev_governance_blocked`, `contains_forbidden_request_fields` |
| Write tools | `file_patch_dry_run`, `file_patch_apply_approval_required`, `git_commit_approval_required`, `report_writer` |
| Read-only tools | `repo_status_read`, `repo_history_read`, `repo_diff_read`, `grep_search`, `file_read`, `route_probe`, `semantic_retrieve`, `smoke_test_readonly` |

## Dashboard wiring

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/dashboard/dashboard_routes.py` |
| Agent V2 status route | `/brain-dashboard/agent-v2/status` |
| Chat proxy route | `/brain-dashboard/chat` → `http://127.0.0.1:8091/v2/chat/agent` |
| Trace proxy route | `/brain-dashboard/agent-v2/runs/{run_id}/trace` |
| Token handling | `X-Brain-Token` forwarded when `BRAIN_ADMIN_TOKEN` configured; token never returned |

## main.py wiring

| Item | Value |
|---|---|
| Module | `tmp_agent/brain_v9/main.py` |
| Agent V2 status alias | `/brain-dashboard/agent-v2/status` |
| Router inclusion | `agent_v2_router` and `agent_v2_chat_router` |
| Backend selection | happens inside `get_agent_runtime_v2()` at runtime |

## Runtime probe results

| Probe | Result |
|---|---|
| LangGraph package available | yes |
| Default backend is native | yes |
| `AGENT_V2_BACKEND=langgraph` selects LangGraph | yes |
| Invalid backend falls back to Native | yes |
| LangGraph end-to-end run status | completed |
| LangGraph node_path observed | all 14 nodes executed |

## Phase result

PHASE 2 — Observability inventory: **COMPLETED**

## Recorded

`2026-06-30T16:45:00+00:00`
