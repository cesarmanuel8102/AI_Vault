# FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-01 — Preflight

## Result: PASS

## Environment
- HEAD: `51a8c9c976af6728bb98236fa6a6e1e19c2e4aae`
- Remote: `51a8c9c976af6728bb98236fa6a6e1e19c2e4aae`
- Branch: `codex/own-capital-sustainable-return`
- Tracked diff: clean
- Staged changes: none

## Services
- Dashboard 8092: responding (status OK, safety OK)
- Brain API 8091: healthy (sessions=1, version=9.0.0, safe_mode=true)
- Brain Models 8091: responding

## Normal Route Probe
- HTTP 200: yes
- Route: `llm_grounded_provider_eval` (correct patched route)
- dry_run: false
- provider_selected: llama8b (local fallback)
- model_selected: llama3.1:8b
- fallback_used: true
- fallback_reason: provider_chain_fallback
- provider_status: SLOW_SUCCESS
- latency_ms: ~21,891
- provider_probe: true (internally set, not explicitly requested)
- content_correct: KIMI_STABILITY_PREFLIGHT_OK
- no_cot_leak: true

## Baselines
- Semantic lines: 1715
- FAISS IDs: 1616
- FAISS ntotal: 1715
- Semantic hash: ab4f62ce37543839
- FAISS index hash: b6ae2ff7d4318a20
- FAISS IDs hash: 43736047db548caf
- Journal count: 349 (scheduler has been running autonomously)

## Observations
- Brain is in safe_mode=true (new since previous session; may affect provider chain)
- Provider chain: [codex, llama8b, deepseek14b, kimi_k2_6_cloud]
- Kimi was NOT selected in this probe (llama8b fallback succeeded)
- No route regression to dry_run detected
- All canonical files unchanged

## Next: Phase 1 — Read prior failure evidence
