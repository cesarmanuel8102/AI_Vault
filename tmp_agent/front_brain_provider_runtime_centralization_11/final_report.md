# FRONT_BRAIN_PROVIDER_RUNTIME_CENTRALIZATION_11

Status: COMPLETE

Scope:
- Removed Agent V2 runtime hardcoded Ollama endpoint fallback literals from finalizer, intent classifier, intent adapter, and capability registry.
- Runtime calls now use centralized `API_ENDPOINTS["ollama"]` from `brain_v9.config`.
- Kimi policy remains unchanged: Kimi K2.6 cloud through Ollama Cloud is still the primary provider path.

Validation:
- py_compile: PASS.
- provider/agent focal regression: 14 passed, 3 warnings.

Safety:
- no real money
- no broker/IBKR
- no memory/semantic mutation
- no FAISS mutation
