# Phase 4 — Root Cause Classification

## Confirmed Root Causes

### 1. PROVIDER_CHAIN_ORDER_REVERSAL (CRITICAL)
- **Location**: `llm.py:356-386`
- **Cause**: Pre-flight context routing separates non-ollama and ollama providers, then concatenates `others + ollamas_sorted`. Since `kimi_k2_6_cloud` is type `ollama` and `codex` is type `codex_cli`, codex moves to front and kimi to back.
- **Trigger**: `_chain_in_cooldown()` returns true when chain failure rate > 5% over last 100 queries.
- **Impact**: Even with `safe_mode=false`, the reordered chain places kimi LAST, causing budget exhaustion before reaching it.

### 2. PROVIDER_CHAIN_BUDGET_EXHAUSTION (CRITICAL)
- **Location**: `llm.py:420-437`
- **Cause**: Total request budget = 90s (from `BRAIN_CHAT_LLM_TIMEOUT`). Budget is shared across all providers. When chain is `[codex, llama8b, deepseek14b, kimi]`, codex and local models consume budget before kimi is reached.
- **Impact**: kimi is skipped with `remaining < min_provider_budget (8s)`.

### 3. SAME_PROVIDER_RETRY_MISSING (HIGH)
- **Location**: `llm.py:399-563`
- **Cause**: Loop iterates `for idx, model_key in enumerate(chain)` once per provider. No retry on timeout or empty response.
- **Impact**: Transient Kimi failures permanently lose the provider for that request.

### 4. COOLDOWN_SIDE_EFFECT_GLOBAL (HIGH)
- **Location**: `llm.py:152-161, 362`
- **Cause**: `_chain_in_cooldown` forces reorder for ALL queries on the chain when failure rate > 5%, not just for slow queries.
- **Impact**: Even fast queries get reordered chain, degrading reliability globally.

## Ruled Out
- ROUTE_REGRESSION — route remained `llm_grounded_provider_eval`
- PROVIDER_PROBE_DEPENDENCY — no `provider_probe:true` used
- SAFE_MODE_WARMUP — already fixed in prior front
- CANONICAL_MEMORY_MUTATION — not touched
- TRADING_B8_TOUCH — not touched
