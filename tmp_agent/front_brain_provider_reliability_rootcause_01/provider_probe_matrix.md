# Provider Probe Matrix

- total_calls_excluding_tags: 15
- kimi_direct_success_rate: 0.667
- brain_provider_probe_kimi_success_rate: 0.8
- brain_provider_probe_fallback_rate: 0.2
- brain_normal_route_real_llm_rate: 0.0
- brain_normal_route_dry_run_rate: 1.0
- avg_latency_by_route: {'direct_kimi': 1611.3, 'provider_probe': 4570.2, 'normal_route': 14.6, 'dashboard_chat': 2027.0}
- timeout_count: 0
- empty_response_count: 1
- fallback_count: 1
- error_types: []
- kimi_tag_visible: True

## Safety
- semantic_hash_unchanged: True
- faiss_index_hash_unchanged: True
- faiss_ids_hash_unchanged: True
- raw_cot_exposed: False
- secrets_exposed: False