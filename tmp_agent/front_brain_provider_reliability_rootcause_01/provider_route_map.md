# Provider Route Map

- normal_route_dry_run_cause: tmp_agent/brain_v9/api/openai_compat.py::_request_dry_run returns true when metadata.read_only or metadata.evaluation is true unless metadata.provider_probe is true.
- provider_probe_real_provider_cause: openai_compat passes provider_probe context to router_entrypoint.handle_user_message; router_entrypoint.select_route returns provider_probe and delegates to BrainSession.provider_probe, which calls LLMManager.query.
- provider_probe_intended_only_for_diagnostics: True
- recommended_route_for_llm_grounded_cycles: A dedicated read-only/evaluation LLM route should reach BrainSession.provider_probe-like provider chain without requiring diagnostic provider_probe semantics.
- fallback_decision_location: tmp_agent/brain_v9/core/llm.py::LLMManager.query. Fallback is idx > 0 in provider chain; exceptions/empty responses/circuit breaker/policy skips advance to next model.
- fallback_after_kimi_initial_success_hypotheses: ['Kimi direct/cloud intermittent empty/slow responses', 'circuit breaker/cooldown or ctx routing reorders/skips', 'provider_probe timeout budget caps Kimi attempts']
- kimi_timeout_seconds: 75
- provider_probe_timeout_seconds: BRAIN_PROVIDER_PROBE_TIMEOUT default 45
- metadata_fields_reliable_when_provider_probe: True
- metadata_fields_missing_in_normal_dry_run: True
- inspected_files: ['tmp_agent/brain_v9/api/openai_compat.py', 'tmp_agent/brain_v9/core/router_entrypoint.py', 'tmp_agent/brain_v9/core/session.py', 'tmp_agent/brain_v9/core/llm.py']