# Patch Decision

- patch_applied: True
- status: PATCH_APPLIED_SAFE_ROUTE_FIX
- files_changed: ['tmp_agent/brain_v9/api/openai_compat.py', 'tmp_agent/brain_v9/core/router_entrypoint.py']
- reason: Root cause was proven in code and probes: read_only/evaluation llm_grounded_cycle was forced into dry_run. Patch adds safe llm_grounded_provider_eval route that reuses LLM-only provider_probe mechanics without requiring provider_probe metadata from caller.
- safety_properties: ['read_only required', 'evaluation required', 'tools_blocked', 'memory_writes_blocked', 'faiss_writes_blocked', 'external_side_effects_blocked', 'no canonical semantic write', 'no FAISS write']
- post_patch_metrics: {'post_patch_calls': 5, 'normal_llm_grounded_route_real_llm_rate': 1.0, 'normal_llm_grounded_route_dry_run_rate': 0.0, 'kimi_success_rate': 0.8, 'fallback_rate': 0.2, 'timeout_count': 0, 'empty_response_count': 0, 'avg_latency_ms': 6017.2}
- residual_issue: Kimi cloud intermittently returns empty response, causing transparent fallback to Codex. This is provider stability, not route semantics.