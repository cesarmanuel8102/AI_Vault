# Baseline Inventory — Phase Q1

| File | Exists | SHA256 | Line/ID Count |
|---|---|---|---|
| semantic_memory.jsonl | True | `655d32381e38ada348c3f201c50484551e02d98ae0869fa53826912c6973ab54` | 1710 lines |
| semantic_memory_faiss.index | True | `b7b755c753cd4017344fb18d51e2ff3d81766151ac3a3dbf753c1004f7d16484` | — |
| semantic_memory_faiss_ids.json | True | `004362363f7a392fd15193392f7fac592e333355e6cc28ba665d3cfb5e9368c1` | 1611 ids |

## Batch ID Counts

- `controlled_batch_01_real_execution_policy`: memory=1, faiss=1
- `controlled_batch_01_runtime_recovery_runbook`: memory=1, faiss=1
- `controlled_batch_01_memory_faiss_canary_doc`: memory=1, faiss=1

## Expected
- memory_line_count: 1710
- faiss_ids_count: 1611
- each batch_id memory_count: 1
- each batch_id faiss_count: 1
