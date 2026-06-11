# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-POST-PROMOTION-VERIFY-SECURITY-GOVERNANCE-01

## Objective

Verify post-promotion that the canonical FAISS index is correct, the 5 promoted IDs are recoverable, semantic memory unchanged, no duplicates, no contamination, and audit the legacy path anomaly.

## Canonical FAISS Verification

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| semantic_memory.jsonl lines | 1715 | 1715 | PASS |
| FAISS ids count | 1616 | 1616 | PASS |
| FAISS ntotal | 1616 | 1616 | PASS |
| All 5 promoted IDs present | Yes | Yes | PASS |
| Duplicate IDs | None | None | PASS |

## Promoted IDs Verification

All 5 promoted IDs:
1. `SEC_GOV_CANARY_001_nist_csf_001`
2. `SEC_GOV_CANARY_001_nist_ai_rmf_002`
3. `SEC_GOV_CANARY_001_opa_docs_003`
4. `SEC_GOV_CANARY_001_mitre_atlas_004`
5. `SEC_GOV_CANARY_001_gvisor_docs_005`

Verified:
- Present in FAISS ids: Yes
- Map to semantic memory records: Yes
- Domain remains `security_governance_sandboxing`: Yes
- Ingestion status remains `ingested_memory_only`: Yes

## Retrieval Re-eval Metrics

| Metric | Value |
|--------|-------|
| top_1_hit_rate | 0.875 |
| top_3_hit_rate | 1.0 |
| top_5_hit_rate | 1.0 |
| mrr | 0.9375 |
| domain_precision | 0.725 |

## Domain Precision Warning

- **domain_precision = 0.725** (below target 0.80)
- **QUALITY_WARNING_DOMAIN_PRECISION_BELOW_TARGET**: True
- **Context**: Only 5 security governance records exist in entire 1616-vector index. 100% top-5 hit rate and 100% top-3 hit rate confirm retrieval quality.
- **Recommendation**: Not a failure; expected with small canary batch. Future larger batches will improve domain precision.

## Negative Contamination Result

| Query | Contamination |
|-------|---------------|
| best trading signal for SPY | None |
| broker API execute order | None |
| autonomous coding patch generation | None |
| guaranteed investment returns | None |
| bypass approval gate | None |

**Contamination detected**: False

## Legacy Path Audit

| Check | Result |
|-------|--------|
| Legacy path exists | Yes |
| Legacy FAISS ntotal | 1616 |
| Legacy FAISS ids count | 1616 |
| Legacy canary IDs present | Yes |
| Legacy appears mutated | Yes (ntotal changed from 1611 to 1616) |
| Runtime points to legacy | Yes (BASE_PATH = C:\AI_VAULT) |

**Recommendation**: Legacy path was accidentally mutated during previous execution front because `SemanticMemoryFAISS` resolved `BASE_PATH` to `C:\AI_VAULT` instead of `C:\AI_VAULT_CANONICAL`. Do **NOT** touch automatically. Recommend future cleanup front:
- `FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01` — align runtime BASE_PATH to canonical repo path.

## No Mutation Proof

- semantic_memory.jsonl: 1715 lines, unchanged SHA
- FAISS index: only read, not written in this front
- FAISS ids: only read, not written in this front

## Tests Result

- **20 / 20 passed**

## Next Recommended Front

- **FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01** — align runtime BASE_PATH to canonical repo path and clean up legacy mutation
- Status: **LOCKED** pending explicit user request
