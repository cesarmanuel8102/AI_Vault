# Live Patched Route Validation

Metadata location: rain.

## required_exact
- http_status: 200
- route: llm_grounded_provider_eval
- dry_run: False
- provider_selected: kimi_k2_6_cloud
- model_selected: kimi-k2.6:cloud
- fallback_used: False
- fallback_reason: 
- provider_status: FAST_SUCCESS
- latency_ms: 3449
- content_non_empty: True
- content: LLM_GROUNDED_ROUTE_OK

## exact_output
- http_status: 200
- route: llm_grounded_provider_eval
- dry_run: False
- provider_selected: kimi_k2_6_cloud
- model_selected: kimi-k2.6:cloud
- fallback_used: False
- fallback_reason: 
- provider_status: FAST_SUCCESS
- latency_ms: 4041
- content_non_empty: True
- content: ROUTE_PATCH_LIVE

## cei_fdot_reasoning
- http_status: 200
- route: llm_grounded_provider_eval
- dry_run: False
- provider_selected: kimi_k2_6_cloud
- model_selected: kimi-k2.6:cloud
- fallback_used: False
- fallback_reason: 
- provider_status: FAST_SUCCESS
- latency_ms: 9822
- content_non_empty: True
- content: Requiring provenance ensures that curated knowledge used in CEI/FDOT work is traceable to its original, authoritative source, preventing costly errors, safety hazards,

## fallback_metadata
- http_status: 200
- route: llm_grounded_provider_eval
- dry_run: False
- provider_selected: 
- model_selected: 
- fallback_used: False
- fallback_reason: deepseek14b: skipped (budget exhausted, -0s left)
- provider_status: FAILED
- latency_ms: 45408
- content_non_empty: False
- content: 

## Summary
- route_ok: True
- dry_run_count: 0
- fallback_rate: 0
- raw_cot_exposed: False
- secrets_exposed: False

