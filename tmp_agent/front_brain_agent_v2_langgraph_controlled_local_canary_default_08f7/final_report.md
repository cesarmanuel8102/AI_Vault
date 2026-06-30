# Final Report — FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONTROLLED-LOCAL-CANARY-DEFAULT-08F7

## Scope
Report-only controlled local canary. No source code, tests, runtime, dashboard, API security, secrets, memory/FAISS, trading, journal, or promotion queue files were modified. Native default backend remains unchanged.

## Branch and baseline
- **Branch:** `codex/own-capital-sustainable-return`
- **Starting baseline:** `ce82142d6047aaec25f4a80a719a3c43b79702cc`
- **Previous front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-DEFAULT-PROMOTION-READINESS-AND-ROBUSTNESS-ROADMAP-08F6`

## Phase completion
| Phase | Status |
|---|---|
| 0 State lock | COMPLETED |
| 1 Baseline confirmation | COMPLETED |
| 2 Canary environment plan | COMPLETED |
| 3 Native default control | COMPLETED |
| 4 LangGraph canary selection | COMPLETED |
| 5 Rollback probe | COMPLETED |
| 6 Smoke validation matrix | COMPLETED |
| 7 Dashboard/trace canary | COMPLETED |
| 8 Blocker status review | COMPLETED |
| 9 Canary decision | COMPLETED |
| 10 Recommended repair fronts | COMPLETED |
| 11 Final report | COMPLETED |

## Smoke validation
- **Tests run:** 37
- **Passed:** 37
- **Failed:** 0
- **Skipped:** 0
- **py_compile:** PASSED
- **Hygiene check:** SAFE

## Canary evidence
### Native default control
- `AGENT_V2_BACKEND` unset.
- `backend_selected`: `native_runtime`.
- No fallback.

### LangGraph canary selection
- `AGENT_V2_BACKEND=langgraph` in isolated shell.
- `backend_selected`: `langgraph_parity`.
- `graph_available`: `true`.
- `execute_timeout_seconds`: `30.0`.
- No fallback.

### Rollback
- `AGENT_V2_BACKEND` unset after canary.
- `backend_selected`: `native_runtime`.
- No code or git changes required.

### Dashboard/trace
- Chat and trace proxies require `BRAIN_ADMIN_TOKEN`.
- Token is forwarded but never returned to clients.
- Dashboard status exposes `agent_v2.backend`.
- API chat response exposes `backend_selected`, `backend_fallback_used`, `backend_fallback_reason`.
- Dashboard status does **not** yet expose `backend_fallback_reason` or `backend_fallback_used` (GAP-08F5-04).

## Gate status
| Gate | Name | Status |
|---|---|---|
| GATE-01 | Native parity | OPEN / BLOCKER |
| GATE-04 | Observability | PARTIAL |
| GATE-08 | Operational cost/model routing | PARTIAL |

GATE-01 remains the only hard blocker for global default promotion.

## Decision
**CANARY_ACCEPTED_READY_FOR_PARITY_REPAIR**

- `canary_safe`: `true`
- `default_promotion_safe_now`: `false`
- `ready_to_make_langgraph_default_now`: `false`

## Recommended next fronts
1. **FRONT-BRAIN-AGENT-V2-LANGGRAPH-PRODUCTION-METHOD-PARITY-08F7-R1** — close GATE-01.
2. **FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-FALLBACK-OBSERVABILITY-08F7-R2** — close GATE-04.
3. **FRONT-BRAIN-AGENT-V2-RUNTIME-BUDGET-AND-MODEL-ROUTING-GOVERNANCE-08F7-R3** — close GATE-08.

## Required evidence before default promotion
- GATE-01 closed with parity tests.
- GATE-04 closed with dashboard fallback observability.
- GATE-08 closed with documented and enforced cost/model-routing policy.
- Local canary Stage 2 completed with operator logs and trace comparison.
- All gates PASS before any source patch changes the default backend.

## Known non-blockers
Pre-existing LSP/type-checker diagnostics in `runtime.py`, `langgraph_parity_runtime.py`, `main.py`, `langgraph_runtime.py`, and `dashboard_routes.py` are not introduced by this report-only front and do not affect runtime behavior or smoke tests.

## Conclusion
The 08F7 controlled local canary is complete and accepted. LangGraph can be selected in an isolated shell via `AGENT_V2_BACKEND=langgraph`, observed through existing dashboard/API surfaces, and rolled back cleanly to Native. Default promotion is intentionally blocked by GATE-01 until method parity is implemented in the recommended follow-up front.
