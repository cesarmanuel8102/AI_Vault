# Phase 5 — Patch Decision

## Patch Applied: Yes

### Patch Type
**Deterministic Kimi-First Chain during Cooldown Reorder**

### Files Changed
- `tmp_agent/brain_v9/core/llm.py` (lines 379-386)

### What Changed
Added block after `new_chain = others + ollamas_sorted`:
```python
# Preserve primary provider at position 0 during cooldown reorder.
if _force_reorder and new_chain != list(chain):
    primary = PROVIDER_PRIORITY.get("primary_provider")
    if primary and primary in new_chain and primary not in others[:1]:
        new_chain = [primary] + [m for m in new_chain if m != primary]
```

### Why
- Chain cooldown reorder was moving `codex` (non-ollama) to position 0 and `kimi_k2_6_cloud` (ollama) to position 3.
- With 90s total budget, codex's 120s timeout consumed the entire budget before kimi was reached.
- Result: kimi never got a chance; all providers after codex were skipped with "budget exhausted".

### Impact
- All 6 post-patch probes: kimi selected FIRST, FAST_SUCCESS, stable latency 2-8s.
- Chain order is now stable: `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]`.
- Minimal risk: only activates during `_force_reorder=True` (chain cooldown).

### Not Applied
- Same-provider retry: deemed unnecessary since primary-first ordering eliminates budget exhaustion.
- Timeout/budget policy: kept at 90s total with per-provider timeouts; reorder fix makes budget sufficient.
