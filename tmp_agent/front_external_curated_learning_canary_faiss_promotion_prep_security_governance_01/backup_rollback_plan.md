# Backup / Rollback Plan
**Batch ID:** SEC_GOV_CANARY_001

## Files to Backup
- memory/semantic/semantic_memory_faiss.index
- memory/semantic/semantic_memory_faiss_ids.json
- memory/semantic/semantic_memory.jsonl

## Backup Directory
`tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/`

## Rollback Method
- Restore exact FAISS index backup from backup directory
- Restore exact FAISS ids backup from backup directory
- Verify FAISS ids count back to 1611
- Verify semantic memory line count stays 1715
- Verify SHA256 matches baseline

## Rollback Triggers
- Embedding generation failure
- FAISS add failure
- FAISS ids count mismatch
- Duplicate FAISS id
- Retrieval eval regression
- Contaminated retrieval
- Schema mismatch
- py_compile or test failure
- User denial

## Validation After Rollback
- faiss_ids_count: 1611
- semantic_memory_lines: 1715
- faiss_index_sha_matches_baseline: True
- faiss_ids_sha_matches_baseline: True
