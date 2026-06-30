# Staged Promotion Plan — 08F6

## Stage 0 — Current state

- **Entry criteria:** Baseline `6ecc495` accepted; Native default; LangGraph opt-in via `AGENT_V2_BACKEND=langgraph`.
- **Exit criteria:** All 08F6 roadmap artifacts accepted.
- **Evidence required:** 08F5 closeout reports and 08F6 readiness review.
- **Rollback path:** Already Native default; unset `AGENT_V2_BACKEND`.
- **Next front:** This front.

## Stage 1 — Opt-in expanded smoke

- **Entry criteria:** 08F6 accepted; Native default preserved.
- **Exit criteria:** Additional scenarios covered; no default change; comparison data collected.
- **Evidence required:** New smoke tests comparing Native vs LangGraph outputs and failure modes.
- **Rollback path:** Unset `AGENT_V2_BACKEND`; revert to Native-only test runs.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-EXPANDED-SMOKE-08F6-R1` or proceed to Stage 2.

## Stage 2 — Local canary default in isolated shell only

- **Entry criteria:** Stage 1 passed; operator wants hands-on LangGraph default experience.
- **Exit criteria:** One terminal/session runs with `AGENT_V2_BACKEND=langgraph`; logs/traces monitored; no production default changed.
- **Evidence required:** Operator log of canary session; trace comparison; issues filed.
- **Rollback path:** Close terminal/session; restart with unset env.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONTROLLED-LOCAL-CANARY-DEFAULT-08F7`.

## Stage 3 — Configurable local default

- **Entry criteria:** All GATE-01 blockers closed; GATE-04 and GATE-08 partial items closed; local canary stable.
- **Exit criteria:** Default controlled by explicit config; rollback documented; no hardcoded default change in source.
- **Evidence required:** Config-driven default selection test; rollback test; dashboard exposes `fallback_reason`.
- **Rollback path:** Change config value or unset env; restart server.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONFIGURABLE-LOCAL-DEFAULT-08F7-R2`.

## Stage 4 — Default promotion PR/front

- **Entry criteria:** All gates PASS; human approval obtained; source patch allowed only in this front.
- **Exit criteria:** Source patch changes default to LangGraph; full CI green; rollback commit plan documented.
- **Evidence required:** Pull request / front report; CI green; parity test suite; rollback runbook.
- **Rollback path:** Revert promotion commit or apply pre-prepared rollback commit.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-DEFAULT-PROMOTION-PATCH-08F7`.

## Stage 5 — Knowledge/memory expansion

- **Entry criteria:** LangGraph default stable in production for defined observation period.
- **Exit criteria:** Controlled memory promotion flow operational; no unauthorized FAISS rebuilds.
- **Evidence required:** Memory promotion front acceptance; retrieval tests; stale-knowledge detection.
- **Rollback path:** Disable memory promotion node; revert to read-only memory retrieval.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-MEMORY-PROMOTION-08F8`.

## Stage 6 — Domain-specific agent roles

- **Entry criteria:** LangGraph default stable; memory boundaries proven; tool governance enforced.
- **Exit criteria:** Sub-agent roles defined but no broker execution enabled.
- **Evidence required:** Role definitions; harness tests; human-gate verification.
- **Rollback path:** Disable sub-agent role nodes; return to single-agent graph.
- **Next front:** `FRONT-BRAIN-MULTI-AGENT-ROLES-ROADMAP-09A`.

## Guardrails

- No stage enables broker/trading execution without a separate risk-governance front.
- Each stage must complete and be accepted before the next stage starts.
- Default promotion is intentionally split into multiple fronts to prevent uncontrolled activation.

## Phase result

PHASE 7 — Staged promotion plan: **COMPLETED**

## Recorded

`2026-06-30T18:45:00+00:00`
