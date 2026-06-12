# Brain Autonomous Observer Report Schema

## Purpose
Standardize the report emitted after each governed autonomous front so a human can quickly audit what changed, what was tested, and whether protected safety boundaries held.

## Required Fields
- `front`: canonical front identifier.
- `objective`: concise objective for the front.
- `actions_taken`: ordered list of actions performed.
- `files_changed`: paths intentionally changed by the front.
- `tests_run`: commands, pass/fail state, and test counts.
- `evidence_paths`: evidence artifacts under `tmp_agent/<front>/`.
- `gates_passed`: safety and quality gates that passed.
- `gates_failed`: gates that failed or blocked the front.
- `memory_mutated`: boolean, true only if semantic memory changed under explicit authorization.
- `faiss_mutated`: boolean, true only if FAISS artifacts changed under explicit authorization.
- `trading_touched`: boolean, true if any trading path or execution path was touched.
- `secrets_exposed`: boolean, true if a secret was printed or committed.
- `raw_cot_exposed`: boolean, true if private reasoning or scratchpad content leaked.
- `runtime_used`: runtime endpoint or local mode used for validation.
- `next_recommended_front`: next safe front.
- `human_review_needed`: boolean escalation marker.

## Optional Fields
- `status`
- `commit_hashes.functional_commit`
- `commit_hashes.ledger_commit`
- `blocked_reason`
- `rollback_manual`

## Safety Defaults
Unless explicitly approved and documented, `memory_mutated`, `faiss_mutated`, `trading_touched`, `secrets_exposed`, and `raw_cot_exposed` must be `false`.
