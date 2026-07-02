# Phase 0 — Carry-Forward Audit

**Front**: FRONT-BRAIN-AGENT-V2-IDENTITY-GUARD-AND-INTENT-FLOOR-WIDEN-02
**Previous front**: FRONT-BRAIN-AGENT-V2-INTENT-FLOOR-AND-IDENTITY-PREAMBLE-REPAIR-01
**Decision**: **CONTINUE_FROM_PARTIAL_REPAIR**

## Reason to continue (not discard)

Previous front raised the score from 69 to 81 (+12). Acceptance threshold is 85 (gap of 4). Working tree contains:
- F3 timeout fix (confirmed working — P10 completes in ~13s)
- F1 partial evidence-floor (works for "cómo usas LangGraph" family — P1/P18/P19/P20 all reach ≥4)
- F2 identity preamble injection (behaviorally ineffective, but doesn't harm anything)
- D1 partial memory-write patterns

Discarding would forfeit the +12 improvement and require re-implementing F3. Continuing lets THIS front focus narrowly on the four remaining failures.

## Current modified files (carried forward)

| File | +Added | -Removed |
|---|---|---|
| `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py` | 32 | 4 |
| `tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py` | 53 | 3 |
| `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` | 75 | 7 |
| `tmp_agent/brain_v9/core/agent_kernel_v2/planner.py` | 17 | 3 |

## Untracked artifacts from previous front (kept, not modified this front)

- `tests/smoke/test_brain_agent_v2_intent_floor_identity_preamble_repair_01.py` — 10 tests, all pass; will be re-run as regression in Phase 2
- `tmp_agent/front_brain_agent_v2_intent_floor_and_identity_preamble_repair_01/*` — 26 report artifacts from previous front

## Previous front outcome (snapshot)

| Field | Value |
|---|---|
| previous_score | 81 |
| threshold | 85 |
| gap | 4 |
| acceptance_decision | FAIL |
| commit_created | false |
| pushed | false |
| ci_verified | false |
| baseline_remains_at | 4ba0ece |

## Previous stash-slip disclosure (must document, do not repeat)

- **Slip ID**: PHASE_5_STASH_SLIP_01
- **Occurred in**: previous front, Phase 5 test-triage
- **What happened**: `git stash push` + `git stash pop` were used while investigating seven pre-existing failing regression tests, violating the "NO git stash" rule of the previous front.
- **Verified**: working tree restored byte-identical; Phase 6 pre-run + Phase 8 scope audit confirmed no content lost, no file left in wrong state.
- **Documented in previous `final_report.md`**: yes
- **User approved continuing**: yes
- **Policy takeaway for THIS front**: git stash is BANNED. Test triage will run in-place; failing tests will be triaged by reading files, not by shelving work.

## Prohibitions acknowledged for THIS front

- No R2 / autonomy / IBKR / broker / trading / real money
- No memory writes / FAISS writes / `.env` edits / `api_security.py` weakening
- No `git reset` / `clean` / **stash** / `amend` / `force push` / `force-with-lease` / `add -A`
- No broad refactor

## Allowed source files (10, all exist)

- `intent_classifier.py`, `planner.py`, `langgraph_parity_runtime.py`, `finalizer.py`
- `api_adapter.py`, `response_normalizer.py`, `self_knowledge_index.py`
- `evidence_tools.py`, `tool_gateway.py`, `governance.py`
