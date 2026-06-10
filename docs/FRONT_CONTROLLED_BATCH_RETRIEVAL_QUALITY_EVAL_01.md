# FRONT-CONTROLLED-BATCH-RETRIEVAL-QUALITY-EVAL-01

## Status
✅ COMPLETE

## Objective
Evaluate retrieval quality of the controlled batch ingestion from FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01. Read-only operation: no memory write, no FAISS write, no reindex, no network externa, no connectors, no trading, no B8.

## Source Controlled Batch IDs
1. `controlled_batch_01_real_execution_policy`
2. `controlled_batch_01_runtime_recovery_runbook`
3. `controlled_batch_01_memory_faiss_canary_doc`

## Baseline Memory / FAISS Counts
- **Memory line count**: 1710
- **FAISS ids count**: 1611
- Each batch ID: exactly 1 in memory, exactly 1 in FAISS

## Query Suite
Each record tested with 5 semantically varied queries (15 total).

### Record 1 — Real Execution Policy
1. "real execution policy controlled Brain operations memory FAISS trading connectors"
2. "Brain governance limits for memory writes and FAISS promotion"
3. "policy preventing external network connectors trading and B8 actions"
4. "controlled operations gating expectations for real execution"
5. "what document defines limits on Brain real execution"

### Record 2 — Runtime Recovery Runbook
1. "runtime recovery Brain V9 dashboard Ollama health check execution gate"
2. "Brain V9 recovery runbook for local runtime readiness"
3. "health check procedures for Ollama dashboard and execution gate"
4. "how to recover Brain runtime before real execution"
5. "runtime readiness troubleshooting document"

### Record 3 — Memory FAISS Canary Doc
1. "first successful semantic memory FAISS canary promotion template"
2. "controlled semantic memory write and FAISS promotion canary"
3. "verified template for future controlled ingestion"
4. "first memory FAISS canary document"
5. "evidence that Brain learned local source through memory and FAISS"

## Per-Record Results

| Record | Queries | Top-1 | Top-3 | Top-5 | Top-10 |
|---|---|---|---|---|---|
| `controlled_batch_01_real_execution_policy` | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `controlled_batch_01_runtime_recovery_runbook` | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `controlled_batch_01_memory_faiss_canary_doc` | 5 | 5/5 | 5/5 | 5/5 | 5/5 |

## Metrics

| Metric | Value |
|---|---|
| Total queries | 15 |
| Top-1 pass count | 15 |
| Top-3 pass count | 15 |
| Top-5 pass count | 15 |
| Top-10 pass count | 15 |
| Top-5 pass rate | 1.00 |
| Top-10 pass rate | 1.00 |

## Pass Criteria

- Each record found in top-5 for ≥4/5 queries ✅
- Each record found in top-10 for 5/5 queries ✅
- At least 2/5 queries per record top-1 ✅
- Overall top-5 pass rate ≥0.80 ✅
- Overall top-10 pass rate =1.00 ✅
- No memory/FAISS mutation ✅

**Final status**: `FRONT_CONTROLLED_BATCH_RETRIEVAL_QUALITY_EVAL_01_COMPLETE`

## Read-Only Confirmation

| Item | Status |
|---|---|
| Memory written | ❌ No |
| FAISS written | ❌ No |
| Reindex | ❌ No |
| Network externa | ❌ No |
| Connectors | ❌ No |
| Trading | ❌ No |
| B8 | ❌ No |
| Protected files touched | ❌ No |

## Files Created
- `brain/controlled_batch_retrieval_quality_eval.py` — retrieval eval module
- `tests/smoke/smoke_front_controlled_batch_retrieval_quality_eval_01.py` — 24 tests (all passing)
- `docs/FRONT_CONTROLLED_BATCH_RETRIEVAL_QUALITY_EVAL_01.md` — this document

## Lessons Learned
- Ollama `nomic-embed-text` + FAISS IndexFlatIP yields strong semantic retrieval at top-1 for controlled ingestion records with varied query phrasing.
- Read-only evaluation module pattern works cleanly alongside existing SemanticMemoryFAISS infrastructure.
- 15/15 top-1 indicates embeddings are well-aligned with ingestion source semantics.

## Next Recommended Front
`FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01`
