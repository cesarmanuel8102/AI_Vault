# MAIN_ROUTER_MEGA_MIGRATION_REPORT_14B

Status: MOSTLY_COMPLETED_WITH_DEFERRED

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B

## State

- Branch: `codex/own-capital-sustainable-return`
- HEAD initial: `27f4e38`
- HEAD final local: pending final docs commit at report creation time
- Origin at start: `27f4e38`
- Backup branch: `backup/main-router-pre-14b-27f4e38`
- Push: not performed

## Commits Created

- `049dda5` - `refactor(routes): split strategy readonly endpoints`
- `8a052a9` - `refactor(routes): split governance control endpoints`
- `cc6e465` - `refactor(routes): split trace streaming dev endpoints`
- `759aa88` - `refactor(routes): split memory semantic endpoints`
- `dd9de03` - `refactor(routes): split provider backed readonly endpoints`
- `2e95d95` - `refactor(routes): split remaining control diagnostics endpoints`

## Endpoint Counts

Before 14B:

- `MAIN_PY_LINES`: 3812
- `APP_ENDPOINTS`: 114
- `APP_GET`: 58
- `APP_POST`: 53
- `APP_DELETE`: 3
- `APP_PUT`: 0
- `APP_PATCH`: 0

After route commits:

- `MAIN_PY_LINES`: 3258
- `APP_ENDPOINTS`: 59
- `APP_GET`: 16
- `APP_POST`: 40
- `APP_DELETE`: 3
- `APP_PUT`: 0
- `APP_PATCH`: 0

Net reduction:

- Lines removed from `main.py`: 554
- Decorators removed from `main.py`: 55
- GET decorators removed from `main.py`: 42
- POST decorators removed from `main.py`: 13

## Routers Created

- `tmp_agent/brain_v9/routes/strategy_readonly_routes.py`
- `tmp_agent/brain_v9/routes/governance_control_routes.py`
- `tmp_agent/brain_v9/routes/trace_streaming_routes.py`
- `tmp_agent/brain_v9/routes/memory_semantic_routes.py`
- `tmp_agent/brain_v9/routes/provider_readonly_routes.py`
- `tmp_agent/brain_v9/routes/main_remaining_control_routes.py`

## Endpoints Moved

### Strategy Readonly

- `GET /brain/strategy-engine/summary`
- `GET /brain/strategy-engine/candidates`
- `GET /brain/strategy-engine/scorecards`
- `GET /brain/strategy-engine/ranking`
- `GET /brain/strategy-engine/ranking-v2`
- `GET /brain/strategy-engine/features`
- `GET /brain/strategy-engine/history`
- `GET /brain/strategy-engine/signals`
- `GET /brain/strategy-engine/archive`
- `GET /brain/strategy-engine/expectancy`
- `GET /brain/strategy-engine/expectancy/by-strategy`
- `GET /brain/strategy-engine/expectancy/by-venue`
- `GET /brain/strategy-engine/expectancy/by-symbol`
- `GET /brain/strategy-engine/expectancy/by-context`
- `GET /brain/strategy-engine/edge-validation`
- `GET /brain/strategy-engine/context-edge-validation`
- `GET /brain/strategy-engine/active-catalog`
- `GET /brain/strategy-engine/pipeline-integrity`
- `GET /brain/strategy-engine/post-trade-analysis`
- `GET /brain/strategy-engine/post-trade-hypotheses`
- `GET /brain/strategy-engine/learning-loop`
- `GET /brain/strategy-engine/hypotheses`
- `GET /brain/strategy-engine/execution-audit`
- `GET /brain/strategy-engine/adaptation-state`
- `GET /brain/strategy-engine/session-performance`

### Governance Control

- `GET /brain/meta-governance/status`
- `GET /brain/change-control/scorecard`
- `GET /brain/control-layer/status`
- `GET /brain/purpose/status`
- `GET /brain/consciousness/status`
- `POST /brain/purpose/refresh`
- `POST /brain/control-layer/freeze`
- `POST /brain/control-layer/unfreeze`
- `POST /brain/self-improvement/change`
- `POST /brain/self-improvement/change/{change_id}/validate`
- `POST /brain/self-improvement/change/{change_id}/promote`
- `POST /brain/self-improvement/change/{change_id}/rollback`
- `POST /brain/validate`

### Trace Streaming

- `POST /brain/agent-trace/event`
- `GET /brain/agent-trace/latest`
- `GET /brain/agent-trace/stream`

### Memory Semantic

- `GET /brain/semantic-memory/search`
- `POST /brain/semantic-memory/ingest`
- `POST /brain/semantic-memory/ingest-session`

### Provider Readonly

- `GET /brain-dashboard/agent-v2/status`
- `GET /brain/operating-context`
- `GET /brain/maintenance/status`

### Remaining Control Diagnostics

- `POST /brain/ops/log-cleanup`
- `GET /brain/ops/log-status`
- `GET /brain/ops/adn-quality`
- `GET /brain/ops/upgrade-check`
- `GET /brain/ops/pre-upgrade`
- `GET /brain/ops/post-upgrade`
- `GET /brain/ops/ethics`
- `POST /self-diagnostic/run`

## Endpoints Remaining In main.py

Remaining endpoints are intentionally deferred because they are high-risk or directly coupled to session runtime, PAD/GOD, active sessions, mutation lifecycles, or strategy execution:

- `POST /brain/maintenance/action` - maintenance action wrapper can start/stop local services; keep in main pending dedicated maintenance-control extraction.
- `GET /chat/introspectivo/debug` - depends on introspective orchestrator state.
- `POST /chat/introspectivo` - chat response model and orchestrator path.
- `POST /chat` - primary BrainSession route, active session lifecycle, trace integration, permission flow.
- `DELETE /sessions/{session_id}` - active session mutation.
- `DELETE /sessions/{session_id}/memory` - session memory mutation.
- `POST /brain/learned/patterns/{pattern_id}/disable` - learned pattern mutation.
- `DELETE /brain/learned/patterns/{pattern_id}` - learned pattern mutation.
- `POST /brain/learned/test_simulate` - strict operator controlled simulation.
- `GET /brain/mutations` - mutation subsystem still paired with rollback/test apply.
- `GET /brain/mutations/{mutation_id}` - mutation subsystem.
- `POST /brain/mutations/{mutation_id}/rollback` - mutation rollback.
- `POST /brain/mutations/test_apply` - mutation test apply.
- `GET /brain/chat_excellence/status` - proposal subsystem tied to apply/dry-run/rollback lifecycle.
- `POST /brain/scheduler/alerts/ack` - scheduler mutation.
- `POST /brain/proactive/run/{task_id}` - proactive task execution.
- `POST /brain/llm/circuit_breaker/reset` - runtime control mutation.
- `GET /brain/chat_excellence/proposals` - proposal lifecycle read paired with mutation actions.
- `GET /brain/learning/proposals` - learning proposal lifecycle read paired with transition/evaluate.
- `GET /brain/chat_excellence/proposals/{proposal_id}` - proposal lifecycle.
- `POST /brain/chat_excellence/proposals/{proposal_id}/reject` - proposal mutation.
- `POST /brain/chat_excellence/proposals/{proposal_id}/dry_run` - proposal dry-run execution.
- `POST /brain/chat_excellence/proposals/{proposal_id}/apply` - proposal apply mutation.
- `POST /brain/chat_excellence/proposals/{proposal_id}/rollback` - proposal rollback.
- `GET /brain/chat_excellence/proposals/{proposal_id}/health_gate_log` - proposal lifecycle read.
- `POST /brain/chat_excellence/proposals/apply_batch` - batch mutation.
- `POST /brain/chat_excellence/proposals/evaluate` - evaluation execution.
- `GET /brain/chat_excellence/proposals/{proposal_id}/evaluation_status` - proposal lifecycle read.
- `POST /brain/utility/refresh` - writes utility snapshots.
- `POST /brain/utility/v2/refresh` - writes utility snapshots.
- `GET /brain/autonomy/next-actions` - autonomy action queue surface paired with execution endpoint.
- `GET /brain/autonomy/sample-accumulator` - autonomy state surface.
- `POST /brain/autonomy/execute-top-action` - autonomy execution.
- `GET /brain/autonomy/ibkr-ingester` - IBKR adjacent status.
- `POST /brain/autonomy/ibkr-snapshot` - IBKR adjacent snapshot action.
- `GET /brain/operations` - mixed operational surface.
- `GET /brain/pipeline-health` - mixed operational surface.
- `POST /brain/post-bl-roadmap/refresh` - refresh mutation.
- `POST /brain/meta-improvement/refresh` - refresh mutation.
- `POST /brain/chat-product/refresh` - refresh mutation.
- `POST /brain/autonomous-governance-eval/refresh` - refresh mutation.
- `POST /brain/utility-governance/refresh` - refresh mutation.
- `GET /brain/session-memory` - session memory state surface.
- `POST /brain/roadmap/governance/refresh` - refresh mutation.
- `POST /brain/learning/refresh` - learning refresh.
- `POST /brain/learning/proposals/{proposal_id}/transition` - proposal transition mutation.
- `POST /brain/learning/proposals/{proposal_id}/sandbox-run` - sandbox execution.
- `POST /brain/learning/proposals/{proposal_id}/evaluate` - evaluation execution.
- `POST /brain/strategy-engine/simulation-gate/{strategy_id}` - backtest/probation execution gate.
- `POST /brain/strategy-engine/refresh` - strategy engine refresh mutation.
- `POST /brain/strategy-engine/execute-top-candidate` - strategy execution.
- `POST /brain/strategy-engine/execute-candidate/{strategy_id}` - strategy execution.
- `POST /brain/strategy-engine/execute-batch/{strategy_id}` - strategy execution.
- `POST /brain/strategy-engine/execute-comparison-cycle` - strategy execution.
- `POST /brain/metacognition/audit` - claim audit action.
- `POST /agent` - deprecated/internal AgentLoop route.
- `POST /dev` - unsafe dev surface guarded by strict operator access.
- `GET /godmode/status` - PAD/GOD session state.
- `POST /godmode` - PAD/GOD execution route.

## Tests Run

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile` for all new routers.
- `python tests/contract/test_main_routes_readonly_extra_split_13f.py`
- `python tests/contract/test_main_routes_readonly_diagnostics_split_13e.py`
- `python tests/contract/test_main_routes_validators_observability_split_13d.py`
- `python tests/contract/test_main_routes_health_status_deferred_split_13c.py`
- `python tests/contract/test_main_routes_startup_state_adapter_13b.py`
- `python tests/contract/test_main_routes_health_status_split_13a.py`
- `python tests/contract/test_main_routes_curated_knowledge_split_14a.py`
- `python tests/contract/test_main_routes_gate_tool_split_14b.py`
- `python tests/contract/test_main_routes_dashboard_shell_split_14c.py`
- `python tests/contract/test_main_routes_dev_debug_split_14e.py`
- `python tests/contract/test_main_routes_memory_semantic_split_14b.py`
- `python tests/contract/test_main_routes_governance_control_split_14c.py`
- `python tests/contract/test_main_routes_trace_streaming_split_14d.py`
- `python tests/contract/test_main_routes_provider_readonly_split_14e.py`
- `python tests/contract/test_main_routes_strategy_readonly_split_14f.py`
- `python tests/contract/test_main_routes_remaining_control_split_14h.py`
- `python tests/contract/test_main_router_topology_contract_12b.py`
- `python tests/contract/test_main_router_dev_surface_guard_12c.py`
- `python tests/contract/test_main_router_surface_matrix_12d.py`
- `python tests/contract/test_main_router_auth_permission_contract_12e.py`
- `python tests/contract/test_main_router_side_effect_boundary_12f.py`
- `python tests/unit/test_ollama_config_session_message_11d_c.py`
- `python tests/unit/test_ollama_config_centralization_11d_b.py`
- `python tests/integration/test_autonomy_e2e_memory_tool_fallback_11c.py`
- `python tests/unit/test_scvl_final_answer_gate_01.py`
- `python tests/unit/test_scvl_semantic_promotion_gate_01.py`

## Failures / Reverts

- No route block was reverted.
- One expected contract drift occurred after moving `/self-diagnostic/run`; `test_main_routes_dev_debug_split_14e.py` was updated to classify it as moved to `main_remaining_control_routes.py`.

## Files Touched

- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/routes/strategy_readonly_routes.py`
- `tmp_agent/brain_v9/routes/governance_control_routes.py`
- `tmp_agent/brain_v9/routes/trace_streaming_routes.py`
- `tmp_agent/brain_v9/routes/memory_semantic_routes.py`
- `tmp_agent/brain_v9/routes/provider_readonly_routes.py`
- `tmp_agent/brain_v9/routes/main_remaining_control_routes.py`
- `tests/contract/test_main_routes_strategy_readonly_split_14f.py`
- `tests/contract/test_main_routes_governance_control_split_14c.py`
- `tests/contract/test_main_routes_trace_streaming_split_14d.py`
- `tests/contract/test_main_routes_memory_semantic_split_14b.py`
- `tests/contract/test_main_routes_provider_readonly_split_14e.py`
- `tests/contract/test_main_routes_remaining_control_split_14h.py`
- `tests/contract/test_main_routes_dev_debug_split_14e.py`
- `tests/contract/test_main_router_dev_surface_guard_12c.py`
- `tests/contract/test_main_router_surface_matrix_12d.py`
- `.github/workflows/brain-agent-v2-hygiene.yml`
- `.github/workflows/nontrading-smoke-regression.yml`
- `docs/audit/MAIN_ROUTER_MEGA_MIGRATION_REPORT_14B.md`

## No-Touch Confirmation

Confirmed not modified:

- `memory/semantic/*`
- FAISS files
- `tmp_agent/state/*`
- `autonomous_journal.jsonl`
- session internals
- SCVL gate internals
- `semantic_memory_faiss.py`
- trading engine internals
- risk limits
- kill switches
- `dry_run_only`
- broker/IBKR/QC code

## Deferred Next Front

Recommended next front:

`FRONT-BRAIN-MAIN-ROUTER-SESSION-LIFECYCLE-15A`

Scope should isolate chat/session/agent routes behind explicit session provider boundaries, with no `session.py` internal rewrites unless separately authorized.
