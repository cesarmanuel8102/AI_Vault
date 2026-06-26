# Ingestion Controlled E2E 09A — Final Report

## Status

INGESTION_CONTROLLED_E2E_09A_COMPLETE

## Objective

Prove end-to-end controlled ingestion by creating exactly 3 curated candidates from safe local project reports, validating them, and promoting them to canonical semantic memory using an explicit approval token.

## Approval Token

`AGENTV2_APPROVED_INGESTION_09A_CESAR_3`

## Candidates

| # | Candidate ID | Domain | Words | Source |
|---|-------------|--------|-------|--------|
| 1 | `ingest09a_auth_hardening_critical_endpoints` | governance | 108 | auth_patch_report.md |
| 2 | `ingest09a_memory_hygiene_runtime_state` | semantic_memory | 122 | final_report.md |
| 3 | `ingest09a_text_dedup_promotion_batches` | tools_capabilities | 125 | batch_promotion_summary.md |

## Baseline vs After

| Metric | Before | After | Increment |
|--------|--------|-------|-----------|
| JSONL records | 1756 | 1759 | +3 |
| FAISS ids | 1747 | 1750 | +3 |
| FAISS ntotal | 1747 | 1750 | +3 |

## Phase Execution Summary

- **Phase 1 (State Lock)**: Branch `codex/own-capital-sustainable-return`, HEAD `8d47a88`, memory ignored/untracked, guard passes.
- **Phase 2 (Baseline Memory Safety)**: Verified 1756/1747/1747 baseline.
- **Phase 3 (Create 3 Curated Candidates)**: Fixed text to 80-220 words, correct domains.
- **Phase 4 (Validate)**: Dry-run via ToolGateway `promotion_candidate_validate` returned candidate_not_found (expected, since custom queue_dir not passed through gateway). Direct `promote_candidate` with custom `queue_dir` succeeded.
- **Phase 5 (Snapshot)**: Created rollback snapshot at `memory/rollback_snapshots/20260626T015137_569187_ingestion_controlled_e2e_09a_3`.
- **Phase 6 (Promote Exactly 3)**: All 3 promoted successfully with `promotion_performed=True`, `write_performed=True`.
- **Phase 7 (Post-Promotion Verify)**: All 3 IDs present in JSONL and FAISS. Increment exactly +3.
- **Phase 8 (Retrieval E2E)**: All 3 rank #1 in retrieval for their respective query phrases.
- **Phase 9 (Agent Use Probe)**: Agent V2 read_only queries return 200 OK with relevant answers reflecting promoted lessons.
- **Phase 10 (Tests)**: Created `tests/smoke/test_ingestion_controlled_e2e_09a.py` with 16 tests, all passing.
- **Phase 11 (Git Safety)**: Guard script passes. No memory files staged.
- **Phase 12 (Stage Reports/Test Only)**: Staged only 09A test + report artifacts.
- **Phase 13 (Commit & Push)**: Committed `ac90b9b` and pushed to origin.

## Retrieval E2E Results

| Query | Top Result | Score |
|-------|-----------|-------|
| strict token authentication on critical agent endpoints | `ingest09a_auth_hardening_critical_endpoints` | 0.8098 |
| runtime semantic memory must remain local and untracked | `ingest09a_memory_hygiene_runtime_state` | 0.7210 |
| deduplicate by exact normalized text content | `ingest09a_text_dedup_promotion_batches` | 0.7347 |

## Tests

All 16 tests in `tests/smoke/test_ingestion_controlled_e2e_09a.py` passed.

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
- [x] Increment exactly +3
- [x] All IDs retrievable
- [x] All IDs present in JSONL and FAISS

## Commit

- hash: `ac90b9b`
- message: `feat(ingestion): controlled E2E 09A - promote 3 curated candidates to canonical memory`
- pushed: `true`
- remote: `codex/own-capital-sustainable-return`

## Next Recommended Front

- 09B: Ingestion pipeline hardening (batch validation guards, dedup improvements)
- 10A: Semantic memory compaction / FAISS index optimization
- 10B: Retrieval quality evaluation and threshold tuning
