# RESTART-BRAIN-8091-LOAD-PATCHED-PROVIDER-ROUTE-01

## Status
BRAIN_8091_PATCHED_PROVIDER_ROUTE_RELOAD_COMPLETED

## Runtime Reload
- old_pid: 46620
- old_command: `"C:\Users\cesar\AppData\Local\Programs\Python\Python311\python.exe" -m brain_v9.main`
- classified_as_brain_api: True
- stop_success: True
- new_pid: 50624
- restart_command: `python -u tmp_agent\brain_v9\start_safe_server.py`
- working_directory: `C:\AI_VAULT_CANONICAL`

## Patched Route
- route_ok: True
- route: `llm_grounded_provider_eval`
- dry_run: False
- provider_selected: `kimi_k2_6_cloud`
- model_selected: `kimi-k2.6:cloud`
- fallback_used: False
- fallback_rate_probe: 0
- content_non_empty_count: 3/4

Note: one additional probe returned provider_status=FAILED with empty content, but the route stayed patched and dry_run=false.

## Dashboard
- status_ok: True
- safety_ok: True

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

## Next
FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-8091-RELOAD

## Tests
- py_compile: PASS
- focused_smoke: 5 passed
