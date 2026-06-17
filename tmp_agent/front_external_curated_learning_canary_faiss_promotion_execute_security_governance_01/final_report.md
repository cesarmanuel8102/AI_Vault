# Final Report: FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01

**Status**: FAISS_PROMOTION_EXECUTED_SECURITY_GOVERNANCE_CANARY

**Branch**: codex/own-capital-sustainable-return

## Commits

| Type | Commit | Description |
|------|--------|-------------|
| functional | edd455a | learning: execute security governance canary FAISS promotion |
| ledger | 9ed1d8c | ledger: record security governance canary FAISS promotion execution |

## Head State

- **local HEAD**: 9ed1d8c
- **remote HEAD**: 9ed1d8c
- **local == remote**: Yes

## Batch Details

- **batch_id**: SEC_GOV_CANARY_001
- **promoted_count**: 5

## Promoted IDs

1. SEC_GOV_CANARY_001_nist_csf_001
2. SEC_GOV_CANARY_001_nist_ai_rmf_002
3. SEC_GOV_CANARY_001_opa_docs_003
4. SEC_GOV_CANARY_001_mitre_atlas_004
5. SEC_GOV_CANARY_001_gvisor_docs_005

## Source IDs

- nist_csf
- nist_ai_rmf
- opa_docs
- mitre_atlas
- gvisor_docs

## FAISS Before / After

| Metric | Before | After |
|--------|--------|-------|
| FAISS ids count | 1611 | 1616 |
| FAISS ntotal | 1611 | 1616 |

## Semantic Memory

- **semantic_memory.jsonl lines**: 1715 (unchanged)
- **Mutated**: false

## Safety

| Check | Value |
|-------|-------|
| semantic_memory_mutated | false |
| faiss_mutated | true |
| embeddings_created | true |
| rollback_available | true |
| broker_api_used | false |
| trading_used | false |

## Retrieval Eval

| Metric | Value |
|--------|-------|
| top_1_hit_rate | 0.875 |
| top_3_hit_rate | 1.0 |
| top_5_hit_rate | 1.0 |
| mrr | 0.9375 |
| domain_precision | 0.725 |

## Negative Contamination

- **Detected**: false
- All 5 negative queries returned no trading/broker/coding contamination.

## Tests

- **25 / 25 passed**

## Next Front

- **FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-POST-PROMOTION-VERIFY-SECURITY-GOVERNANCE-01**
- Status: **LOCKED**

## Verification

| Check | Result |
|-------|--------|
| local_equals_remote_branch | true |
| staged_empty | true |
| unstaged_tracked_empty | true |
| roadmap_valid | true |
| tests_passed | true |
| memory_lines | 1715 |
| faiss_ids | 1616 |
