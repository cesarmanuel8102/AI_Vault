# NEXT PROMPT RECOMMENDATION

## Completed Front
FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01

## Next Recommended Front
FRONT-BRAIN-CANONICAL-MEMORY-PROMOTION-EXECUTE-APPROVED-01

## Why
- 5 high-confidence candidates have been approved for future canonical promotion.
- All 12 strict safety gates passed.
- No canonical memory has been touched yet.
- Approval manifest exists and is machine-readable.

## Preconditions Before Execution
1. Human review of this approval manifest (Cesar sign-off).
2. Create backups:
   - memory/semantic/semantic_memory.jsonl
   - memory/semantic/semantic_memory_faiss.index
   - memory/semantic/semantic_memory_faiss_ids.json
3. Record hash baselines for all three files.
4. Review the execution plan in:
   tmp_agent/front_brain_memory_promotion_review_and_approve_all_passing_01/FUTURE_CANONICAL_PROMOTION_EXECUTION_PLAN.md
5. Confirm rollback criteria.

## Execution Scope
- Append only 5 approved candidates to canonical semantic_memory.jsonl.
- Update FAISS index if embedding pipeline is ready.
- If FAISS pipeline is not ready, append to semantic_memory.jsonl only and defer FAISS update to a later front.
- Post-write retrieval validation required.
- Rollback must be possible at any step.

## Hard Prohibitions (Inherited)
- Do NOT modify .env.
- Do NOT touch trading/*, B8/*, tmp_agent/strategies/*.
- Do NOT promote rejected/duplicate/held candidates.
- Do NOT use git reset/clean/stash/amend/force push.
