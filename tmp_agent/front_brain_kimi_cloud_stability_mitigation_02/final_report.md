# FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02 — Final Report

## Status
**BRAIN_KIMI_CLOUD_STABILITY_MITIGATION_02_COMPLETED_WITH_PATCH**

## Objective
Diagnose and patch provider chain ordering, timeout, and budget behavior so that LLM-grounded read_only/evaluation cycles reliably try Kimi first.

## Root Cause
**PROVIDER_CHAIN_ORDER_REVERSAL**
- Location: `llm.py:356-386`
- During chain cooldown, pre-flight context routing separates providers by type (ollama vs non-ollama) and sorts them.
- `kimi_k2_6_cloud` (type=ollama) was moved to position 3; `codex` (type=codex_cli) moved to position 0.
- With 90s total budget, codex's 120s timeout consumed the entire budget before kimi was reached.

## Patch Applied
- **File**: `tmp_agent/brain_v9/core/llm.py`
- **Lines**: 379-386
- **Logic**: After forced reorder, preserve primary provider (`kimi_k2_6_cloud`) at position 0 if it was displaced.
- **Risk**: Minimal — only activates during `_force_reorder=True` (chain cooldown).

## Post-Patch Results (6 probes)
- Kimi selected: **6/6 = 100%**
- Chain order: **Stable** `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]` on all probes
- Provider status: **FAST_SUCCESS** on all probes
- Latency range: **2.1s – 7.9s**
- Avg latency: **~4.4s**
- Empty responses: 0
- Budget exhaustion: 0
- Fallback used: 0
- Dry runs: 0

## Safety
- Semantic lines: 1715 (unchanged)
- FAISS IDs: 1616 (unchanged)
- No canonical mutation
- No trading/B8/strategies/secrets/CoT

## Next Recommended Front
**FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-02**
- Now that Kimi is reliably selected first, attempt the 30 controlled LLM-grounded autonomy cycles again.
