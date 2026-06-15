# NEXT PROMPT RECOMMENDATION

## Current State
FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02 completed with patch.

## Verified Capability
- Kimi reliably selected first (6/6 probes)
- Stable chain order: [kimi_k2_6_cloud, codex, llama8b, deepseek14b]
- FAST_SUCCESS, avg latency ~4.4s
- No budget exhaustion, no timeouts

## Recommended Next Front
**FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-02**

## Scope
Run exactly 30 controlled real LLM-grounded autonomy cycles through Brain 8091 using the normal route after Kimi stability mitigation 02 patch.

## Prerequisites
- Brain 8091 running with patched llm.py
- safe_mode=false
- Dashboard 8092 running

## Acceptance Criteria
- 30 cycles complete
- Kimi selection rate >= 0.80
- Provider success rate >= 0.80
- Empty response rate <= 0.20
- No dry_run_count > 0
- No canonical semantic/FAISS mutation
- No trading/B8/strategies touched
- No secrets/raw CoT exposed
