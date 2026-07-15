# MAIN_ROUTER_FINAL_MIGRATION_REPORT_14A

Front: FRONT-BRAIN-MAIN-ROUTER-EXTRA-AGGRESSIVE-COMPLETE-MIGRATION-14A

## Status

MOSTLY_COMPLETED_WITH_DEFERRED

Moved the safest additional runtime route blocks: curated knowledge, gate/tool permissions, dashboard shell, and dev/debug GET diagnostics. Remaining routes are coupled to chat/session, memory/FAISS, trading/strategy, governance mutation, or runtime side effects and should be split by smaller dedicated fronts.

## State

- HEAD initial: 3103047
- HEAD final local: d1c5aaf
- Origin: 3103047
- main.py lines before: 4267
- main.py lines after: 3812
- APP_ENDPOINTS before: 131
- APP_ENDPOINTS after: 114

## Commits Created

- `d1c5aaf refactor(routes): split dev debug endpoints`
- `430a301 refactor(routes): split dashboard shell endpoints`
- `347234a refactor(routes): split gate tool permission endpoints`
- `dc2d9b6 refactor(routes): split curated knowledge endpoints`

## Routers Created

- tmp_agent/brain_v9/routes/curated_knowledge_routes.py
- tmp_agent/brain_v9/routes/gate_tool_routes.py
- tmp_agent/brain_v9/routes/dashboard_shell_routes.py
- tmp_agent/brain_v9/routes/dev_debug_routes.py

## Endpoint Counts Remaining

- total: 114
- DELETE: 3
- GET: 58
- POST: 53

## Remaining Endpoints

| line | method | path | category | reason | next front |
|---:|---|---|---|---|---|
| 1116 | GET | `/brain-dashboard/agent-v2/status` | DASHBOARD_RUNTIME | Agent V2 dashboard status reads runtime runs/provider metadata; leave for dashboard runtime split. | FRONT-BRAIN-MAIN-ROUTES-DASHBOARD-RUNTIME-SPLIT |
| 1138 | GET | `/brain/operating-context` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 1146 | GET | `/brain/maintenance/status` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 1151 | POST | `/brain/maintenance/action` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 1178 | GET | `/chat/introspectivo/debug` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 1204 | POST | `/chat/introspectivo` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 1429 | POST | `/chat` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 1911 | DELETE | `/sessions/{session_id}` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 1921 | DELETE | `/sessions/{session_id}/memory` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 1931 | POST | `/brain/learned/patterns/{pattern_id}/disable` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 1946 | DELETE | `/brain/learned/patterns/{pattern_id}` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 1961 | POST | `/brain/learned/test_simulate` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2056 | GET | `/brain/mutations` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2068 | GET | `/brain/mutations/{mutation_id}` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2084 | POST | `/brain/mutations/{mutation_id}/rollback` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2100 | POST | `/brain/mutations/test_apply` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2153 | GET | `/brain/chat_excellence/status` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2197 | POST | `/brain/scheduler/alerts/ack` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2226 | POST | `/brain/proactive/run/{task_id}` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2252 | POST | `/brain/llm/circuit_breaker/reset` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2271 | GET | `/brain/chat_excellence/proposals` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2282 | GET | `/brain/learning/proposals` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2289 | GET | `/brain/chat_excellence/proposals/{proposal_id}` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2303 | POST | `/brain/chat_excellence/proposals/{proposal_id}/reject` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2322 | POST | `/brain/chat_excellence/proposals/{proposal_id}/dry_run` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2338 | POST | `/brain/chat_excellence/proposals/{proposal_id}/apply` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2391 | POST | `/brain/chat_excellence/proposals/{proposal_id}/rollback` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2408 | GET | `/brain/chat_excellence/proposals/{proposal_id}/health_gate_log` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2420 | POST | `/brain/chat_excellence/proposals/apply_batch` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2473 | POST | `/brain/chat_excellence/proposals/evaluate` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2505 | GET | `/brain/chat_excellence/proposals/{proposal_id}/evaluation_status` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2532 | POST | `/brain/utility/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2552 | POST | `/brain/utility/v2/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2556 | GET | `/brain/autonomy/next-actions` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2561 | GET | `/brain/autonomy/sample-accumulator` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2633 | POST | `/brain/autonomy/execute-top-action` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2642 | GET | `/brain/autonomy/ibkr-ingester` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2662 | POST | `/brain/autonomy/ibkr-snapshot` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2681 | GET | `/brain/operations` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2714 | GET | `/brain/pipeline-health` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2763 | POST | `/brain/post-bl-roadmap/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2768 | POST | `/brain/meta-improvement/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2773 | POST | `/brain/chat-product/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2778 | POST | `/brain/autonomous-governance-eval/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2783 | POST | `/brain/utility-governance/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2788 | GET | `/brain/meta-governance/status` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2800 | GET | `/brain/session-memory` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 2809 | POST | `/brain/roadmap/governance/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2813 | POST | `/brain/learning/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2826 | POST | `/brain/learning/proposals/{proposal_id}/transition` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2840 | POST | `/brain/learning/proposals/{proposal_id}/sandbox-run` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2853 | POST | `/brain/learning/proposals/{proposal_id}/evaluate` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 2866 | GET | `/brain/strategy-engine/summary` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2870 | GET | `/brain/strategy-engine/candidates` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2875 | GET | `/brain/strategy-engine/scorecards` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2879 | GET | `/brain/strategy-engine/ranking` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2884 | GET | `/brain/strategy-engine/ranking-v2` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2889 | GET | `/brain/strategy-engine/features` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2894 | GET | `/brain/strategy-engine/history` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2899 | GET | `/brain/strategy-engine/signals` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2904 | GET | `/brain/strategy-engine/archive` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2909 | GET | `/brain/strategy-engine/expectancy` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2914 | GET | `/brain/strategy-engine/expectancy/by-strategy` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2919 | GET | `/brain/strategy-engine/expectancy/by-venue` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2924 | GET | `/brain/strategy-engine/expectancy/by-symbol` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2929 | GET | `/brain/strategy-engine/expectancy/by-context` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2934 | GET | `/brain/strategy-engine/edge-validation` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2939 | GET | `/brain/strategy-engine/context-edge-validation` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2944 | GET | `/brain/strategy-engine/active-catalog` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2949 | GET | `/brain/strategy-engine/pipeline-integrity` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2954 | GET | `/brain/strategy-engine/post-trade-analysis` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2958 | GET | `/brain/strategy-engine/post-trade-hypotheses` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2962 | GET | `/brain/strategy-engine/learning-loop` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2967 | GET | `/brain/strategy-engine/hypotheses` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 2971 | GET | `/brain/strategy-engine/execution-audit` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3012 | POST | `/brain/strategy-engine/simulation-gate/{strategy_id}` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3023 | GET | `/brain/strategy-engine/adaptation-state` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3036 | GET | `/brain/strategy-engine/session-performance` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3055 | POST | `/brain/ops/log-cleanup` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3062 | GET | `/brain/ops/log-status` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3069 | GET | `/brain/ops/adn-quality` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3075 | GET | `/brain/ops/upgrade-check` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3081 | GET | `/brain/ops/pre-upgrade` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3087 | GET | `/brain/ops/post-upgrade` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3093 | GET | `/brain/ops/ethics` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3099 | POST | `/brain/strategy-engine/refresh` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3103 | POST | `/brain/strategy-engine/execute-top-candidate` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3108 | POST | `/brain/strategy-engine/execute-candidate/{strategy_id}` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3113 | POST | `/brain/strategy-engine/execute-batch/{strategy_id}` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3118 | POST | `/brain/strategy-engine/execute-comparison-cycle` | TRADING_STRATEGY_BLOCKED | Trading/strategy/QC/IBKR adjacent surface; intentionally deferred to avoid changing live financial behavior. | TRADING-ROUTE-SPLIT-DEDICATED |
| 3122 | GET | `/brain/change-control/scorecard` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3127 | GET | `/brain/control-layer/status` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3132 | GET | `/brain/purpose/status` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 3137 | GET | `/brain/consciousness/status` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 3150 | POST | `/brain/purpose/refresh` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 3155 | POST | `/brain/control-layer/freeze` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3160 | POST | `/brain/control-layer/unfreeze` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3164 | POST | `/brain/self-improvement/change` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3168 | POST | `/brain/self-improvement/change/{change_id}/validate` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3172 | POST | `/brain/self-improvement/change/{change_id}/promote` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3176 | POST | `/brain/self-improvement/change/{change_id}/rollback` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3180 | POST | `/brain/validate` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 3186 | POST | `/self-diagnostic/run` | MUTATION_SURFACE | Mutating/control verb or protected state transition; deferred to avoid behavior/security drift. | FRONT-BRAIN-MAIN-ROUTES-CONTROL-MUTATION-SPLIT-14G |
| 3218 | GET | `/brain/semantic-memory/search` | MEMORY_SEMANTIC | Memory/semantic/FAISS data operations; requires exact-copy router plus no-data-mutation hashing. | FRONT-BRAIN-MAIN-ROUTES-MEMORY-SEMANTIC-SPLIT-14D |
| 3240 | POST | `/brain/semantic-memory/ingest` | MEMORY_SEMANTIC | Memory/semantic/FAISS data operations; requires exact-copy router plus no-data-mutation hashing. | FRONT-BRAIN-MAIN-ROUTES-MEMORY-SEMANTIC-SPLIT-14D |
| 3251 | POST | `/brain/semantic-memory/ingest-session` | MEMORY_SEMANTIC | Memory/semantic/FAISS data operations; requires exact-copy router plus no-data-mutation hashing. | FRONT-BRAIN-MAIN-ROUTES-MEMORY-SEMANTIC-SPLIT-14D |
| 3257 | POST | `/brain/metacognition/audit` | DEV_DEBUG_DEFERRED | Remaining dev/debug route has action/runtime side effects or provider ambiguity. | FRONT-BRAIN-MAIN-ROUTES-DEV-DEBUG-SECOND-PASS |
| 3263 | POST | `/agent` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 3495 | POST | `/dev` | CHAT_SESSION | Chat/session runtime coupled to active_sessions, streaming, BrainSession, AgentLoop or dev execution; needs dedicated provider design. | FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F |
| 3556 | GET | `/godmode/status` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3578 | POST | `/godmode` | GOVERNANCE_CONTROL | Governance/control mutation or privileged path; needs dedicated signed-permission contract. | FRONT-BRAIN-MAIN-ROUTES-GOVERNANCE-CONTROL-SPLIT |
| 3729 | POST | `/brain/agent-trace/event` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 3758 | GET | `/brain/agent-trace/latest` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |
| 3770 | GET | `/brain/agent-trace/stream` | PROVIDER_NEEDED | Read-like endpoint still relies on main globals/providers or unclear side effects. | FRONT-BRAIN-MAIN-ROUTES-PROVIDER-READONLY-SPLIT |

## Tests Executed

- py_compile main.py
- py_compile curated_knowledge_routes.py gate_tool_routes.py dashboard_shell_routes.py dev_debug_routes.py
- 13F,13E,13D,13C,13B,13A contracts PASS
- 14A,14B,14C,14E contracts PASS
- 12B,12C,12D,12E,12F contracts PASS
- 11D-C, 11D-B PASS
- 11C integration PASS
- SCVL final answer and semantic promotion PASS

## Failures / Reverts

- No block reverted.
- One contract false-positive was corrected in 14B for approval token scrub checks.
- Line-ending noise occurred in commit 347234a; behavior tests still pass. Do not amend without operator approval.

## No-Touch Confirmation

- memory/semantic runtime data not modified
- FAISS files not modified
- trading engine files not modified
- session.py not modified
- SCVL internals not modified
- semantic_memory_faiss.py not modified
- no servers started
- no live APIs called
- no IBKR/QC/trading live executed
- no push

## Push Recommendation

- Push is authorized after operator review of local commits and line-ending note.

## Next Smallest Front

- FRONT-BRAIN-MAIN-ROUTES-MEMORY-SEMANTIC-SPLIT-14D with before/after file hashes and no-FAISS-write assertions.
- FRONT-BRAIN-MAIN-ROUTES-CHAT-SESSION-SPLIT-14F only after provider boundary design.

