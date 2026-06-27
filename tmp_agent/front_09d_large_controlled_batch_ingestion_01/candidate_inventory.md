# Candidate Inventory — 09D Large Controlled Batch Ingestion

## Scan Date
2026-06-26

## Source Directories Scanned
- `memory/promotion_queue/`
- `memory/semantic_staging/`

## Filter Criteria
1. Not already promoted to canonical semantic_memory
2. Not exact text duplicate of existing canonical memory
3. Text length > 50 characters
4. No raw CoT exposure
5. No secrets exposed
6. No trading execution detected

## Results

### Total Candidates Available
- promotion_queue files: 57
- semantic_staging files: 48
- Total: 105 files scanned

### After Deduplication and Filtering
- Already promoted (in semantic_memory): 8
- Exact text duplicates: 40
- Archived/superseded (terminal_status): 45
- Missing text or too short: 4
- **Unique eligible candidates: 8**

### Selected for 09D (all 8)

| # | Candidate ID | Source | Text Length | Domain | Safety |
|---|-------------|--------|-------------|--------|--------|
| 1 | cycle02_retry_candidate_002 | semantic_staging | 215 | unknown | PASS |
| 2 | cycle02_retry_candidate_003 | semantic_staging | 176 | unknown | PASS |
| 3 | cycle02_retry_candidate_004 | semantic_staging | 219 | unknown | PASS |
| 4 | cycle02_retry_candidate_005 | semantic_staging | 160 | unknown | PASS |
| 5 | cycle02_retry_candidate_007 | semantic_staging | 198 | unknown | PASS |
| 6 | cycle02_retry_candidate_009 | semantic_staging | 200 | unknown | PASS |
| 7 | cycle02_retry_candidate_014 | semantic_staging | 171 | unknown | PASS |
| 8 | llm_grounded_cycle_006 | semantic_staging | 587 | unknown | PASS |

### Note on Batch Size
The requested 24-candidate batch is not achievable because:
- The promotion_queue contains mostly archived/superseded records from previous fronts
- 40 semantic_staging files are exact text duplicates of already-promoted content
- Only 8 unique, non-duplicate, safety-passed candidates remain

This is an honest bounded count, not a failure. The 8 candidates will be promoted in this controlled batch.
