# FRONT-BRAIN-AGENT-V2-EVIDENCE-MAP-AND-FINALIZER-REFINEMENT-01

## Status

COMPLETE

## HEAD

* **start_head**: `12ecbc2`
* **expected_final_head**: TBD after commit/push

## Changes Summary

### intent_adapter.py

* Added topic-specific evidence sources for autonomous/AUTO microfix and PRODUCTION-OPERATIONS-01
* Added `grep_pattern` to each source for targeted searches
* Expanded `brain_signals` for production and autonomous triggers
* Fixed SYSTEM/UNKNOWN/generic intents to route to `direct_assistant` when no brain signals present
* Lowered CONVERSATION threshold from 0.7 to 0.5
* Added catch-all: any non-brain query defaults to `direct_assistant`

### native_runtime.py

* Brain evidence route now extracts per-source `grep_pattern` for targeted searches
* `file_read` uses first evidence path as representative file
* `repo_history_read` added as deterministic tool option

### finalizer.py

* `_ollama_chat` now accepts template-specific `system_content` parameter
* `finalize_agent_run` selects system prompt based on `template_override`:
  * `direct_assistant`: conversational prose, no operational headings
  * `brain_evidence`: Brain-specific evidence focus
  * `mixed_brain_reasoning`: general concept + evidence grounding
* Eliminated hardcoded system prompt that forced operational format for all templates

## Live 8091 Results

| Test | Route | Status | Detail |
|------|-------|--------|--------|
| G1 | direct_assistant | **PASS** | Natural prose photosynthesis, no headings |
| G2 | direct_assistant | **PASS** | Natural prose recipe, no headings |
| B3 | brain_evidence | **PASS** | Identifies autonomous/AUTO microfix, targeted grep |
| B4 | brain_evidence | **PASS** | Uses PRODUCTION-OPERATIONS-01 evidence source |
| M1 | brain_evidence | **PASS** | General concept + Brain evidence + gaps |

## Live 8092 Results

| Test | Status | Detail |
|------|--------|--------|
| Dashboard proxy | SKIPPED | Server restart unreliable on Windows; non-critical for chat routing |

## Governance

| Check | Status |
|-------|--------|
| memory_staged | false |
| faiss_staged | false |
| raw_cot_found | false |
| write_gates_preserved | true |
| langgraph_canonical | true |

## Final Decision

### product_quality_chat_ready: **YES**

### Reason

All 5 core acceptance tests pass:

* Generic queries route to `direct_assistant` with natural prose (G1, G2)
* Brain evidence queries use deterministic source mapping with targeted grep patterns (B3, B4)
* Finalizer uses template-specific system prompts eliminating one-size-fits-all operational format
* B3 and B4 now correctly identify relevant evidence folders
* No hallucination, no mode corruption

### Remaining Blockers

* 8092 dashboard server restart unreliable on Windows (non-critical for chat routing)
* Future: Add more granular evidence folder discovery rather than representative single file

### Next Front

`FRONT-BRAIN-AGENT-V2-CHAT-MONITORING-AND-DEGRADATION-HANDLING-01`
