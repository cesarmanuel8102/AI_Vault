# B7-STRANGLER-10 — LLM Chain Select Extraction Report (Post-Fix)

## Summary

- **Head base:** ec8766bf
- **session.py before:** 5366 lines
- **session.py after:** 5325 lines
- **Net reduction:** 41 lines
- **New module:** `tmp_agent/brain_v9/core/session_llm_chain_select.py` (154 lines)
- **Symbols extracted (5):** MODEL_PRIORITY_ALIASES, normalize_model_priority, should_use_compact_chat_prompt, should_use_analysis_frontier, select_llm_chain

## _MODEL_PRIORITY_ALIASES rebind

```python
# session.py — class attribute rebind (not duplicated inline dict)
_MODEL_PRIORITY_ALIASES = _llm_chain_select.MODEL_PRIORITY_ALIASES
```

This ensures a single source of truth in the new module while preserving
BrainSession._MODEL_PRIORITY_ALIASES access for all internal and external consumers.

## Shim form

```python
# session.py
from brain_v9.core import session_llm_chain_select as _llm_chain_select

class BrainSession:
    _MODEL_PRIORITY_ALIASES = _llm_chain_select.MODEL_PRIORITY_ALIASES

    @classmethod
    def _normalize_model_priority(cls, model_priority: str) -> str:
        return _llm_chain_select.normalize_model_priority(
            model_priority, aliases=cls._MODEL_PRIORITY_ALIASES,
        )

    @classmethod
    def _should_use_compact_chat_prompt(cls, message, intent, history, model_priority):
        return _llm_chain_select.should_use_compact_chat_prompt(...)

    @classmethod
    def _should_use_analysis_frontier(cls, message, intent, history, model_priority):
        return _llm_chain_select.should_use_analysis_frontier(...)

    @classmethod
    def _select_llm_chain(cls, message, intent, history, model_priority):
        return _llm_chain_select.select_llm_chain(...)
```

All shims are AST-clean: docstring optional + single Return statement.

## Consumers preserved

- Internal: chat(), _route_to_llm(), _select_llm_chain(), _select_agent_model_priority(), _llm_status_fastpath(), _codex_role_fastpath()
- External: test_brain_chat_hygiene.py (6 assertions), test_llm_codex_integration.py (3 assertions)

## Protected paths touched

None. Tool01, fastpaths, routing core, routing/guards.py, UI, memory, strategies, main.py, config.py, execution_gate.py, api_security.py all untouched.

## Already-extracted modules touched

None. Read-only imports from session_query_predicates (B7-03) and llm (already imported in session.py).

## Validation results

| validation | result |
|------------|--------|
| Phase1 local validation | PASS |
| B7 carryover (24 files) | PASS (283 passed, 0 failed) |
| B7-10 new tests (3 files) | PASS (52 passed, 0 failed) |
| test_brain_chat_hygiene.py | BASELINE_EQUIVALENT (40 pre-existing failures) |
| test_llm_codex_integration.py | BASELINE_EQUIVALENT (8 pre-existing failures) |
| Import smoke | PASS |
| AST shim audit | PASS |
| py_compile session.py | PASS |
| py_compile new module | PASS |
| Patch reverse apply check | PASS (PATCH_REVERSES_CLEAN) |

## Patch details

- **Path:** `tmp_agent/b7_strangler_evidence/b7_10_llm_chain_select_extraction.patch`
- **Size:** ~33 KB
- **Includes untracked files:** Yes (4 new files synthesized without `git add -N`)
- **git add -N used:** No
