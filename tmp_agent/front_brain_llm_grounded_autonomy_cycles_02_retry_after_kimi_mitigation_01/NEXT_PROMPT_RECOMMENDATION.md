# NEXT PROMPT RECOMMENDATION

## Current Blocker
Provider chain budget exhaustion after intermittent Kimi timeouts prevents reliable LLM-grounded autonomy cycles.

## Recommended Next Front
**FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02**

## Scope
1. Audit provider chain budget calculation in `tmp_agent/brain_v9/core/llm.py` and/or `router_entrypoint.py`.
2. Identify timeout threshold and budget allocation per provider.
3. Determine whether budget is per-request, per-session, or per-chain.
4. Evaluate feasibility of same-provider retry (1 retry) before advancing chain.
5. Test adjusted parameters with 3 preflight probes.
6. Acceptance: 3/3 probes select Kimi, latency < 15s, no budget exhaustion.

## Proposed Prompt Template
```
KIMI K2.6 OPENCODE PROMPT — FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02

Objectives:
1. Audit provider chain budget/timeout logic.
2. Add same-provider retry for transient Kimi timeouts.
3. Verify with 3 preflight probes.
4. If successful, unblock FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY.

Hard prohibitions: [same list]
```

## Alternative if Retry Not Feasible
Increase per-chain budget or reduce Kimi timeout to 15s with immediate local fallback for speed-critical paths.
