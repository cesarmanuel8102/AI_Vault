# Phase 2 — Code Path Audit

## Files Audited
- `tmp_agent/brain_v9/core/llm.py`
- `tmp_agent/brain_v9/core/router_entrypoint.py`
- `tmp_agent/brain_v9/core/session.py`

## Provider Chain Construction
- Defined in `llm.py:46-67` as `CHAINS` dictionary
- Default "chat"/"ollama" chain: `[kimi_k2_6_cloud, codex, llama8b, deepseek14b]`

## Why Chain Order Changed
The reorder happens in `llm.py:356-386`:
```python
_force_reorder = self._chain_in_cooldown(model_priority)
if (_est > 4500 or _force_reorder) and len(chain) > 1:
    others = [m for m in mutable_chain if MODELS.get(m, {}).get("type") != "ollama"]
    ollamas = [m for m in mutable_chain if MODELS.get(m, {}).get("type") == "ollama"]
    new_chain = others + ollamas_sorted
```

- `kimi_k2_6_cloud` has type `"ollama"` → goes into `ollamas`
- `codex` has type `"codex_cli"` → goes into `others`
- Result: `new_chain = [codex, ...] + [kimi_k2_6_cloud, ...]`

`_force_reorder` is true when chain failure rate > 5% over last 100 queries (`_CHAIN_FAIL_RATE_THRESHOLD = 0.05`, `_CHAIN_HEALTH_WINDOW = 100`).

## Budget Logic
- Total budget: `BRAIN_CHAT_LLM_TIMEOUT=90` seconds (from `session.py`)
- `llm.py:420-437`: Each provider is skipped if `remaining < min_provider_budget (8s)`
- When codex (timeout=120) is first, it can consume the entire 90s budget on timeout
- Subsequent providers (including kimi) are skipped with "budget exhausted"

## Same-Provider Retry
- **None exists.** The loop iterates `for idx, model_key in enumerate(chain)` once per provider.
- No retry mechanism for transient timeouts.

## Can Safe Eval Force Kimi-First?
- Currently NO. `llm.py` does not receive metadata flags.
- Patch option: preserve `kimi_k2_6_cloud` at position 0 during reorder, or pass metadata flags through the call chain.

## Critical Code Locations
| Concept | File | Lines |
|---------|------|-------|
| Chain definition | llm.py | 46-67 |
| Reorder logic | llm.py | 356-386 |
| Budget skip | llm.py | 420-437 |
| Chain cooldown | llm.py | 152-161 |
| Session timeout | session.py | ~2596 |
