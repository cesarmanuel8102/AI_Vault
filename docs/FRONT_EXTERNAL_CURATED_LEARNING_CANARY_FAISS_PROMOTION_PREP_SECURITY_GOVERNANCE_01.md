# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01

## Objective

Prepare a read-only FAISS promotion package for the security governance canary batch (SEC_GOV_CANARY_001), pending explicit user approval before any FAISS mutation.

## Explicit User Authorization for Prep Only

This front is a **dry-run / prep only**.
- No FAISS mutation occurred.
- No embeddings were created.
- No model calls were made.
- No memory append occurred.
- All preparation is deterministic and read-only.

## Batch Details

- **batch_id**: `SEC_GOV_CANARY_001`
- **domain**: `security_governance_sandboxing`
- **candidate_count**: 5

## Memory IDs

1. `SEC_GOV_CANARY_001_nist_csf_001`
2. `SEC_GOV_CANARY_001_nist_ai_rmf_002`
3. `SEC_GOV_CANARY_001_opa_docs_003`
4. `SEC_GOV_CANARY_001_mitre_atlas_004`
5. `SEC_GOV_CANARY_001_gvisor_docs_005`

## Source IDs

- `nist_csf`
- `nist_ai_rmf`
- `opa_docs`
- `mitre_atlas`
- `gvisor_docs`

## Embedding Text Design

- **Deterministic**: same input always produces same output
- **Built only from existing record fields**: source_title, source_id, domain, taxonomy_tags, capability_target, content_summary, retrieval_phrases
- **No model call**: no embedding model invoked
- **No embeddings created**: only text strings are built for preview/SHA

## Promotion Plan

- **promotion_status**: `proposed_only`
- **expected FAISS ids before**: 1611
- **expected FAISS ids after if approved**: 1616
- **memory lines remain**: 1715

## Human Approval Package

- **approval phrase required**:
  ```
  APPROVE_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_SEC_GOV_CANARY_001
  ```
- **denial phrase**:
  ```
  DENY_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_SEC_GOV_CANARY_001
  ```

## Backup / Rollback Plan

- Backup FAISS index and ids files before promotion.
- Rollback restores previous index + ids if promotion fails.
- Plan captured in:
  `tmp_agent/front_external_curated_learning_canary_faiss_promotion_prep_security_governance_01/backup_rollback_plan.json`

## Future Execution Plan

- Next front: `FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01`
- That front will:
  1. Verify approval phrase from user
  2. Backup existing FAISS
  3. Generate embeddings for the 5 canary records
  4. Add vectors to FAISS index
  5. Update ids JSON
  6. Verify counts (1616 ids)
  7. Run retrieval eval
  8. Report results
- That front is **LOCKED** until the exact approval phrase is provided.

## No Mutation Proof

- semantic_memory.jsonl lines: 1715 (unchanged from baseline)
- semantic_memory.jsonl SHA: unchanged
- semantic_memory_faiss.index SHA: unchanged
- semantic_memory_faiss_ids.json SHA: unchanged
- FAISS ids count: 1611 (unchanged)

## Tests Result

- **40 / 40 passed**

## Next Front Status

- **FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01**
- Status: **LOCKED**
- Reason: Requires exact user approval phrase because this next front will mutate FAISS.
