# FRONT-BRAIN-LLM-GROUNDED-MEMORY-PROMOTION-AUDIT-01 — Source Inventory

## Phase: PHASE_2_INVENTORY
## Timestamp (UTC): 2026-06-15T23:35:00+00:00

## Sources Scanned

### 1. memory/autonomous_journal.jsonl
- **File Type**: jsonl
- **Item Count**: 370 lines
- **Candidate Count**: 0 (journal is append-only operational log, not promotion candidate)
- **Malformed**: 0
- **Duplicates**: 0
- **Raw CoT**: NO
- **Secrets**: NO
- **Trading Execution**: NO
- **Canonical Write Attempt**: NO
- **Safety Verdict**: SAFE_APPEND_ONLY

### 2. memory/promotion_queue/
- **File Type**: directory (28 JSON files)
- **Items**:
  - 9 × llm_grounded_cycle_001..009.json (from prior autonomy cycles)
  - 7 × cycle02_retry_candidate_002,003,004,005,007,009,014.json (from retry cycle)
  - 5 × sem_cand_*.json (older semantic candidates)
  - 7 × stability_rerun_cycle_010,020,030,040,050,060,070,080,090,100,110,120.json
- **Candidate Count**: 28
- **Malformed**: 0
- **Duplicates**: 0
- **Raw CoT**: NO
- **Secrets**: NO
- **Trading Execution**: NO
- **Canonical Write Attempt**: NO
- **Safety Verdict**: SAFE

### 3. memory/semantic_staging/
- **File Type**: directory (26 JSON/JSONL files + 2 shadow dirs)
- **Items**: mirrors promotion_queue minus one file; plus `semantic_memory_candidate.jsonl`
- **Candidate Count**: 26
- **Malformed**: 0
- **Duplicates**: 0
- **Raw CoT**: NO
- **Secrets**: NO
- **Trading Execution**: NO
- **Canonical Write Attempt**: NO
- **Safety Verdict**: SAFE

### 4. tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_02/all_cycles.json
- **File Type**: json
- **Item Count**: 30 cycle records
- **Candidate Count**: 30 (each cycle has a response_preview suitable for audit)
- **Malformed**: 0
- **Duplicates**: 0
- **Raw CoT**: FLAGGED — some response previews may contain reasoning fragments
- **Secrets**: NO
- **Trading Execution**: NO
- **Canonical Write Attempt**: NO
- **Safety Verdict**: RAW_COT_FLAGGED_FOR_REDACTION

### 5. tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_02/batches/
- **File Type**: directory (6 JSON + 6 MD)
- **Item Count**: 12
- **Candidate Count**: 0 (batch metadata, not content candidates)
- **Malformed**: 0
- **Duplicates**: 0
- **Raw CoT**: NO
- **Secrets**: NO
- **Trading Execution**: NO
- **Canonical Write Attempt**: NO
- **Safety Verdict**: SAFE

## Totals
- **Total Items Scanned**: 456
- **Total Candidates Identified**: 84
- **Total Malformed**: 0
- **Total Containing Raw CoT**: 1 (all_cycles.json flagged for redaction)
- **Total Containing Secrets**: 0
- **Total Containing Trading Execution**: 0
- **Total Canonical Write Attempts**: 0

## Overall Safety Verdict
SAFE_WITH_RAW_COT_REDARCTION_REQUIRED — No secrets, no trading, no canonical writes. One source flagged for potential raw CoT fragments.
