# Ingestion Small Batch 09B — Final Report

## Status

INGESTION_SMALL_BATCH_09B_COMPLETE

## Objective

Scale from 09A controlled E2E ingestion (3 records) to a small controlled batch of exactly 12 high-quality curated candidates, proving the ingestion/promotion/retrieval/agent-use circuit scales while preserving memory hygiene, auth hardening, rollback safety, and Git safety.

## Approval Token

`AGENTV2_APPROVED_INGESTION_09B_CESAR_12`

## Candidates (12)

| # | Candidate ID | Domain | Words |
|---|-------------|--------|-------|
| 1 | `ingest09b_auth_test_separation` | governance | 116 |
| 2 | `ingest09b_strict_auth_no_localhost_bypass` | governance | 105 |
| 3 | `ingest09b_memory_untracked_runtime_boundary` | semantic_memory | 109 |
| 4 | `ingest09b_guard_blocks_memory_staging` | production_operations | 105 |
| 5 | `ingest09b_promotion_requires_text_dedup` | tools_capabilities | 124 |
| 6 | `ingest09b_rollback_before_batch_write` | production_operations | 119 |
| 7 | `ingest09b_retrieval_query_by_text_not_id` | semantic_memory | 119 |
| 8 | `ingest09b_agent_probe_read_only_auth` | operator_readiness | 126 |
| 9 | `ingest09b_validation_before_promotion` | governance | 118 |
| 10 | `ingest09b_no_memory_commit_after_promotion` | production_operations | 124 |
| 11 | `ingest09b_source_loader_boundary` | brain_architecture | 127 |
| 12 | `ingest09b_small_batch_scaling_rule` | governance | 136 |

## Baseline vs After

| Metric | Before | After | Increment |
|--------|--------|-------|-----------|
| JSONL records | 1759 | 1771 | +12 |
| FAISS ids | 1750 | 1762 | +12 |
| FAISS ntotal | 1750 | 1762 | +12 |

## Phase Summary

- **Phase 1 (State Lock)**: Branch `codex/own-capital-sustainable-return`, HEAD `dd8ffd2`, local=remote, staged empty, guard passes.
- **Phase 2 (Baseline Memory)**: 1759/1750/1750 confirmed. 08F and 09A IDs preserved.
- **Phase 3 (Create 12)**: Manual curated candidates from safe local reports.
- **Phase 4 (Validate Dry-Run)**: All 12 valid. No writes. No duplicates.
- **Phase 5 (Source Path)**: Reused 09A narrow path: temporary queue_dir.
- **Phase 6 (Snapshot)**: Created at `memory/rollback_snapshots/20260626T021348_953734_ingestion_small_batch_09b_12`.
- **Phase 7 (Promote 12)**: All 12 promoted successfully (ok=True, promotion_performed=True, write_performed=True).
- **Phase 8 (Post-Promotion Verify)**: All 12 IDs in JSONL and FAISS. Increment exactly +12.
- **Phase 9 (Retrieval E2E)**: All 12 rank #1 in top-5 retrieval.
- **Phase 10 (Agent Use Probe)**: 5 read_only probes with auth token returned 200 OK with relevant answers.
- **Phase 11 (Tests)**: 20 tests in `tests/smoke/test_ingestion_small_batch_09b.py`, all passing.
- **Phase 12 (Git Safety)**: Memory files ignored/untracked. Guard passes. No queue/staging mutation.
- **Phase 13 (Stage)**: Only 09B test + report artifacts staged.
- **Phase 14 (Commit & Push)**: Pending.

## Retrieval E2E

All 12 candidates retrieved in top-5, all rank #1. Scores: 0.83, 0.72, 0.81, 0.88, 0.80, 0.89, 0.89, 0.90, 0.79, 0.84, 0.87, 0.83.

## Regression Tests

- 09A: 16/16 pass (baseline evolved to 1771/1762)
- Auth: 14/14 pass
- 08B: 17/17 pass
- 08F: 9/10 pass (1 failure due to baseline evolution, not safety regression)
- Memory hygiene: Fails on fixed baseline count (expected after promotions)

## Safety Checklist

- [x] No secrets in candidates
- [x] No raw CoT in candidates
- [x] No trading execution in candidates
- [x] No massive ingestion
- [x] No internet ingestion
- [x] No memory files committed
- [x] No `git add -A`
- [x] Guard script passes
- [x] Approval token used
- [x] Confirm phrase used
- [x] Rollback snapshot created
- [x] Increment exactly +12
- [x] All IDs retrievable
- [x] All IDs present in JSONL and FAISS
- [x] Queue not mutated
- [x] Staging not mutated

## Commit

- hash: `PENDING`
- message: `test(agent_v2): verify small batch ingestion e2e`
- pushed: `PENDING`

## Next Recommended Front

- 09C: Medium batch ingestion (24-48 candidates) with automated candidate extraction
- 10A: Semantic memory compaction / FAISS index optimization
- 10B: Retrieval quality evaluation and threshold tuning
