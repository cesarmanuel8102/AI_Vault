# Root Cause Classification

- classification: ['ROUTE_SEMANTICS_BUG', 'DRY_RUN_GUARD_OVERMATCH', 'KIMI_CLOUD_INSTABILITY']
- primary_cause: ROUTE_SEMANTICS_BUG / DRY_RUN_GUARD_OVERMATCH
- secondary_cause: KIMI_CLOUD_INSTABILITY: direct Kimi had 1/3 empty response; Brain provider_probe had 1/5 fallback; post-patch had 1/5 fallback.
- normal_route_behavior: Before patch: read_only/evaluation metadata forced dry_run in openai_compat, so normal llm_grounded_cycle returned canonical dry-run router, not LLM.
- provider_probe_behavior: Reached real provider through BrainSession.provider_probe, with tools/memory/FAISS blocked.
- kimi_direct_success_rate: 0.667
- brain_provider_probe_kimi_success_rate: 0.8
- brain_provider_probe_fallback_rate: 0.2
- normal_route_real_llm_rate_before: 0.0
- normal_route_dry_run_rate_before: 1.0
- normal_route_real_llm_rate_after: 1.0
- normal_route_dry_run_rate_after: 0.0
- timeout_count: 0
- empty_response_count: 1
- metadata_propagation_bug: False
- dashboard_proxy_limitation: Dashboard chat not used as canonical LLM-grounded cycle path; limited to UI/proxy checks.