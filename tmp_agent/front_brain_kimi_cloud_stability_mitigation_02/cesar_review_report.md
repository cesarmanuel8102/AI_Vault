# Cesar Review — FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02

## 1. Why the 30-cycle retry failed
The prior retry (FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-01) stopped at Phase 3 preflight because only 1/3 probes selected kimi_k2_6_cloud. Root cause was chain order reversal: during cooldown, llm.py moved codex to position 0 and kimi to position 3. Codex's 120s timeout consumed the 90s total budget, so kimi was skipped with "budget exhausted".

## 2. Why safe_mode=false was not sufficient
safe_mode=false fixed warmup/cold-model issues, but did not address the dynamic chain reordering logic. Reorder is independent of safe_mode.

## 3. Whether Kimi itself works directly
Yes. When kimi is first in the chain, all 6 post-patch probes succeeded with FAST_SUCCESS and latencies 2-8s.

## 4. Why provider chain order changed
`llm.py:356-386` separates providers by type (ollama vs non-ollama). During cooldown, non-ollama providers are placed first. Since kimi_k2_6_cloud is type=ollama and codex is type=codex_cli, codex moves to position 0.

## 5. Whether chain budget is per request
Yes. `max_time=90` is shared across all providers in the chain.

## 6. Whether patch was applied
Yes. Small patch in `llm.py:379-386` preserves primary provider at position 0 during forced reorder.

## 7. Post-patch probe results
- 6 probes
- Kimi selected: 6/6 (100%)
- Chain order: stable `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]`
- Status: FAST_SUCCESS on all
- Avg latency: ~4.4s
- No budget exhaustion, no timeouts, no empty responses

## 8. Semantic/FAISS safety
- Unchanged. 1715/1616.

## 9. Exact commits (pending)
- `fix: preserve primary provider order during chain cooldown reorder in llm.py`

## 10. Next recommended front
FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-02
