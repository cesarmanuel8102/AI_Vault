# Backup / Rollback Plan
**Batch ID:** SEC_GOV_CANARY_001
**Domain:** security_governance_sandboxing

## Files to Backup
- memory/semantic/semantic_memory.jsonl
- memory/semantic/semantic_memory_faiss.index
- memory/semantic/semantic_memory_faiss_ids.json

## Backup Directory
`tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/backups/SEC_GOV_CANARY_001/`

## Rollback Triggers
- schema validation failure
- memory line count mismatch
- FAISS ids count mismatch
- duplicate memory_id
- rejected source appears
- hold source appears
- retrieval contamination
- py_compile or test failure

## Rollback Method
Restore exact backup files from backup directory to memory/semantic/

## Validation After Rollback
- Sha Equals Baseline: True
- Memory Line Count Equals 1710: True
- Faiss Ids Count Equals 1611: True

## Note
Actual backups will be created in the execute front after user approval. This plan is preparatory only.
