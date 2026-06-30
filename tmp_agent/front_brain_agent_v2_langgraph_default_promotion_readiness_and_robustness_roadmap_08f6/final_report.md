# Final Report — FRONT-BRAIN-AGENT-V2-LANGGRAPH-DEFAULT-PROMOTION-READINESS-AND-ROBUSTNESS-ROADMAP-08F6

## Scope

Report-only readiness review and robustness roadmap for promoting LangGraph Agent V2 from opt-in to default. No source code, tests, runtime, dashboard, API security, environment/secrets, memory/FAISS, trading/broker, journal/promotion, or default-backend changes were made.

## Baseline

- **Starting baseline:** `6ecc495b6f505683edbae2de35dfccf6831698d5`
- **Branch:** `codex/own-capital-sustainable-return`
- **Previous front:** FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Phase completion

| Phase | Status |
|---|---|
| 0 — State lock | COMPLETED |
| 1 — Baseline confirmation | COMPLETED |
| 2 — Native vs LangGraph comparison | COMPLETED |
| 3 — Default promotion gate matrix | COMPLETED |
| 4 — LangGraph suite adoption plan | COMPLETED |
| 5 — Brain knowledge and memory roadmap | COMPLETED |
| 6 — Governance and human gate plan | COMPLETED |
| 7 — Staged promotion plan | COMPLETED |
| 8 — Readiness decision | COMPLETED |
| 9 — Final report | COMPLETED |

## Smoke validation

- **Total tests run:** 37
- **Passed:** 37
- **Failed:** 0
- **Skipped:** 0
- **py_compile:** PASSED
- **Hygiene:** SAFE

## CI status

| Workflow | Status | Run ID |
|---|---|---|
| phase1-ci | success | 28455364187 |
| nontrading-smoke-regression | success | 28455364593 |

## Gate summary

| Status | Count |
|---|---|
| PASS | 6 |
| PARTIAL | 2 |
| FAIL | 0 |
| UNKNOWN | 0 |
| Blockers | 1 |

### Blocking gate

- **GATE-01 — Native parity:** `LangGraphParityRuntimeV2` is missing `plan_run`, `pause_run`, `resume_run`, and `cancel_run`.

### Partial gates

- **GATE-04 — Observability:** GAP-08F5-04: dashboard status route does not expose `backend_fallback_reason`.
- **GATE-08 — Operational cost and model routing:** explicit cost/step/model-routing policy not yet documented.

## Native vs LangGraph comparison summary

| Outcome | Count |
|---|---|
| Native stronger | 5 |
| LangGraph stronger | 8 |
| Equivalent | 5 |
| Default promotion blockers | 2 |

LangGraph is structurally better aligned with Brain's long-term agentic orchestration goals, but two blocking gaps must close before default promotion:

1. Runtime contract completeness: missing `plan_run`, `pause_run`, `resume_run`, `cancel_run`.
2. Checkpoint/resume readiness: no pause/resume methods and the resume path is unverified.

## Staged promotion plan summary

| Stage | State |
|---|---|
| 0 — Current state | COMPLETED |
| 1 — Opt-in expanded smoke | RECOMMENDED |
| 2 — Local canary default (isolated shell) | RECOMMENDED |
| 3 — Configurable local default | BLOCKED_BY_GATE_01 |
| 4 — Default promotion PR/front | BLOCKED_BY_GATE_01 |
| 5 — Knowledge/memory expansion | FUTURE |
| 6 — Domain-specific agent roles | FUTURE |

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

## Known non-blockers

- Pre-existing LSP/type-checker diagnostics in `runtime.py`, `langgraph_parity_runtime.py`, and `main.py` are not introduced by this report-only front and do not affect runtime behavior or smoke tests.
- GAP-08F5-04 is recorded but not a default-promotion blocker for controlled local canary.

## Acceptance

**ACCEPTED_08F6_LANGGRAPH_DEFAULT_PROMOTION_READINESS_AND_ROBUSTNESS_ROADMAP**

## Recorded

`2026-06-30T18:55:00+00:00`
