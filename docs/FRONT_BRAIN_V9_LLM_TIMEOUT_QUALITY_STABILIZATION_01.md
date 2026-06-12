# FRONT-BRAIN-V9-LLM-TIMEOUT-QUALITY-STABILIZATION-01

## Status
`BRAIN_V9_LLM_TIMEOUT_QUALITY_STABILIZED`

## Change
- Raised the governed chat LLM budget from a hard `12s` wait to configurable `BRAIN_CHAT_LLM_TIMEOUT` with default `30s` plus a small outer guard.
- Passed `max_time` into `LLMManager.query(...)` so provider selection honors the budget.
- Added a bounded `governed_eval_fallback` fastpath inside `BrainSession.chat` for meta/evaluation prompts when local LLM providers are slow/unavailable.
- The adapter still calls `handle_user_message(...)`; this does not bypass router governance.

## Mini Quality Suite
- prompts_attempted: `8`
- successful_responses: `8`
- timeout_fallback_count: `0`
- metadata_full_rate: `1.0`
- raw_cot_count: `0`

## Safety
- memory_mutated: `false`
- faiss_mutated: `false`
- trading_touched: `false`
- legacy_touched: `false`

## Runtime
- runtime used: `8091`
- 8090 was not touched.

## Next
`FRONT-CODEX-TO-BRAIN-EVALUATION-HARNESS-V2-01`
