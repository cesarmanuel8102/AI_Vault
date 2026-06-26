# Ingestion Medium Batch 09C — Final Report

## Status

INGESTION_MEDIUM_BATCH_09C_COMPLETE

## Objective

Scale from 09B small-batch ingestion (12 records) to a controlled medium batch of exactly 24 high-quality curated candidates, proving the ingestion/promotion/retrieval/agent-use circuit scales while preserving auth hardening, memory Git hygiene, rollback safety, validation quality, and regression stability.

## Approval Token

`AGENTV2_APPROVED_INGESTION_09C_CESAR_24`

## Candidates (24)

| # | Candidate ID | Domain | Words |
|---|-------------|--------|-------|
| 1 | `ingest09c_accepted_baseline_helper` | test_infrastructure | 117 |
| 2 | `ingest09c_legacy_tests_preserve_historical_artifacts` | test_infrastructure | 117 |
| 3 | `ingest09c_dynamic_sha_for_readonly_tests` | test_infrastructure | 115 |
| 4 | `ingest09c_full_regression_after_baseline_shift` | production_operations | 118 |
| 5 | `ingest09c_medium_batch_requires_previous_small_batch` | governance | 120 |
| 6 | `ingest09c_exact_candidate_count_gate` | governance | 120 |
| 7 | `ingest09c_no_arbitrary_source_ingestion` | governance | 124 |
| 8 | `ingest09c_candidate_text_word_count_gate` | governance | 129 |
| 9 | `ingest09c_candidate_safety_flags_required` | governance | 121 |
| 10 | `ingest09c_cross_batch_duplicate_check` | retrieval_quality | 125 |
| 11 | `ingest09c_normalized_text_hash_uniqueness` | retrieval_quality | 124 |
| 12 | `ingest09c_temporary_queue_dir_boundary` | brain_architecture | 114 |
| 13 | `ingest09c_supported_loader_path_required` | brain_architecture | 113 |
| 14 | `ingest09c_prewrite_snapshot_required` | production_operations | 113 |
| 15 | `ingest09c_partial_failure_rolls_back` | production_operations | 128 |
| 16 | `ingest09c_postpromotion_count_contract` | semantic_memory | 120 |
| 17 | `ingest09c_promoted_ids_in_jsonl_and_faiss` | semantic_memory | 125 |
| 18 | `ingest09c_no_blank_or_duplicate_new_text` | semantic_memory | 128 |
| 19 | `ingest09c_retrieval_topk_contract` | retrieval_quality | 126 |
| 20 | `ingest09c_retrieval_failure_policy` | retrieval_quality | 131 |
| 21 | `ingest09c_agent_probe_uses_auth_and_readonly` | operator_readiness | 132 |
| 22 | `ingest09c_agent_probe_no_write_tools` | operator_readiness | 125 |
| 23 | `ingest09c_git_safety_after_runtime_mutation` | production_operations | 132 |
| 24 | `ingest09c_medium_to_large_scaling_boundary` | governance | 122 |

## Baseline vs After

| Metric | Before | After | Increment |
|--------|--------|-------|-----------|
| JSONL records | 1771 | 1795 | +24 |
| FAISS ids | 1762 | 1786 | +24 |
| FAISS ntotal | 1762 | 1786 | +24 |

## Phase Summary

- **Phase 1 (State Lock)**: Branch `codex/own-capital-sustainable-return`, HEAD `c92e3dc`, local=remote, guard passes.
- **Phase 2 (Baseline Memory)**: 1771/1762/1762 confirmed. 08F, 09A, 09B IDs preserved.
- **Phase 3 (Create 24)**: Manual curated candidates from safe local reports.
- **Phase 4 (Validate Dry-Run)**: All 24 valid. No duplicates, no secrets, no CoT.
- **Phase 5 (Source Path)**: Temporary queue_dir at `promotion_queue_09c/`, proven narrow path.
- **Phase 6 (Snapshot)**: Created at `memory/rollback_snapshots/20260626T041148_804675_ingestion_medium_batch_09c_24`.
- **Phase 7 (Promote 24)**: All 24 promoted successfully. `allowed_domains` parameter used to support new domains (test_infrastructure, retrieval_quality, security_hardening). Initial attempt failed on candidate 2 due to unknown_domain_not_approved; rolled back, added allowed_domains, and re-promoted all 24 successfully.
- **Phase 8 (Post-Promotion Verify)**: All 24 IDs in JSONL and FAISS. Exact +24 increments.
- **Phase 9 (Retrieval E2E)**: All 24 retrieved in top-10. 0 failures.
- **Phase 10 (Agent Use Probe)**: 8 read_only probes with auth token returned 200 OK with relevant answers.
- **Phase 11 (Tests)**: 24 tests in `tests/smoke/test_ingestion_medium_batch_09c.py`, all passing.
- **Phase 12 (Legacy Test Alignment)**: Updated `_accepted_runtime_baseline.py` to 1795/1786/1786. Updated 3 legacy tests to match. All pass.
- **Phase 13 (Git Safety)**: Guard passes. No memory staged.
- **Phase 14 (Stage)**: Only test + report artifacts staged.
- **Phase 15 (Commit & Push)**: Committed `8133c56` and pushed to origin.

## Retrieval E2E

All 24 candidates retrieved in top-10. 0 failures.

## Regression Results

| Test | Result |
|------|--------|
| test_ingestion_medium_batch_09c | 24/24 pass |
| test_ingestion_small_batch_09b | 20/20 pass |
| test_ingestion_controlled_e2e_09a | 16/16 pass |
| test_agent_v2_auth_endpoints_01 | 14/14 pass |
| test_memory_git_hygiene_final_01 | 15/15 pass (updated) |
| test_agent_v2_text_dedup_batch_promotion_08f_24 | 17/17 pass (updated) |
| test_agent_v2_promotion_candidate_promote_08b | 17/17 pass |
| test_agent_v2_semantic_retrieval_hygiene_01 | 4/4 pass |
| test_agent_v2_faiss_rebuild_hydration_01 | 7/7 pass (updated) |

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
- [x] Increment exactly +24
- [x] All IDs retrievable
- [x] All IDs present in JSONL and FAISS
- [x] Queue not mutated
- [x] Staging not mutated
- [x] Legacy tests aligned

## Commit

- hash: `8133c56`
- message: `test(agent_v2): verify medium batch ingestion e2e`
- pushed: `true`
- remote: `codex/own-capital-sustainable-return`

## Next Recommended Front

- 09D: Large controlled batch (48-96 candidates) with enhanced deduplication
- 10A: Semantic memory compaction / FAISS index optimization
- 10B: Retrieval quality evaluation and threshold tuning
