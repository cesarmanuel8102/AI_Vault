# Phase 3 — Kimi Route Preflight (FAILED)

## Front
FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-01

## Probes Summary
| # | Prompt | Latency | Provider | Status | Empty | Budget Issue |
|---|--------|---------|----------|--------|-------|--------------|
| 1 | Return exactly KIMI_MITIGATION_ROUTE_OK | 8,484ms | kimi_k2_6_cloud | FAST_SUCCESS | No | None |
| 2 | Explain safe_mode=false | 45,281ms | null | FAILED | Yes | kimi_k2_6_cloud: budget exhausted |
| 3 | Return exactly KIMI_FAST_SUCCESS_CHECK | 45,265ms | null | FAILED | Yes | kimi_k2_6_cloud: budget exhausted |

## Key Metrics
- Kimi selection rate: 1/3 = 33.3%
- Provider selected present: 1/3 = 33.3%
- Empty response rate: 2/3 = 66.7%
- Average latency: ~33.0s (skewed by timeouts)

## Diagnosis
**Root cause: PROVIDER_CHAIN_BUDGET_EXHAUSTION_AFTER_TIMEOUT**

1. Probe 1 succeeds in ~8.5s with Kimi FAST_SUCCESS, proving Kimi is intermittently available.
2. Probes 2 & 3 hit ~45s latency — consistent with Kimi timeout threshold.
3. Kimi timeout causes chain to advance through codex -> llama8b -> deepseek14b -> kimi_k2_6_cloud.
4. Chain budget is exhausted by the time any fallback is reached.
5. Result: `provider_selected=null`, `fallback_reason="budget exhausted"`.

## Critical Observation
Provider chain order CHANGED between probe 1 and probes 2/3:
- Probe 1: `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]`
- Probes 2/3: `[codex, llama8b, deepseek14b, kimi_k2_6_cloud]`

This suggests dynamic chain reordering or different routing logic based on prior state.

## Implication
- `safe_mode=false` patch fixed warmup/cold-model issues.
- **New blocker**: Provider chain has no same-provider retry and a tight cumulative budget. Intermittent Kimi timeouts exhaust the entire chain.
- Running 30 cycles would result in high failure rate and meaningless data.

## Decision
STOP with `FAILED_KIMI_NOT_SELECTED_PREFLIGHT`.

## Recommended Next Front
**FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02**
- Focus: provider chain budget tuning, same-provider retry, or timeout reduction.
- Acceptance: 3/3 preflight probes select Kimi, latency < 15s, no budget exhaustion.
