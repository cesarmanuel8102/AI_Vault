# FRONT-REAL-MEMORY-FAISS-PROMOTION-01

## Status: COMPLETE

**Decision:** PROMOTED_CANARY_TO_FAISS
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**Head Before:** feb069b9

## Purpose

Execute the first controlled canary promotion from `memory/semantic/semantic_memory.jsonl` to the FAISS index, limited to a single canary record.

## Canary Record

- **ID:** `canary-00000000-0000-0000-0000-000000000001`
- **Source:** `front_real_canary_exec_01`
- **Text:** *Canary record for controlled real write verification...*
- **In JSONL:** Yes, exactly once, last line

## Files Created

- `brain/semantic_memory_faiss_promotion.py` — single-record promotion adapter
- `docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md` — this document
- `tests/smoke/smoke_front_real_memory_faiss_promotion_01.py` — 18 smoke tests

## Evidence Files (not staged)

- `tmp_agent/front_real_memory_faiss_promotion_01/backups/*` — full backups before promotion
- `tmp_agent/front_real_memory_faiss_promotion_01/baseline_snapshot.json` — hashes before
- `tmp_agent/front_real_memory_faiss_promotion_01/faiss_inventory.json/.md`
- `tmp_agent/front_real_memory_faiss_promotion_01/promotion_plan.json/.md`
- `tmp_agent/front_real_memory_faiss_promotion_01/pre_write_validation.json`
- `tmp_agent/front_real_memory_faiss_promotion_01/promotion_execution.json`
- `tmp_agent/front_real_memory_faiss_promotion_01/post_promotion_validation.json/.md`

## Files Modified

- `memory/semantic/semantic_memory_faiss.index` — appended canary vector (1606 → 1607)
- `memory/semantic/semantic_memory_faiss_ids.json` — appended canary id (1606 → 1607)

## Files NOT Modified

- `memory/semantic/semantic_memory.jsonl` — unchanged (guaranteed)
- `tmp_agent/brain_v9/core/session.py` — untouched
- `tmp_agent/brain_v9/main.py` — untouched
- `brain/curated_runtime_lookup.py` — untouched

## Promotion Plan Summary

```
records_to_promote: ["canary-00000000-0000-0000-0000-000000000001"]
before_ids_count: 1606
canary_already_present: false
expected_after_ids_count: 1607
duplicate_handling: no_op_if_duplicate
```

## Guarantees

- `semantic_memory_jsonl_modified`: false
- `faiss_write_executed`: true (single canary vector + id)
- `promotion_executed`: true
- `patch_application_executed`: false
- `trading_executed`: false
- `b8_touched`: false
- `backups_created`: true
- `rollback_available`: true

## Test Results

18 smoke tests passed (output saved at `tmp_agent/front_real_memory_faiss_promotion_01/test_results.txt`).

## Next Recommended

FRONT-REAL-PATCH-MATERIALIZATION-01 — first governed patch artifact materialization
