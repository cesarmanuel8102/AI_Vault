# Prior State Summary

- provider_route_patch_status: BRAIN_PROVIDER_RELIABILITY_ROOTCAUSE_COMPLETED_WITH_PATCH
- patch_applied: 
- 8091_reload_status: BRAIN_8091_PATCHED_PROVIDER_ROUTE_RELOAD_COMPLETED
- live_route: llm_grounded_provider_eval
- live_dry_run: False
- live_provider: kimi_k2_6_cloud
- residual_kimi_instability: 
- semantic_lines_baseline: 1715
- faiss_ids_baseline: 1616
- faiss_ntotal_baseline: 1616

## Stop Gates
- dry_run_count > 0
- fallback_rate > 0.50 after 10 cycles
- provider_success_rate < 0.60 after 10 cycles
- timeout/empty rate > 0.30 after 10 cycles
- dashboard failure twice
- semantic/FAISS mutation
- raw CoT/secrets/trading/B8/strategies touched
