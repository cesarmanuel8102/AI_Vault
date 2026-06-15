# Phase 3 — Kimi Route Preflight (FAILED)

## Front
FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-01

## Probes Summary
| # | Prompt | Latency | Provider | Status | Empty | Budget Issue |
|---|--------|---------|----------|--------|-------|--------------|
| 1 | Return exactly KIMI_MITIGATION_ROUTE_OK | 45,062ms | null | FAILED | Yes | deepseek14b: budget exhausted |
| 2 | Explain safe_mode=false | 45,047ms | null | FAILED | Yes | deepseek14b: budget exhausted |
| 3 | Return exactly KIMI_FAST_SUCCESS_CHECK | 2,469ms | kimi_k2_6_cloud | FAST_SUCCESS | No | None |

## Key Metrics
- Kimi selection rate: 1/3 = 33.3%
- Provider selected present: 1/3 = 33.3%
- Empty response rate: 2/3 = 66.7%
- Average latency: ~30.9s (skewed by timeouts)

## Diagnosis
**Root cause: PROVIDER_CHAIN_BUDGET_EXHAUSTION_AFTER_TIMEOUT**

1. Probes 1 & 2 hit ~45s latency — consistent with Kimi timeout threshold.
2. Kimi timeout causes chain to advance: codex → llama8b → deepseek14b.
3. Chain budget (per-session cumulative time allowance) is exhausted by the time deepseek14b is reached.
4. Result: `provider_selected=null`, `fallback_reason="budget exhausted"`.
5. Probe 3 succeeds in ~2.5s with Kimi FAST_SUCCESS, proving Kimi is intermittently available, not permanently broken.

## Implication
- `safe_mode=false` patch fixed warmup/cold-model issues.
- **New blocker**: Provider chain has no same-provider retry and a tight cumulative budget. A single Kimi timeout exhausts the entire chain.
- Running 30 cycles would result in high failure rate and meaningless data.

## Decision
STOP with `FAILED_KIMI_NOT_SELECTED_PREFLIGHT`.

## Recommended Next Front
FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02 — tune provider chain budget/timeout and add same-provider retry for transient timeouts.
