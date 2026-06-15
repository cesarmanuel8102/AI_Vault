# FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-8091-RELOAD

## Status
FAILED_PROVIDER_STABILITY_GATE

## Summary
- cycles_completed: 15
- batches_completed: 3
- stop_reason: `provider_success_rate_below_0_60_after_10_cycles`
- normal_route_used: true
- provider_probe_used_for_cycles: false
- dry_run_count: 0
- provider_success_rate: 0.533
- kimi_success_rate: 0.533
- fallback_rate: 0.067
- empty_response_count: 7
- avg_latency_ms: 28598.3
- avg_quality_score: 0.65

## Learning
- lessons_created: 7
- mistakes_recorded: 7
- promotion_candidates_created: 7
- semantic_staging_count: 7
- canonical_promotions: 0

## Safety
- semantic_lines: 1715 -> 1715
- faiss_ids: 1616 -> 1616
- faiss_ntotal: 1616 -> 1616
- canonical_semantic_mutated: False
- faiss_mutated: False
- trading_touched: False
- b8_touched: False
- secrets_exposed: False
- raw_cot_exposed: False

## Interpretation
The patched live route worked: no cycle returned `diagnostic_dry_run`. The front stopped because provider success degraded under repeated real calls: 8/15 cycles had provider-selected non-empty content, with 7 empty responses.

## Next
FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-01

## Tests
- py_compile: PASS
- focused_smoke: 6 passed
