# FRONT-BRAIN-KIMI-CLOUD-STABILITY-MITIGATION-02 — Patch Source Verify

- **Patch File**: tmp_agent/brain_v9/core/llm.py
- **Patch Lines**: 379-386
- **Patch Present**: YES

## Patch Logic
```python
# Preserve primary provider at position 0 during cooldown reorder.
# Prevents budget exhaustion by keeping kimi first so fallback
# happens only after kimi is attempted, not before it.
if _force_reorder and new_chain != list(chain):
    primary = PROVIDER_PRIORITY.get("primary_provider")
    if primary and primary in new_chain and primary not in others[:1]:
        new_chain = [primary] + [m for m in new_chain if m != primary]
```

## Safety Checks
- **Touches trading/**: NO
- **Touches B8/**: NO
- **Touches memory/semantic/**: NO
- **Touches FAISS**: NO
- **Touches tmp_agent/strategies/**: NO
- **Bypasses governance**: NO
- **Exposes raw CoT**: NO
- **Only activates during**: `_force_reorder=True` (chain cooldown)

## Verdict
PATCH_VERIFIED_PRESENT_AND_SAFE
