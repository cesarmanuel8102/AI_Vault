# Phase 1 — Prior Failure Summary

## Context
Front: FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-01

## Prior Kimi Mitigation 01 Results
- safe_mode=false: confirmed active
- Post-mitigation probes: 5/5 selected kimi_k2_6_cloud with FAST_SUCCESS
- 0 empty responses, 0 fallbacks
- Latency: 2.6-7s

## Latest Retry Preflight Results (3 probes)
- Probe 1: kimi_k2_6_cloud selected, FAST_SUCCESS, ~8.5s, content OK
- Probe 2: provider=null, FAILED, ~45s, empty response, budget exhausted
- Probe 3: provider=null, FAILED, ~45s, empty response, budget exhausted

## Critical Observations
1. **Provider chain order CHANGED between probes:**
   - Probe 1 chain: `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]`
   - Probe 2/3 chain: `[codex, llama8b, deepseek14b, kimi_k2_6_cloud]`
   - kimi_k2_6_cloud moved from position 0 to position 3
   - codex moved from position 1 to position 0

2. **Budget exhaustion:**
   - When codex is first and has 120s timeout, it times out and exhausts the 90s total budget
   - By the time the chain reaches kimi_k2_6_cloud (position 3), budget is -0s
   - No actual fallback occurred — all providers after codex were skipped due to budget

3. **Kimi is intermittently available:**
   - Probe 1 proved kimi CAN succeed when it's tried first with sufficient budget
   - Probes 2/3 prove kimi FAILS when placed at the end after budget exhaustion

## Root Cause Hypothesis
- **PROVIDER_CHAIN_ORDER_REVERSAL**: `llm.py` pre-flight context routing logic reorders the chain when in cooldown, moving non-ollama providers (codex) before ollama providers (kimi_k2_6_cloud).
- **PROVIDER_CHAIN_BUDGET_EXHAUSTION**: The 90s shared budget is consumed by the first provider's timeout, leaving no budget for subsequent providers.

## Stop Reason
FAILED_KIMI_NOT_SELECTED_PREFLIGHT: provider_selected missing in 2/3 probes. Budget exhaustion after timeout.
