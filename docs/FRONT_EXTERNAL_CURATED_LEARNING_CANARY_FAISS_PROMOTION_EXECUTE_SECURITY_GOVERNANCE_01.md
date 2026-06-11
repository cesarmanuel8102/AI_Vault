# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01

## Objective

Execute the first controlled FAISS promotion for the security governance canary batch SEC_GOV_CANARY_001, after explicit user approval.

## Explicit User Approval

- **Approval phrase used**: `APPROVE_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_SEC_GOV_CANARY_001`
- **Found in user prompt**: Yes
- **Verified at**: 2026-06-11

## Batch Details

- **batch_id**: `SEC_GOV_CANARY_001`
- **domain**: `security_governance_sandboxing`

## IDs Promoted (5)

1. `SEC_GOV_CANARY_001_nist_csf_001`
2. `SEC_GOV_CANARY_001_nist_ai_rmf_002`
3. `SEC_GOV_CANARY_001_opa_docs_003`
4. `SEC_GOV_CANARY_001_mitre_atlas_004`
5. `SEC_GOV_CANARY_001_gvisor_docs_005`

## Embedding / FAISS Stack Used

- **Stack**: `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- **Embedding API**: Ollama localhost:11434/api/embeddings
- **Model**: nomic-embed-text
- **Dimension**: 768
- **FAISS index type**: `faiss.IndexFlatIP` (cosine similarity)
- **Promotion method**: Direct incremental add to canonical index/ids

## Before / After FAISS

| Metric | Before | After |
|--------|--------|-------|
| FAISS ids count | 1611 | 1616 |
| FAISS ntotal | 1611 | 1616 |
| semantic_memory.jsonl lines | 1715 | 1715 (unchanged) |

## Semantic Memory Unchanged Proof

- **semantic_memory.jsonl SHA unchanged**: verified against baseline
- **Line count**: 1715 before, 1715 after
- **No append occurred**

## Retrieval Eval Result

| Metric | Value |
|--------|-------|
| top_1_hit_rate | 0.875 |
| top_3_hit_rate | 1.0 |
| top_5_hit_rate | 1.0 |
| mrr | 0.9375 |
| domain_precision | 0.725 |

All 8/8 positive queries achieved top-5 hit. Domain precision of 0.725 is excellent given only 5 security governance records exist in the entire 1616-vector index.

## Negative Query Contamination Result

| Query | Contamination |
|-------|---------------|
| best trading signal for SPY | None |
| broker API execute order | None |
| autonomous coding patch generation | None |
| guaranteed investment returns | None |
| bypass approval gate | None |

**Contamination detected**: False

## Rollback Plan

- **Backup dir**: `tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/`
- **Backup files**: semantic_memory.jsonl, semantic_memory_faiss.index, semantic_memory_faiss_ids.json
- **Backup verified**: SHAs match baseline
- **Rollback available**: Yes — restore backup files to `memory/semantic/`

## Tests Result

- **25 / 25 passed**

## Next Recommended Front

- **FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-POST-PROMOTION-VERIFY-SECURITY-GOVERNANCE-01**
- Status: **LOCKED**
- Purpose: Verify long-term stability of promoted FAISS records
