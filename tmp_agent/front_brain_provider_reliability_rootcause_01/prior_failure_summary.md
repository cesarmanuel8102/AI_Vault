# Prior Failure Summary

- normal_8091_route_behavior: Normal 8091 route returned dry-run canonical router; provider_probe:true was required to reach real provider responses.
- provider_probe_route_behavior: provider_probe:true reached real provider chain with provider metadata.
- kimi_success_count: 2
- fallback_count: 8
- timeout_count: 0
- empty_response_count: 0
- latency_distribution_ms: {'min': 6536, 'max': 28803, 'avg': 16581.5, 'median': 16422.0}
- provider_model_metadata_observed: [('codex', 'gpt-5.5'), ('kimi_k2_6_cloud', 'kimi-k2.6:cloud')]
- stop_reason: fallback_rate_above_0_50_after_10_cycles
- provider_success_rate: 1.0
- fallback_rate: 0.8