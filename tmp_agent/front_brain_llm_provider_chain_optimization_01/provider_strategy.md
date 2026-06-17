# Provider Strategy

- status: `BRAIN_LLM_PROVIDER_CHAIN_OPTIMIZATION_PARTIAL_KIMI_CONFIG_MISSING`
- chain: `Kimi K2.6 cloud -> Codex -> local Ollama`
- Kimi K2.6: `CONFIG_MISSING`
- Codex: `EXECUTOR_AVAILABLE_NOT_SELF_BENCHMARKED`
- local fallback: `llama3.1:8b`
- demoted: `kimi-k2.5:cloud` is not primary because autonomy probe returned empty.
- empty response policy: failure, continue chain.
- budget policy: cap effective timeout instead of skipping solely on nominal timeout.
