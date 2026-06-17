# FRONT-BRAIN-LLM-PROVIDER-CHAIN-OPTIMIZATION-01 Final Report

- status: `BRAIN_LLM_PROVIDER_CHAIN_OPTIMIZATION_PARTIAL_KIMI_CONFIG_MISSING`
- functional_commit: `9367f8d`
- ledger_commit: `2541b11`
- final_head: `2541b11`
- remote_head: `2541b11`

## Provider
- primary_provider: `Kimi K2.6 cloud`
- kimi_status: `CONFIG_MISSING`
- secondary_provider: `Codex`
- codex_status: `EXECUTOR_AVAILABLE_NOT_SELF_BENCHMARKED`
- tertiary_provider: `local Ollama`
- local_fallback_model: `llama3.1:8b`
- demoted: `kimi-k2.5:cloud` no queda como primary porque devolvió empty response en autonomy.

## Latency
- before direct probe: `llama3.1:8b 52.917s after Kimi fallback`
- after llama3.1:8b tiny: `29.523s`
- after llama3.1:8b short: `21.389s`
- after llama3.1:8b autonomy: `29.941s`
- legacy kimi-k2.5 tiny: `4.131s`
- legacy kimi-k2.5 autonomy: `empty_response`

## Quality
- dry_run_eval_score: `1.0`
- successful_responses: `8/8`
- timeout_fallback_count: `0`

## Safety
- memory_mutated: `false`
- faiss_mutated: `false`
- semantic_memory_lines: `1715`
- faiss_ids: `1616`
- faiss_ntotal: `1616`
- trading_touched: `false`
- raw_cot_exposed: `false`
- secrets_exposed: `false`

## Next
- `FRONT-KIMI-K2-6-CLOUD-PROVIDER-CONFIG-RUNBOOK-01`
