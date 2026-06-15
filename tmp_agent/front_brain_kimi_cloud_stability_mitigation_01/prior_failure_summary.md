# Prior Failure Summary
## FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-01

## Sources
- `tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_8091_reload/final_report.json`
- `tmp_agent/restart_brain_8091_load_patched_provider_route_01/final_report.json`
- `tmp_agent/front_brain_provider_reliability_rootcause_01/final_report.json`

## Key Metrics

| Metric | Value |
|--------|-------|
| cycles_completed | 15 |
| provider_success_rate | 0.533 |
| kimi_success_rate | 0.533 |
| empty_response_count | 7 |
| empty_response_rate | 0.467 |
| fallback_rate | 0.067 |
| timeout_count | 0 |
| avg_latency_ms | 28,598 |

## Declining Trend Across Batches

| Batch | Success Rate | Empty Count | Avg Latency (ms) |
|-------|-------------|-------------|------------------|
| 01 | 0.80 | 1 | 21,229 |
| 02 | 0.60 | 2 | 24,683 |
| 03 | 0.20 | 4 | 39,882 |

## Critical Discovery: Hidden safe_mode Factor

**Prior reports DID NOT mention safe_mode**, indicating this factor was overlooked. Our current investigation revealed:

- `start_safe_server.py` defaulted `BRAIN_SAFE_MODE` to `"true"`
- This forced Brain into safe mode regardless of other settings
- In safe_mode, the provider chain falls back to local `llama8b` immediately
- **Kimi was NEVER actually tested under normal conditions in prior fronts**
- The "empty responses" may have been from llama8b fallback, not Kimi

## Post-safe_mode=false Probe (Just Completed)

| Metric | safe_mode=true (prior) | safe_mode=false (current) |
|--------|----------------------|---------------------------|
| provider_selected | llama8b | kimi_k2_6_cloud |
| fallback_used | true | false |
| latency_ms | 21,891 | 6,860 |
| provider_status | SLOW_SUCCESS | FAST_SUCCESS |

**Conclusion**: The majority of prior "Kimi empty response" failures may actually have been **safe_mode-induced local fallback failures**, not genuine Kimi cloud instability.
