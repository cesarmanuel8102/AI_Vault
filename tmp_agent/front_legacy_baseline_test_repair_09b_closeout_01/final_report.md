# Legacy Baseline Test Repair 09B Closeout 01 — Final Report

## Status

LEGACY_BASELINE_TEST_REPAIR_09B_CLOSEOUT_COMPLETE

## Objective

Repair legacy smoke tests that still expected old fixed memory baselines from before 09A/09B. Align test suite to treat post-09B state as the latest accepted local runtime baseline.

## Tests Repaired

### test_agent_v2_text_dedup_batch_promotion_08f_24.py
- **Failure**: `test_live_jsonl_and_ids_counts_match_post_verify` asserted live counts equal 08F post-verify counts (1780), but live memory advanced to 1771 after 09A+09B.
- **Fix**: Kept all 08F report artifact assertions (manifest counts, increments, uniqueness). Changed live count assertions to:
  - `live >= 08F post-verify` (preserves 08F promotions)
  - `live == 1771` (matches accepted post-09B baseline)
- **Result**: 17/17 pass

### test_memory_git_hygiene_final_01.py
- **Failure**: Three tests asserted fixed counts 1756/1747/1747 from pre-09A baseline.
- **Fix**: Renamed functions to remove hardcoded numbers (`_preserved_1756` → `_preserved`). Added `>=` checks against 08F baseline. Added `==` checks against current accepted baseline (1771/1762/1762). All Git hygiene invariants (untracked, ignored, guard, no staging) remain unchanged.
- **Result**: 15/15 pass

### test_agent_v2_faiss_rebuild_hydration_01.py
- **Failure**: `test_semantic_jsonl_unchanged_after_rebuild` compared JSONL SHA to a hardcoded old baseline.
- **Fix**: Replaced hardcoded SHA with dynamic before/after SHA comparison and count assertions against current accepted baseline (1771/1762/1762).
- **Result**: 7/7 pass

### _accepted_runtime_baseline.py (new helper)
- Centralizes accepted baseline constants for future front updates.

## No Real Regressions Detected

All failures classified as `FIXED_OLD_COUNT_ASSUMPTION` or `FIXED_OLD_SHA_ASSUMPTION`. No functional regressions in auth, promotion, retrieval, or memory safety.

## Memory Safety

- jsonl_records: 1771 (unchanged from 09B)
- faiss_ids_count: 1762 (unchanged from 09B)
- faiss_ntotal: 1762 (unchanged from 09B)
- 08F IDs present: yes
- 09A IDs present: yes
- 09B IDs present: yes
- memory files tracked: no
- memory files staged: no

## Full Regression Results

| Test | Result |
|------|--------|
| test_ingestion_small_batch_09b | 20/20 pass |
| test_ingestion_controlled_e2e_09a | 16/16 pass |
| test_agent_v2_auth_endpoints_01 | 14/14 pass |
| test_memory_git_hygiene_final_01 | 15/15 pass (repaired) |
| test_agent_v2_text_dedup_batch_promotion_08f_24 | 17/17 pass (repaired) |
| test_agent_v2_promotion_candidate_promote_08b | 17/17 pass |
| test_agent_v2_semantic_retrieval_hygiene_01 | 4/4 pass |
| test_agent_v2_faiss_rebuild_hydration_01 | 7/7 pass (repaired) |

## Recommended Next Front

FRONT-INGESTION-MEDIUM-BATCH-09C
