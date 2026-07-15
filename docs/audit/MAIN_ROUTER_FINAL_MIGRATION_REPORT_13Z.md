# MAIN_ROUTER_FINAL_MIGRATION_REPORT_13Z

Front: FRONT-BRAIN-MAIN-ROUTER-FULL-MIGRATION-SWEEP-13F-TO-CLOSE

## Status

PARTIALLY_COMPLETED_WITH_DEFERRED

Reason: moved all low-risk read-only endpoints selected for this sweep. Remaining endpoints are dashboard/session/chat/control/mutation/memory/FAISS/trading/dev-debug/provider-ambiguous surfaces and should be handled by narrower fronts.

## State

- Initial HEAD: 3319b60
- Working branch: codex/own-capital-sustainable-return
- main.py line count before: 4375
- main.py line count after: 4267

## Routers Created

- tmp_agent/brain_v9/routes/read_only_diagnostics_extra.py

## Endpoints Moved

- GET /brain/utility
- GET /brain/utility/v2
- GET /brain/utility/status
- GET /brain/roadmap/governance
- GET /brain/roadmap/development-status
- GET /brain/post-bl-roadmap/status
- GET /brain/meta-improvement/status
- GET /brain/chat-product/status
- GET /brain/autonomous-governance-eval/status
- GET /brain/utility-governance/status
- GET /brain/research/summary
- GET /brain/research/knowledge
- GET /brain/research/indicators
- GET /brain/research/strategies
- GET /brain/research/hypotheses
- GET /brain/research/candidates
- GET /brain/learning/status
- GET /brain/self-improvement/ledger
- GET /brain/self-improvement/change/{change_id}/status

## Remaining main.py Endpoint Counts

- total remaining @app endpoints: 131
- DELETE: 3
- GET: 70
- POST: 58

## Remaining Endpoints

| line | method | path | category | reason |
|---:|---|---|---|---|
| 304 | GET | `/dashboard` | DASHBOARD_UI_SURFACE | dashboard/UI or Agent V2 dashboard runtime; deferred to dashboard-specific router work. |
| 314 | GET | `/dashboard-v2` | DASHBOARD_UI_SURFACE | dashboard/UI or Agent V2 dashboard runtime; deferred to dashboard-specific router work. |
| 1140 | GET | `/brain-dashboard/agent-v2/status` | DASHBOARD_UI_SURFACE | dashboard/UI or Agent V2 dashboard runtime; deferred to dashboard-specific router work. |
| 1162 | GET | `/brain/operating-context` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 1170 | GET | `/brain/maintenance/status` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 1175 | POST | `/brain/maintenance/action` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 1202 | GET | `/chat/introspectivo/debug` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 1228 | POST | `/chat/introspectivo` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 1453 | POST | `/chat` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 1935 | DELETE | `/sessions/{session_id}` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 1949 | POST | `/gate/approve/{pending_id}` | CONTROL_SURFACE | governance/approval privileged control surface; requires dedicated signed-gate router contract. |
| 1989 | POST | `/gate/reject/{pending_id}` | CONTROL_SURFACE | governance/approval privileged control surface; requires dedicated signed-gate router contract. |
| 2000 | POST | `/tool01/permission/approve` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 2043 | GET | `/tool01/permission/pending/{session_id}` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 2055 | GET | `/tool01/permission/grants/{session_id}` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 2074 | DELETE | `/sessions/{session_id}/memory` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 2084 | POST | `/brain/learned/patterns/{pattern_id}/disable` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2099 | DELETE | `/brain/learned/patterns/{pattern_id}` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2114 | POST | `/brain/learned/test_simulate` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2209 | GET | `/brain/mutations` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2221 | GET | `/brain/mutations/{mutation_id}` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2237 | POST | `/brain/mutations/{mutation_id}/rollback` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2253 | POST | `/brain/mutations/test_apply` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2306 | GET | `/brain/chat_excellence/status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2350 | POST | `/brain/scheduler/alerts/ack` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2379 | POST | `/brain/proactive/run/{task_id}` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2405 | POST | `/brain/llm/circuit_breaker/reset` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2424 | GET | `/brain/chat_excellence/proposals` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2435 | GET | `/brain/learning/proposals` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2442 | GET | `/brain/chat_excellence/proposals/{proposal_id}` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2456 | POST | `/brain/chat_excellence/proposals/{proposal_id}/reject` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2475 | POST | `/brain/chat_excellence/proposals/{proposal_id}/dry_run` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2491 | POST | `/brain/chat_excellence/proposals/{proposal_id}/apply` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2544 | POST | `/brain/chat_excellence/proposals/{proposal_id}/rollback` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2561 | GET | `/brain/chat_excellence/proposals/{proposal_id}/health_gate_log` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2573 | POST | `/brain/chat_excellence/proposals/apply_batch` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2626 | POST | `/brain/chat_excellence/proposals/evaluate` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2658 | GET | `/brain/chat_excellence/proposals/{proposal_id}/evaluation_status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2685 | POST | `/brain/utility/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2705 | POST | `/brain/utility/v2/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2709 | GET | `/brain/autonomy/next-actions` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2714 | GET | `/brain/autonomy/sample-accumulator` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2786 | POST | `/brain/autonomy/execute-top-action` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2795 | GET | `/brain/autonomy/ibkr-ingester` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 2815 | POST | `/brain/autonomy/ibkr-snapshot` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 2834 | GET | `/brain/operations` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 2867 | GET | `/brain/pipeline-health` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2916 | POST | `/brain/post-bl-roadmap/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2921 | POST | `/brain/meta-improvement/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2926 | POST | `/brain/chat-product/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2931 | POST | `/brain/autonomous-governance-eval/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2936 | POST | `/brain/utility-governance/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2941 | GET | `/brain/meta-governance/status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 2953 | GET | `/brain/session-memory` | MEMORY_FAISS_SURFACE | memory/semantic/FAISS surface explicitly blocked in this sweep. |
| 2962 | POST | `/brain/roadmap/governance/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2966 | POST | `/brain/learning/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2979 | POST | `/brain/learning/proposals/{proposal_id}/transition` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 2993 | POST | `/brain/learning/proposals/{proposal_id}/sandbox-run` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3006 | POST | `/brain/learning/proposals/{proposal_id}/evaluate` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3019 | GET | `/brain/strategy-engine/summary` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3023 | GET | `/brain/strategy-engine/candidates` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3028 | GET | `/brain/strategy-engine/scorecards` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3032 | GET | `/brain/strategy-engine/ranking` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3037 | GET | `/brain/strategy-engine/ranking-v2` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3042 | GET | `/brain/strategy-engine/features` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3047 | GET | `/brain/strategy-engine/history` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3052 | GET | `/brain/strategy-engine/signals` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3057 | GET | `/brain/strategy-engine/archive` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3062 | GET | `/brain/strategy-engine/expectancy` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3067 | GET | `/brain/strategy-engine/expectancy/by-strategy` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3072 | GET | `/brain/strategy-engine/expectancy/by-venue` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3077 | GET | `/brain/strategy-engine/expectancy/by-symbol` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3082 | GET | `/brain/strategy-engine/expectancy/by-context` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3087 | GET | `/brain/strategy-engine/edge-validation` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3092 | GET | `/brain/strategy-engine/context-edge-validation` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3097 | GET | `/brain/strategy-engine/active-catalog` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3102 | GET | `/brain/strategy-engine/pipeline-integrity` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3107 | GET | `/brain/strategy-engine/post-trade-analysis` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3111 | GET | `/brain/strategy-engine/post-trade-hypotheses` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3115 | GET | `/brain/strategy-engine/learning-loop` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3120 | GET | `/brain/strategy-engine/hypotheses` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3124 | GET | `/brain/strategy-engine/execution-audit` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3165 | POST | `/brain/strategy-engine/simulation-gate/{strategy_id}` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3176 | GET | `/brain/strategy-engine/adaptation-state` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3189 | GET | `/brain/strategy-engine/session-performance` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3208 | POST | `/brain/ops/log-cleanup` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3215 | GET | `/brain/ops/log-status` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3222 | GET | `/brain/ops/adn-quality` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3228 | GET | `/brain/ops/upgrade-check` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3234 | GET | `/brain/ops/pre-upgrade` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3240 | GET | `/brain/ops/post-upgrade` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3246 | GET | `/brain/ops/ethics` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3252 | POST | `/brain/strategy-engine/refresh` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3256 | POST | `/brain/strategy-engine/execute-top-candidate` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3261 | POST | `/brain/strategy-engine/execute-candidate/{strategy_id}` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3266 | POST | `/brain/strategy-engine/execute-batch/{strategy_id}` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3271 | POST | `/brain/strategy-engine/execute-comparison-cycle` | TRADING_BLOCKED | strategy/trading/QC/IBKR adjacent surface; explicitly blocked in this sweep. |
| 3275 | GET | `/brain/change-control/scorecard` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 3280 | GET | `/brain/control-layer/status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 3285 | GET | `/brain/purpose/status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 3290 | GET | `/brain/consciousness/status` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 3303 | POST | `/brain/purpose/refresh` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3308 | POST | `/brain/control-layer/freeze` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3313 | POST | `/brain/control-layer/unfreeze` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3317 | POST | `/brain/self-improvement/change` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 3321 | POST | `/brain/self-improvement/change/{change_id}/validate` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3325 | POST | `/brain/self-improvement/change/{change_id}/promote` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3329 | POST | `/brain/self-improvement/change/{change_id}/rollback` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3333 | POST | `/brain/validate` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3339 | GET | `/brain/auto-surgeon/status` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3344 | GET | `/brain/auto-surgeon/diagnostics` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3349 | GET | `/self-diagnostic` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3356 | POST | `/self-diagnostic/run` | MUTATION_OR_CONTROL_SURFACE | mutating/control verb or protected state transition; deferred for dedicated guarded router contract. |
| 3399 | GET | `/brain/semantic-memory/status` | MEMORY_FAISS_SURFACE | memory/semantic/FAISS surface explicitly blocked in this sweep. |
| 3515 | GET | `/brain/curated-knowledge/status` | CURATED_RUNTIME_SURFACE | existing curated lookup feature with operator/demo path policy; leave for dedicated curated router front. |
| 3533 | POST | `/brain/curated-knowledge/search` | CURATED_RUNTIME_SURFACE | existing curated lookup feature with operator/demo path policy; leave for dedicated curated router front. |
| 3591 | POST | `/brain/curated-knowledge/demo-search` | CURATED_RUNTIME_SURFACE | existing curated lookup feature with operator/demo path policy; leave for dedicated curated router front. |
| 3656 | GET | `/brain/semantic-memory/search` | MEMORY_FAISS_SURFACE | memory/semantic/FAISS surface explicitly blocked in this sweep. |
| 3678 | POST | `/brain/semantic-memory/ingest` | MEMORY_FAISS_SURFACE | memory/semantic/FAISS surface explicitly blocked in this sweep. |
| 3689 | POST | `/brain/semantic-memory/ingest-session` | MEMORY_FAISS_SURFACE | memory/semantic/FAISS surface explicitly blocked in this sweep. |
| 3695 | GET | `/brain/metacognition/status` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3701 | POST | `/brain/metacognition/audit` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3707 | GET | `/brain/introspection/status` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3713 | GET | `/brain/introspection/gpu` | DEV_DEBUG_SURFACE | debug/diagnostic/ops surface; may run checks or depend on dev runtime, deferred. |
| 3718 | POST | `/agent` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 3950 | POST | `/dev` | SESSION_CHAT_CONTROL_SURFACE | session/chat/tool permission boundary; blocked by no-session.py/no session runtime rule. |
| 4011 | GET | `/godmode/status` | CONTROL_SURFACE | governance/approval privileged control surface; requires dedicated signed-gate router contract. |
| 4033 | POST | `/godmode` | CONTROL_SURFACE | governance/approval privileged control surface; requires dedicated signed-gate router contract. |
| 4184 | POST | `/brain/agent-trace/event` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 4213 | GET | `/brain/agent-trace/latest` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |
| 4225 | GET | `/brain/agent-trace/stream` | READ_ONLY_PROVIDER_NEEDED | GET/read-like endpoint remains but has provider/global/runtime ambiguity; deferred rather than risk behavior drift. |

## Validation

- python -m py_compile tmp_agent/brain_v9/main.py
- python -m py_compile tmp_agent/brain_v9/routes/read_only_diagnostics_extra.py
- python -m py_compile tests/contract/test_main_routes_readonly_extra_split_13f.py
- python tests/contract/test_main_routes_readonly_extra_split_13f.py: 8/8 passed
- python tests/contract/test_main_routes_readonly_diagnostics_split_13e.py: 9/9 passed
- python tests/contract/test_main_routes_validators_observability_split_13d.py: 9/9 passed
- python tests/contract/test_main_routes_health_status_deferred_split_13c.py: 9/9 passed
- python tests/contract/test_main_routes_startup_state_adapter_13b.py: 10/10 passed
- python tests/contract/test_main_routes_health_status_split_13a.py: 8/8 passed
- python tests/contract/test_main_router_topology_contract_12b.py: 13/13 passed
- python tests/contract/test_main_router_dev_surface_guard_12c.py: 11/11 passed
- python tests/contract/test_main_router_surface_matrix_12d.py: 12/12 passed
- python tests/contract/test_main_router_auth_permission_contract_12e.py: 9/9 passed
- python tests/contract/test_main_router_side_effect_boundary_12f.py: 9/9 passed
- python tests/unit/test_ollama_config_session_message_11d_c.py: 5/5 passed
- python tests/unit/test_ollama_config_centralization_11d_b.py: 11/11 passed
- python tests/integration/test_autonomy_e2e_memory_tool_fallback_11c.py: OK
- python tests/unit/test_scvl_final_answer_gate_01.py: OK
- python tests/unit/test_scvl_semantic_promotion_gate_01.py: OK

## No-Touch Confirmation

- session.py not touched
- dashboard files not touched
- trading/QC/IBKR files not touched
- SCVL files not touched
- memory/semantic runtime data not touched
- FAISS files not touched
- semantic_memory_faiss.py not touched
- no live APIs executed
- no servers started
- no push

## Recommended Next Fronts

- FRONT-BRAIN-MAIN-ROUTES-CURATED-KNOWLEDGE-SPLIT-13G for curated lookup endpoints only.
- FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-GATE-SPLIT-13H for /gate and /tool01 permission surfaces only.
- FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-BOUNDARY-13I only after session routing boundary is stable.
