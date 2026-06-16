# Brain Agent Finalizer V2

Agent V2 final synthesis uses `kimi-k2.6:cloud` through local Ollama Cloud (`/api/chat`) with `think:false`. The runtime records `provider_attempted`, `provider_used`, `model_used`, `provider_degraded`, `fallback_reason`, and `latency_ms`. If Kimi fails or returns empty content, fallback is explicit and never hidden. Raw chain-of-thought is not requested, read, logged, or displayed.
