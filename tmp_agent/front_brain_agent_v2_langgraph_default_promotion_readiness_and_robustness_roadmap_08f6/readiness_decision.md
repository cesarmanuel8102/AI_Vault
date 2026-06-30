# Readiness Decision — FRONT-BRAIN-AGENT-V2-LANGGRAPH-DEFAULT-PROMOTION-READINESS-AND-ROBUSTNESS-ROADMAP-08F6

## Scope

This front is report-only. No source code, tests, runtime, dashboard, API security, environment/secrets, memory/FAISS, trading/broker, journal/promotion, or default-backend changes are made.

## Baseline

- **Starting baseline:** `6ecc495b6f505683edbae2de35dfccf6831698d5`
- **Starting baseline short:** `6ecc495`
- **Branch:** `codex/own-capital-sustainable-return`

## Gate summary

| Status | Count |
|---|---|
| PASS | 6 |
| PARTIAL | 2 |
| FAIL | 0 |
| UNKNOWN | 0 |
| Blockers | 1 |

## Blocking gates

### GATE-01 — Native parity

- **Status:** PARTIAL
- **Blocker:** YES
- **Reason:** `LangGraphParityRuntimeV2` is missing `plan_run`, `pause_run`, `resume_run`, and `cancel_run`. `NativeAgentRuntimeV2` exposes all nine production methods.
- **Required evidence before default promotion:** Implement the missing methods and add parity tests against Native behavior.

### GATE-04 — Observability

- **Status:** PARTIAL
- **Blocker:** NO
- **Reason:** GAP-08F5-04: dashboard status route does not expose `backend_fallback_reason`.
- **Required action before default promotion:** Close GAP-08F5-04.

### GATE-08 — Operational cost and model routing

- **Status:** PARTIAL
- **Blocker:** NO
- **Reason:** Explicit cost/step/model-routing policy not yet documented as runtime policy.
- **Required action before default promotion:** Document and enforce the policy.

## Smoke validation

- **Total tests run:** 37
- **Passed:** 37
- **Failed:** 0
- **Skipped:** 0
- **py_compile:** PASSED
- **Hygiene:** SAFE

## CI status at decision

| Workflow | Status | Run ID |
|---|---|---|
| phase1-ci | success | 28455364187 |
| nontrading-smoke-regression | success | 28455364593 |

## Known non-blockers

- Pre-existing LSP/type-checker diagnostics in `runtime.py`, `langgraph_parity_runtime.py`, and `main.py` are not introduced by this report-only front and do not affect runtime behavior or smoke tests.
- GAP-08F5-04 is recorded but not a default-promotion blocker for controlled local canary.

## Decision

**READY_FOR_CONTROLLED_LOCAL_CANARY_ONLY**

LangGraph Agent V2 is operationally ready for opt-in use and for a controlled local canary where the operator explicitly sets `AGENT_V2_BACKEND=langgraph`. It is **not** ready to become the default backend.

## Recommended next front

`FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONTROLLED-LOCAL-CANARY-DEFAULT-08F7`

## Required evidence before default promotion

1. GATE-01 closed: `LangGraphParityRuntimeV2` implements `plan_run`, `pause_run`, `resume_run`, `cancel_run` with parity tests against `NativeAgentRuntimeV2`.
2. GATE-04 closed: dashboard status route exposes `backend_fallback_reason` and `backend_fallback_used`.
3. GATE-08 closed: cost/step/model-routing policy documented and enforced in runtime configuration.
4. Local canary Stage 2 completed with operator logs, trace comparison, and no critical issues.
5. All gates show PASS before any source patch changes the default backend.

## Recorded

`2026-06-30T18:50:00+00:00`
