# NEXT PROMPT RECOMMENDATION

## Current Blocker
Provider chain budget exhaustion after intermittent Kimi timeouts, combined with dynamic chain order reversal, prevents reliable LLM-grounded autonomy cycles.

## Key New Finding
Provider chain order is NOT static:
- Probe 1 order: `[kimi, codex, llama8b, deepseek14b]` → succeeded
- Probe 2/3 order: `[codex, llama8b, deepseek14b, kimi]` → failed (budget exhausted before reaching kimi)

This suggests the chain algorithm dynamically reorders based on prior success/failure or budget state. When Kimi moves to the end of the chain, a timeout on early providers exhausts budget before reaching Kimi.

## Recommended Next Front
**FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02**

## Scope
1. Audit provider chain construction logic in `tmp_agent/brain_v9/core/llm.py` and/or `router_entrypoint.py`.
2. Identify what causes chain order to flip.
3. Determine if budget is per-request, per-session, or per-chain.
4. Evaluate if chain order can be made deterministic (Kimi always first for cloud-enabled queries).
5. Test adjusted parameters with 3 preflight probes.
6. Acceptance: 3/3 probes select Kimi, latency < 15s, no budget exhaustion, consistent chain order.

## Proposed Prompt Template
```
KIMI K2.6 OPENCODE PROMPT — FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02

Objectives:
1. Audit provider chain construction and ordering logic.
2. Fix chain order determinism for cloud provider queries.
3. Tune chain budget or timeout thresholds.
4. Verify with 3 preflight probes.
5. If successful, unblock FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY.

Hard prohibitions: [same list]
```

## Alternative
If chain order cannot be made static, increase per-chain budget or reduce timeout to 15s with immediate retry at position 1 instead of advancing chain.
