# MAIN ROUTER RESIDUAL SURFACE AUDIT 16A

**Status:** RESIDUAL_SURFACE_AUDIT_COMPLETED

**Front:** FRONT-BRAIN-MAIN-ROUTER-RESIDUAL-SURFACE-AUDIT-16A

**Scope:** Post-chat route move inventory of `tmp_agent/brain_v9/main.py` after FRONT-BRAIN-MAIN-ROUTER-CHAT-FINAL-ROUTE-MOVE-15F.

This document does NOT move routes. It classifies every remaining `@app.*` endpoint in `main.py` and proposes the next low-risk migration front.

---

## Base

- Repository: `C:\AI_VAULT_CANONICAL`
- Branch: `codex/own-capital-sustainable-return`
- HEAD initial: `5cb9684`
- `main.py` lines: 2441
- Residual `@app.*` endpoints in `main.py`: 50
- Chat route moved: `POST /chat` lives in `tmp_agent/brain_v9/routes/chat_entrypoint_routes.py`

---

## Category Definitions

| Category | Meaning |
|----------|---------|
| ROUTER_SHELL_READY | Thin wrapper; can move mechanically with a clean provider. |
| PROVIDER_BOUNDARY_READY | Needs a small provider/service before moving, but no deep logic refactor. |
| NEEDS_SERVICE_BOUNDARY | Contains substantial logic/helpers that should be extracted first. |
| CONTROL_MUTATION | POST/PUT/DELETE/PATCH that mutates runtime state or files. |
| GOVERNANCE_SECURITY | Auth, RBAC, operator gates, GOD/PAD, permission boundaries. |
| MEMORY_SEMANTIC_FAISS | Adjacent to memory, session memory, semantic/FAISS stores. |
| TRADING_QC_IBKR | Trading, strategy execution, QC/IBKR, order/risk adjacent. |
| TRACE_STREAMING | Streaming, trace, event-source. Needs special no-server contract. |
| DEV_DEBUG_RISKY | Dev/debug endpoints with side effects or internal state access. |
| KEEP_IN_MAIN_APP_ASSEMBLY | Must stay in `main.py` as app shell/startup/assembly wiring. |

---

## Full Endpoint Matrix

| # | Method | Path | Line | Function | Category | Risk | Mutates State | Auth/Guard | Runtime Data | Trading/QC/IBKR Adjacent | Session/Chat Adjacent | Memory/FAISS Adjacent | Safe to Move | Proposed Target Router | Proposed Front | Reason |
|---|--------|------|------|----------|----------|------|---------------|------------|--------------|--------------------------|------------------------|------------------------|--------------|------------------------|----------------|--------|
| 1 | POST | `/brain/maintenance/action` | 1157 | `brain_maintenance_action` | NEEDS_SERVICE_BOUNDARY | medium | yes | OperatorAccess | yes (maintenance helpers) | no | no | no | defer | `maintenance_routes.py` | 16C | Uses `_brain_maintenance_action_result` and `_build_brain_maintenance_status` helpers still in `main.py`. |
| 2 | POST | `/brain/learned/patterns/{pattern_id}/disable` | 1278 | `brain_learned_pattern_disable` | PROVIDER_BOUNDARY_READY | low | yes | StrictOperatorAccess | no | no | no | no | yes | `agent_learning_routes.py` | 16B | Thin wrapper around `FailureLearner.get().disable()`. |
| 3 | DELETE | `/brain/learned/patterns/{pattern_id}` | 1293 | `brain_learned_pattern_delete` | PROVIDER_BOUNDARY_READY | low-medium | yes | StrictOperatorAccess | no | no | no | no | yes | `agent_learning_routes.py` | 16B | Thin wrapper around `FailureLearner.get().delete()`. |
| 4 | POST | `/brain/learned/test_simulate` | 1308 | `brain_learned_test_simulate` | NEEDS_SERVICE_BOUNDARY | medium | yes | StrictOperatorAccess | yes (creates test session, persists pattern) | no | yes (test session via `get_or_create_session`) | no | defer | `agent_learning_routes.py` | 16D | Full meta-loop with session creation, LLM call, sandbox validation and persistence. |
| 5 | GET | `/brain/mutations` | 1403 | `brain_mutations` | ROUTER_SHELL_READY | low | no | none | no | no | no | no | yes | `code_mutation_routes.py` | 16B | Read-only list from `CodeMutator.get()`. |
| 6 | GET | `/brain/mutations/{mutation_id}` | 1415 | `brain_mutation_detail` | ROUTER_SHELL_READY | low | no | none | no | no | no | no | yes | `code_mutation_routes.py` | 16B | Read-only detail from `CodeMutator.get()`. |
| 7 | POST | `/brain/mutations/{mutation_id}/rollback` | 1431 | `brain_mutation_rollback` | CONTROL_MUTATION | high | yes | StrictOperatorAccess | no | no | no | no | defer | `code_mutation_routes.py` | 16D | Restores files from backups; mutates code on disk. |
| 8 | POST | `/brain/mutations/test_apply` | 1447 | `brain_mutations_test_apply` | CONTROL_MUTATION / DEV_DEBUG_RISKY | high | yes | StrictOperatorAccess | no | no | no | no | defer | `code_mutation_routes.py` | 16D | Applies code mutation directly and optionally starts health monitoring. |
| 9 | GET | `/brain/chat_excellence/status` | 1500 | `brain_chat_excellence_status` | ROUTER_SHELL_READY | low | no | none | no | no | yes (chat excellence) | no (reads JSON state) | yes | `chat_excellence_routes.py` | 16B | Reads `chat_excellence_history.json`; no mutation. |
| 10 | POST | `/brain/scheduler/alerts/ack` | 1544 | `brain_scheduler_alerts_ack` | PROVIDER_BOUNDARY_READY | low-medium | yes | none | yes (scheduler alerts) | no | no | no | yes | `autonomy_scheduler_routes.py` | 16B | Thin wrapper around `proactive_scheduler.acknowledge_alerts()`. |
| 11 | POST | `/brain/proactive/run/{task_id}` | 1573 | `brain_proactive_run_task` | PROVIDER_BOUNDARY_READY | low-medium | yes | none | yes (scheduler queue) | no | no | no | yes | `autonomy_scheduler_routes.py` | 16B | Thin wrapper around `proactive_scheduler.run_now()`. |
| 12 | POST | `/brain/llm/circuit_breaker/reset` | 1599 | `brain_llm_cb_reset` | PROVIDER_BOUNDARY_READY | low-medium | yes | StrictOperatorAccess | yes (LLM manager circuit state) | no | no | no | yes | `llm_management_routes.py` | 16B | Resets internal circuit breaker map. |
| 13 | GET | `/brain/chat_excellence/proposals` | 1618 | `brain_ce_proposals` | ROUTER_SHELL_READY | low | no | none | no | no | yes (chat excellence) | no | yes | `chat_excellence_routes.py` | 16B | Lists proposals. |
| 14 | GET | `/brain/learning/proposals` | 1629 | `brain_learning_proposals` | ROUTER_SHELL_READY | low | no | none | no | no | yes (chat excellence alias) | no | yes | `chat_excellence_routes.py` | 16B | Alias to `brain_ce_proposals`. |
| 15 | GET | `/brain/chat_excellence/proposals/{proposal_id}` | 1636 | `brain_ce_proposal_get` | ROUTER_SHELL_READY | low | no | none | no | no | yes | no | yes | `chat_excellence_routes.py` | 16B | Reads a single proposal. |
| 16 | POST | `/brain/chat_excellence/proposals/{proposal_id}/reject` | 1650 | `brain_ce_proposal_reject` | CONTROL_MUTATION | medium | yes | StrictOperatorAccess | no | no | yes | no | defer | `chat_excellence_routes.py` | 16C | Mutates proposal status. |
| 17 | POST | `/brain/chat_excellence/proposals/{proposal_id}/dry_run` | 1669 | `brain_ce_proposal_dry_run` | ROUTER_SHELL_READY | low | no | none | no | no | yes | no | yes | `chat_excellence_routes.py` | 16B | Generates diff, no write. |
| 18 | POST | `/brain/chat_excellence/proposals/{proposal_id}/apply` | 1685 | `brain_ce_proposal_apply` | CONTROL_MUTATION | high | yes | StrictOperatorAccess | no | no | yes | no | defer | `chat_excellence_routes.py` | 16D | Patches files, may restart brain. |
| 19 | POST | `/brain/chat_excellence/proposals/{proposal_id}/rollback` | 1738 | `brain_ce_proposal_rollback` | CONTROL_MUTATION | high | yes | none | no | no | yes | no | defer | `chat_excellence_routes.py` | 16D | Restores files from backups. |
| 20 | GET | `/brain/chat_excellence/proposals/{proposal_id}/health_gate_log` | 1755 | `brain_ce_proposal_health_gate_log` | ROUTER_SHELL_READY | low | no | none | no | no | yes | no | yes | `chat_excellence_routes.py` | 16B | Reads health gate log. |
| 21 | POST | `/brain/chat_excellence/proposals/apply_batch` | 1767 | `brain_ce_proposals_apply_batch` | CONTROL_MUTATION | high | yes | none | no | no | yes | no | defer | `chat_excellence_routes.py` | 16D | Bulk apply of patches. |
| 22 | POST | `/brain/chat_excellence/proposals/evaluate` | 1820 | `brain_ce_proposals_evaluate` | CONTROL_MUTATION | medium-high | yes (optional auto-rollback) | none | no | no | yes | no | defer | `chat_excellence_routes.py` | 16D | May trigger rollbacks. |
| 23 | GET | `/brain/chat_excellence/proposals/{proposal_id}/evaluation_status` | 1852 | `brain_ce_proposal_eval_status` | ROUTER_SHELL_READY | low | no | none | no | no | yes | no | yes | `chat_excellence_routes.py` | 16B | Reads evaluation metadata. |
| 24 | POST | `/brain/utility/refresh` | 1879 | `brain_utility_refresh` | PROVIDER_BOUNDARY_READY | low-medium | yes | OperatorAccess | no | no | no | no | yes | `utility_governance_routes.py` | 16B | Thin orchestration of existing helpers. |
| 25 | POST | `/brain/utility/v2/refresh` | 1899 | `brain_utility_v2_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | no | no | yes | `utility_governance_routes.py` | 16B | Delegates to `brain_utility_refresh`. |
| 26 | GET | `/brain/autonomy/next-actions` | 1903 | `brain_autonomy_next_actions` | ROUTER_SHELL_READY | low | no | none | no | no | no | no | yes | `autonomy_status_routes.py` | 16B | Returns `write_utility_snapshots()["next_actions"]`. |
| 27 | GET | `/brain/autonomy/sample-accumulator` | 1908 | `brain_sample_accumulator_status` | NEEDS_SERVICE_BOUNDARY | medium | no | none | no | no | no | no | defer | `autonomy_status_routes.py` | 16C | Contains multi-platform accumulator aggregation logic that should become a service. |
| 28 | POST | `/brain/autonomy/execute-top-action` | 1980 | `brain_autonomy_execute_top_action` | CONTROL_MUTATION | high | yes | OperatorAccess | no | no | no | no | defer | `autonomy_action_routes.py` | 16D | Executes top action from meta-governance. |
| 29 | GET | `/brain/autonomy/ibkr-ingester` | 1989 | `brain_ibkr_ingester_status` | TRADING_QC_IBKR | medium | no | none | no | yes (IBKR ingester) | no | no | no | `trading_routes.py` (or remain in autonomy) | 16G | IBKR data ingester status. |
| 30 | POST | `/brain/autonomy/ibkr-snapshot` | 2009 | `brain_ibkr_trigger_snapshot` | TRADING_QC_IBKR | medium | yes | OperatorAccess | no | yes (IBKR snapshot) | no | no | no | `trading_routes.py` | 16G | Triggers IBKR market data snapshot. |
| 31 | GET | `/brain/operations` | 2028 | `brain_operations` | NEEDS_SERVICE_BOUNDARY | medium | no | none | no | yes (calls trading health/policy, strategy engine) | no | no | defer | `operations_routes.py` | 16C | Aggregates utility, governance, research, strategy, trading. |
| 32 | GET | `/brain/pipeline-health` | 2061 | `brain_pipeline_health` | DEV_DEBUG_RISKY | low-medium | no | none | no | no (lists test files) | no | no | yes | `dev_debug_routes.py` or `diagnostics_routes.py` | 16B | Counts local test files; dev-observability surface. |
| 33 | POST | `/brain/post-bl-roadmap/refresh` | 2110 | `brain_post_bl_roadmap_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | no | no | yes | `roadmap_governance_routes.py` | 16B | Delegates to `refresh_post_bl_roadmap_status()`. |
| 34 | POST | `/brain/meta-improvement/refresh` | 2115 | `brain_meta_improvement_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | no | no | yes | `meta_improvement_routes.py` | 16B | Delegates to `refresh_meta_improvement_status()`. |
| 35 | POST | `/brain/chat-product/refresh` | 2120 | `brain_chat_product_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | yes | no | yes | `chat_product_governance_routes.py` | 16B | Delegates to `refresh_chat_product_status()`. |
| 36 | POST | `/brain/autonomous-governance-eval/refresh` | 2125 | `brain_autonomous_governance_eval_refresh` | ROUTER_SHELL_READY | low-medium | yes | OperatorAccess | no | no | no | no | yes | `autonomy_governance_routes.py` | 16B | Delegates to `build_autonomous_governance_eval()`. |
| 37 | POST | `/brain/utility-governance/refresh` | 2130 | `brain_utility_governance_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | no | no | yes | `utility_governance_routes.py` | 16B | Delegates to `refresh_utility_governance_status()`. |
| 38 | GET | `/brain/session-memory` | 2135 | `brain_session_memory` | MEMORY_SEMANTIC_FAISS | medium | no* | none | yes (session memory) | no | yes (session memory) | yes (session_memory_state) | no | `memory_semantic_routes.py` | 16F | Reads session memory snapshot; adjacent to session.py runtime. |
| 39 | POST | `/brain/roadmap/governance/refresh` | 2144 | `brain_roadmap_governance_refresh` | ROUTER_SHELL_READY | low | yes | OperatorAccess | no | no | no | no | yes | `roadmap_governance_routes.py` | 16B | Delegates to `promote_roadmap_if_ready()`. |
| 40 | POST | `/brain/learning/refresh` | 2148 | `brain_learning_refresh` | PROVIDER_BOUNDARY_READY | low-medium | yes | OperatorAccess | no | no | no | no | yes | `learning_routes.py` | 16B | Thin wrapper around `run_learning_refresh()`. |
| 41 | POST | `/brain/learning/proposals/{proposal_id}/transition` | 2161 | `brain_learning_proposal_transition` | CONTROL_MUTATION | medium | yes | OperatorAccess | no | no | no | no | defer | `learning_routes.py` | 16C | Mutates learning proposal state. |
| 42 | POST | `/brain/learning/proposals/{proposal_id}/sandbox-run` | 2175 | `brain_learning_proposal_sandbox_run` | CONTROL_MUTATION | medium-high | yes | OperatorAccess | no | no | no | no | defer | `learning_routes.py` | 16C | Executes sandbox run. |
| 43 | POST | `/brain/learning/proposals/{proposal_id}/evaluate` | 2188 | `brain_learning_proposal_evaluate` | CONTROL_MUTATION | medium | yes | OperatorAccess | no | no | no | no | defer | `learning_routes.py` | 16C | Evaluates proposal. |
| 44 | POST | `/brain/strategy-engine/simulation-gate/{strategy_id}` | 2201 | `brain_strategy_engine_simulation_gate` | TRADING_QC_IBKR | medium | no* | none | no | yes (backtest gate, strategy specs) | no | no | no | `strategy_readonly_routes.py` or `trading_routes.py` | 16G | Runs backtest simulation gate (read-only analysis). |
| 45 | POST | `/brain/strategy-engine/refresh` | 2212 | `brain_strategy_engine_refresh` | TRADING_QC_IBKR | medium | yes | OperatorAccess | no | yes (strategy engine refresh) | no | no | no | `trading_routes.py` | 16G | Refreshes strategy engine state. |
| 46 | POST | `/brain/strategy-engine/execute-top-candidate` | 2216 | `brain_strategy_engine_execute_top_candidate` | TRADING_QC_IBKR | high | yes | OperatorAccess | no | yes (executes candidate) | no | no | no | `trading_routes.py` | 16G | Executes top strategy candidate. |
| 47 | POST | `/brain/strategy-engine/execute-candidate/{strategy_id}` | 2221 | `brain_strategy_engine_execute_candidate` | TRADING_QC_IBKR | high | yes | OperatorAccess | no | yes (executes candidate) | no | no | no | `trading_routing_routes.py` | 16G | Executes specific strategy candidate. |
| 48 | POST | `/brain/strategy-engine/execute-batch/{strategy_id}` | 2226 | `brain_strategy_engine_execute_batch` | TRADING_QC_IBKR | high | yes | OperatorAccess | no | yes (executes batch) | no | no | no | `trading_routing_routes.py` | 16G | Executes candidate batch. |
| 49 | POST | `/brain/strategy-engine/execute-comparison-cycle` | 2231 | `brain_strategy_engine_execute_comparison_cycle` | TRADING_QC_IBKR | high | yes | OperatorAccess | no | yes (executes comparison cycle) | no | no | no | `trading_routing_routes.py` | 16G | Executes comparison cycle. |
| 50 | POST | `/brain/metacognition/audit` | 2243 | `brain_metacognition_audit` | ROUTER_SHELL_READY | low | no | none | no | no | no | no | yes | `dev_debug_routes.py` or `metacognition_routes.py` | 16B | Thin wrapper around `audit_response_claims()`. |

---

## Category Distribution

| Category | Count |
|----------|-------|
| ROUTER_SHELL_READY | 22 |
| PROVIDER_BOUNDARY_READY | 7 |
| NEEDS_SERVICE_BOUNDARY | 4 |
| CONTROL_MUTATION | 11 |
| GOVERNANCE_SECURITY | 0 (all mutation endpoints already use OperatorAccess/StrictOperatorAccess; no standalone RBAC surface remains in `main.py`) |
| MEMORY_SEMANTIC_FAISS | 1 |
| TRADING_QC_IBKR | 8 |
| TRACE_STREAMING | 0 (already migrated to `trace_streaming_routes.py`) |
| DEV_DEBUG_RISKY | 1 |
| KEEP_IN_MAIN_APP_ASSEMBLY | 0 (app shell/startup code remains but is not an endpoint) |

---

## Highest-Risk Residuals (do not move without service/contract)

1. `POST /brain/mutations/test_apply` — direct code mutation on disk.
2. `POST /brain/mutations/{mutation_id}/rollback` — file rollback.
3. `POST /brain/chat_excellence/proposals/{proposal_id}/apply` — patch files, optional restart.
4. `POST /brain/chat_excellence/proposals/{proposal_id}/rollback` — restores backups.
5. `POST /brain/chat_excellence/proposals/apply_batch` — bulk patch apply.
6. `POST /brain/chat_excellence/proposals/evaluate` — may auto-rollback.
7. `POST /brain/strategy-engine/execute-candidate/{strategy_id}` — executes strategy candidate.
8. `POST /brain/strategy-engine/execute-top-candidate` — executes top strategy candidate.
9. `POST /brain/strategy-engine/execute-batch/{strategy_id}` — executes candidate batch.
10. `POST /brain/strategy-engine/execute-comparison-cycle` — executes comparison cycle.

---

## Low-Risk Candidates for 16B

These 21 endpoints are thin wrappers that can move mechanically:

- `GET /brain/mutations`
- `GET /brain/mutations/{mutation_id}`
- `GET /brain/chat_excellence/status`
- `GET /brain/chat_excellence/proposals`
- `GET /brain/learning/proposals`
- `GET /brain/chat_excellence/proposals/{proposal_id}`
- `POST /brain/chat_excellence/proposals/{proposal_id}/dry_run`
- `GET /brain/chat_excellence/proposals/{proposal_id}/health_gate_log`
- `GET /brain/chat_excellence/proposals/{proposal_id}/evaluation_status`
- `POST /brain/utility/v2/refresh`
- `GET /brain/autonomy/next-actions`
- `POST /brain/post-bl-roadmap/refresh`
- `POST /brain/meta-improvement/refresh`
- `POST /brain/chat-product/refresh`
- `POST /brain/autonomous-governance-eval/refresh`
- `POST /brain/utility-governance/refresh`
- `POST /brain/roadmap/governance/refresh`
- `POST /brain/metacognition/audit`
- `POST /brain/learned/patterns/{pattern_id}/disable`
- `DELETE /brain/learned/patterns/{pattern_id}`
- `GET /brain/pipeline-health`

Additionally these 7 endpoints need a small provider first but are still low-medium risk:

- `POST /brain/scheduler/alerts/ack`
- `POST /brain/proactive/run/{task_id}`
- `POST /brain/llm/circuit_breaker/reset`
- `POST /brain/utility/refresh`
- `POST /brain/learning/refresh`
- `POST /brain/chat_excellence/proposals/{proposal_id}/reject`

---

## Deferred / Risky Candidates

- `POST /brain/maintenance/action` — needs `_brain_maintenance_action_result` helper extraction.
- `POST /brain/learned/test_simulate` — needs service that owns test session + LLM + sandbox.
- `POST /brain/chat_excellence/proposals/{proposal_id}/apply` — patch apply with optional restart.
- `POST /brain/chat_excellence/proposals/{proposal_id}/rollback` — file restore.
- `POST /brain/chat_excellence/proposals/apply_batch` — bulk patch apply / CONTROL_MUTATION / defer to 16D.
- `POST /brain/chat_excellence/proposals/evaluate` — may rollback.
- `POST /brain/autonomy/execute-top-action` — executes autonomy action.
- `GET /brain/autonomy/sample-accumulator` — multi-platform aggregator logic.
- `GET /brain/operations` — cross-domain aggregator (trading + governance + research).
- `POST /brain/learning/proposals/{proposal_id}/transition` — state mutation.
- `POST /brain/learning/proposals/{proposal_id}/sandbox-run` — sandbox execution.
- `POST /brain/learning/proposals/{proposal_id}/evaluate` — evaluation mutation.
- `GET /brain/session-memory` — session memory adjacent; move only in 16F with no-write contract.
- All `/brain/strategy-engine/*` endpoints — TRADING_QC_IBKR category; defer to 16G.

---

## Keep-in-Main Candidates

There are no residual `@app.*` endpoints that must stay in `main.py`. The remaining `main.py` shell responsibilities are:

- FastAPI app creation and `lifespan` wiring.
- Router inclusion (`app.include_router`).
- Runtime provider registration for chat/session/autonomy.
- Startup/shutdown background tasks.
- Shared module-level state that routers receive via providers (`active_sessions`, `_pad_authenticated_sessions`).

These are not endpoints and therefore are not listed in the matrix above.

---

## Next Recommended Front

**FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B**

Move the 22 `ROUTER_SHELL_READY` endpoints (and optionally the 7 `PROVIDER_BOUNDARY_READY` endpoints once providers are added) into focused routers, leaving all mutation/trading/memory surfaces in `main.py` for later fronts.

---

## No-Touch Confirmation

This audit and its accompanying contract do NOT:

- Move any endpoint in `tmp_agent/brain_v9/main.py`.
- Change behavior of any endpoint.
- Modify `tmp_agent/brain_v9/core/session.py`.
- Modify SCVL internals.
- Modify memory/semantic data or FAISS internals.
- Modify trading/risk/QC/IBKR internals.
- Modify runtime data under `tmp_agent/state`.
- Start a server or call external APIs.

---

## Roadmap Post-15F

| Front | Scope |
|-------|-------|
| 16B — LOW-RISK-SHELL-MOVE | Move `ROUTER_SHELL_READY` endpoints (22 routes). |
| 16C — PROVIDER-BOUNDARY-BATCH | Move `PROVIDER_BOUNDARY_READY` endpoints after small provider extraction (7 routes). |
| 16D — GOVERNANCE/CONTROL-MUTATION-HARDENING | Service/guard extraction before moving control mutations (11 routes). |
| 16E — TRACE/STREAMING SPLIT | Already completed; no residual trace/streaming endpoints remain in `main.py`. |
| 16F — MEMORY/SEMANTIC NO-WRITE BOUNDARY | Move `GET /brain/session-memory` under a no-write contract (1 route). |
| 16G — STRATEGY/TRADING-ADJACENT ISOLATION | Move read-only trading-adjacent endpoints; keep execution endpoints guarded in trading router (8 routes). |
| 16H — MAIN.PY FINAL APP ASSEMBLY AUDIT | Decide final keep-in-main shell and reduce `main.py` to assembly wiring. |
