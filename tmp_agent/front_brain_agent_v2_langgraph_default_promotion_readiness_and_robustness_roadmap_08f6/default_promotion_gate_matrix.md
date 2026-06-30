# Default Promotion Gate Matrix — 08F6

## Summary

| Status | Count |
|---|---|
| PASS | 6 |
| PARTIAL | 2 |
| FAIL | 0 |
| UNKNOWN | 0 |
| Blockers | 1 (GATE-01) |

## Gate details

### GATE-01 — Native parity

- **Status:** PARTIAL
- **Blocker:** YES
- **Criteria:**
  - All production methods present
  - `/v2/chat/agent` schema stable
  - `/v2/agent/status` stable
  - trace API stable
  - run persistence stable
- **Evidence:** LangGraph has `create_run`, `execute_run`, `get_run`, `list_runs`, `get_trace`. Missing `plan_run`, `pause_run`, `resume_run`, `cancel_run`. `/v2/chat/agent` schema stable per 08F1 tests.
- **Required next action:** Implement missing production methods in `LangGraphParityRuntimeV2` and add parity tests against Native behavior.

### GATE-02 — Governance parity

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** 08F4-R2 verified `escalate_auto_mode_effective`, `_governance_gate_node`, `READ_ONLY_TOOL_NAMES`, `WRITE_TOOL_NAMES`. No broker tools in `SUPPORTED_READ_TOOLS`.

### GATE-03 — Failure-mode safety

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** 08F4-R2 verified timeout, malformed run state, auto escalation. 08E tests verify fallback.

### GATE-04 — Observability

- **Status:** PARTIAL
- **Blocker:** NO
- **Evidence:** API adapter exposes backend metadata; trace retrieval works. Dashboard status route does not expose `backend_fallback_reason` (GAP-08F5-04).
- **Required next action:** Close GAP-08F5-04 before default promotion front.

### GATE-05 — Rollback

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** 08F5 rollback runbook documented; `runtime.py` already falls back safely.

### GATE-06 — Test/CI

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** 37/37 smoke tests passed; phase1-ci and nontrading-smoke-regression green.

### GATE-07 — Knowledge/Memory boundary

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** No auto-promotion; no FAISS rebuild in runtime; existing promotion queues require explicit fronts.

### GATE-08 — Operational cost and model routing

- **Status:** PARTIAL
- **Blocker:** NO
- **Evidence:** No expensive model hardcoded. Explicit cost/step budgets not yet documented as runtime policy.
- **Required next action:** Document and enforce cost/step/model-routing policy before default promotion.

### GATE-09 — Human operator control

- **Status:** PASS
- **Blocker:** NO
- **Evidence:** Auto write-intent escalates to `approval_required`; fallback via env; audit trail via TraceStore and run.json.

## Phase result

PHASE 3 — Default promotion gate matrix: **COMPLETED**

## Recorded

`2026-06-30T18:25:00+00:00`
