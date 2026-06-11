# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-EXECUTE-SECURITY-GOVERNANCE-01

## Objective

Execute the first canary ingestion (memory-only, no FAISS) for the `security_governance_sandboxing` domain, using the user-approved package.

## Approval Phrase Used

```
APPROVE_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_SEC_GOV_CANARY_001
```

## Batch Details

| Field | Value |
|-------|-------|
| batch_id | SEC_GOV_CANARY_001 |
| domain | security_governance_sandboxing |
| appended_count | 5 |
| source_ids | nist_csf, nist_ai_rmf, opa_docs, mitre_atlas, gvisor_docs |
| apprended_memory_ids | SEC_GOV_CANARY_001_nist_csf_001, SEC_GOV_CANARY_001_nist_ai_rmf_002, SEC_GOV_CANARY_001_opa_docs_003, SEC_GOV_CANARY_001_mitre_atlas_004, SEC_GOV_CANARY_001_gvisor_docs_005 |

## Before / After Counts

| Metric | Before | After |
|--------|--------|-------|
| semantic_memory.jsonl lines | 1710 | 1715 |
| FAISS index SHA | b7b755c753cd4017344fb18d51e2ff3d81766151ac3a3dbf753c1004f7d16484 | unchanged |
| FAISS ids count | 1611 | 1611 |
| FAISS ids SHA | 004362363f7a392fd15193392f7fac592e333355e6cc28ba665d3cfb5e9368c1 | unchanged |

## Backup Manifest Summary

- **Backup dir:** `tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/`
- **Files backed up:** semantic_memory.jsonl, semantic_memory_faiss.index, semantic_memory_faiss_ids.json
- **Backup verified:** SHA256 matches original for all 3 files
- **Restore instructions:** Copy backup files back to `memory/semantic/` and verify SHA256

## Append Manifest Summary

- **Target file:** `memory/semantic/semantic_memory.jsonl`
- **Appended at:** 2026-06-11T08:12:36+00:00
- **Records appended:** 5
- **All records:** ingestion_status=ingested_memory_only, faiss_eligible=false, faiss_embedding_text=""
- **User approval phrase:** present in each record

## Post-Append Validation

- ✅ Memory line count: 1715 (expected)
- ✅ FAISS index SHA: unchanged
- ✅ FAISS ids count: 1611 (expected)
- ✅ No duplicate memory_id
- ✅ All 5 records domain=security_governance_sandboxing
- ✅ All 5 records acceptance_status=accept
- ✅ All 5 records ingestion_status=ingested_memory_only
- ✅ All 5 records user_approval_phrase present
- ✅ All 5 records faiss_eligible=false
- ✅ All 5 records faiss_embedding_text=""
- ✅ No rejected/hold/candidate/financial/coding sources
- ✅ No broker_api/trading_signal/executable_code/chain_of_thought fields

## Tests

- 32/32 smoke tests passed
- All py_compile checks passed

## Safety Proof

- **FAISS mutated:** false
- **Embeddings created:** false
- **Broker/API used:** false
- **Trading used:** false

## Rollback Instructions

If needed, restore from backup:
```bash
cp tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/semantic_memory.jsonl memory/semantic/
cp tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/semantic_memory_faiss.index memory/semantic/
cp tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/semantic_memory_faiss_ids.json memory/semantic/
```

Then verify counts return to baseline (1710 lines, 1611 FAISS ids).

## Next Recommended Front

`FRONT-EXTERNAL-CURATED-LEARNING-CANARY-POST-INGESTION-VERIFY-SECURITY-GOVERNANCE-01` — **LOCKED** pending user request.
