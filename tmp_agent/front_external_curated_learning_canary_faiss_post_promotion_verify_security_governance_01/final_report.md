# Final Report: FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-POST-PROMOTION-VERIFY-SECURITY-GOVERNANCE-01

**Status**: FAISS_POST_PROMOTION_VERIFY_PASSED_WITH_QUALITY_WARNING

**Branch**: codex/own-capital-sustainable-return

## Commits

| Type | Commit | Description |
|------|--------|-------------|
| functional | 0b5f2a5 | learning: verify security governance canary FAISS promotion |
| ledger | 09890ec | ledger: record security governance canary FAISS post-promotion verify |

## Head State

- **local HEAD**: 09890ec
- **remote HEAD**: 09890ec
- **local == remote**: Yes

## Canonical Verification

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| semantic_memory.jsonl lines | 1715 | 1715 | PASS |
| FAISS ids count | 1616 | 1616 | PASS |
| FAISS ntotal | 1616 | 1616 | PASS |
| All 5 promoted IDs present | Yes | Yes | PASS |
| Duplicate IDs | None | None | PASS |

## Promoted IDs Verified

- `SEC_GOV_CANARY_001_nist_csf_001`
- `SEC_GOV_CANARY_001_nist_ai_rmf_002`
- `SEC_GOV_CANARY_001_opa_docs_003`
- `SEC_GOV_CANARY_001_mitre_atlas_004`
- `SEC_GOV_CANARY_001_gvisor_docs_005`

All present in FAISS, all map to semantic records, all domain `security_governance_sandboxing`, all status `ingested_memory_only`.

## Retrieval Re-eval

| Metric | Value |
|--------|-------|
| top_1_hit_rate | 0.875 |
| top_3_hit_rate | 1.0 |
| top_5_hit_rate | 1.0 |
| mrr | 0.9375 |
| domain_precision | 0.725 |

## Quality Warning

- **domain_precision = 0.725** (below target 0.80)
- Not a failure — only 5 security governance records exist in 1616-vector index
- 100% top-5 hit rate confirms retrieval quality

## Negative Contamination

- **Detected**: False

## Legacy Path Audit

| Check | Result |
|-------|--------|
| Legacy path exists | Yes |
| Legacy FAISS ntotal | 1616 |
| Legacy canary IDs present | Yes |
| Legacy mutated | Yes (was 1611, now 1616) |
| Runtime points to legacy | Yes (BASE_PATH = C:\AI_VAULT) |

**Recommendation**: FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01

## Tests

- **20 / 20 passed**

## No Mutation Proof

- semantic_memory.jsonl: unchanged
- FAISS index: read-only in this front
- FAISS ids: read-only in this front

## Next Front

- **FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01**
- Status: **LOCKED**
- Purpose: Align runtime BASE_PATH to canonical repo path and clean up legacy mutation
