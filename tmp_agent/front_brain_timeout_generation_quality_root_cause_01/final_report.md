# FRONT-BRAIN-TIMEOUT-GENERATION-QUALITY-ROOT-CAUSE-01

- status: `ROOT_CAUSE_DIAGNOSED_READ_ONLY`
- primary_root_cause: `BRAIN_CHAT_LLM_TIMEOUT default/effective budget is 30s, but LLMManager model chain entries require nominal timeouts from 60s to 120s; budget-aware skip rejects every model before generation.`
- secondary_root_cause: `Direct Ollama qwen2.5-coder:14b generation timed out after 75s for a 32-token probe, so raising Brain timeout alone may still produce poor latency unless model/provider path is changed or warmed.`
- runtime_8091_active: `True`
- brain_probe_summary: `[{'name': 'short', 'latency_ms': 63913.79, 'fallback_detected': False, 'route': 'agent'}, {'name': 'medium', 'latency_ms': 84.01, 'fallback_detected': True, 'route': 'llm'}, {'name': 'fastpath', 'latency_ms': 15.05, 'fallback_detected': False, 'route': 'brain_session_governed_chat'}]`
- recommended_fix: `Implement a guarded quality fix: raise budget only where it can work, add short-prompt low-latency route or model lane, and keep fallback classified as non-success.`
- recommended_next_front: `FRONT-BRAIN-TIMEOUT-GENERATION-QUALITY-FIX-01`
- memory_mutated: `True`
- faiss_mutated: `False`
- staged_empty: `True`
- tracked_unstaged_empty: `False`
- commit_created: `False`
- push_done: `False`