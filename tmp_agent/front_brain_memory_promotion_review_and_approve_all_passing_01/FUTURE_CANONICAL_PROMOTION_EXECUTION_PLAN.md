# FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01 — Future Canonical Promotion Execution Plan

## Scope
This plan describes the next front: **FRONT-BRAIN-CANONICAL-MEMORY-PROMOTION-EXECUTE-APPROVED-01**.
This plan is read-only and does NOT execute any canonical promotion.

## Prerequisites (all must be satisfied before execution)
1. Approval manifest exists: `tmp_agent/front_brain_memory_promotion_review_and_approve_all_passing_01/APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json`
2. Cesar approved the "approve all passing candidates" policy in this front.
3. Backup of `memory/semantic/semantic_memory.jsonl` created and verified.
4. Backup of FAISS index (`memory/semantic/semantic_memory_faiss.index`) created.
5. Backup of FAISS IDs (`memory/semantic/semantic_memory_faiss_ids.json`) created.
6. Hash baseline recorded for all three files.
7. Dry-run append plan prepared showing exact lines to add.
8. Exact list of candidates to write: 5 approved entries (see APPROVED manifest).
9. Post-write retrieval validation planned.
10. Rollback criteria defined (if any write fails validation, restore from backup).
11. Smoke test requirements defined.

## Execution Steps (for the next front)
1. Verify backups exist and hashes match baselines.
2. Load APPROVED manifest and validate all 5 candidates.
3. Generate exact JSONL lines for each approved candidate.
4. Perform dry-run append to a temporary copy of semantic_memory.jsonl.
5. Validate dry-run copy (JSON parseable, no corruption, line count = baseline + 5).
6. If dry-run passes, append to real `memory/semantic/semantic_memory.jsonl`.
7. Update FAISS index with new embeddings (if embedding generation available).
8. Verify retrieval: each new candidate must be retrievable by domain keyword.
9. Run smoke tests to confirm no corruption.
10. Update ROADMAP_STATUS and ledger.

## Hard Constraints (inherited)
- Do NOT modify .env.
- Do NOT touch trading/* or B8/*.
- Do NOT use git reset/clean/stash/amend/force push.
- Only promote candidates listed in APPROVED manifest.
- No rejected/duplicate/held candidates may be promoted.
- Rollback ready at every step.

## Approved Candidates to Promote
| # | Candidate ID | Domain | Confidence |
|---|---|---|---|
| 1 | audit_0017 | coding_debugging | 0.90 |
| 2 | audit_0018 | coding_debugging | 0.89 |
| 3 | audit_0019 | dashboard_reliability | 0.86 |
| 4 | audit_0020 | provider_reliability | 0.91 |
| 5 | audit_0021 | governance | 0.88 |

## Rollback Criteria
- If any JSONL line is malformed after append → restore from backup immediately.
- If FAISS index corruption detected → restore index from backup.
- If retrieval test fails for any candidate → investigate; if unresolvable → restore.
- If semantic_memory.jsonl line count differs from expected → restore.

## Next Front Name
FRONT-BRAIN-CANONICAL-MEMORY-PROMOTION-EXECUTE-APPROVED-01
