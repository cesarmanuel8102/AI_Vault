# Provider Stability Root Cause

Status: FAILED_PROVIDER_STABILITY_GATE

The normal 8091 route returned a dry-run canonical router response and did not expose provider metadata. The safe real-provider route required `metadata.provider_probe=true`.

With provider_probe enabled, 10 real LLM-grounded cycles ran before the stop gate:

- provider_success_rate: 1.0
- fallback_rate: 0.8
- timeout_count: 0
- empty_response_count: 0
- primary provider initially: kimi_k2_6_cloud
- fallback provider observed: codex
- stop reason: fallback_rate > 0.50 after 10 cycles

Interpretation: reasoning quality was high, but Kimi/provider stability was not clean enough to continue toward 30 cycles under this prompt's governance gates. Next front should root-cause provider reliability before more LLM-grounded cycles or memory promotion audit.
