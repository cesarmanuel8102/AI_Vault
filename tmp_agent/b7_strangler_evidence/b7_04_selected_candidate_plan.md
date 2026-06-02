# B7-STRANGLER-04 — Selected Candidate Plan (for B7-STRANGLER-04-IMPLEMENT)

## Selected: **C1 — Routing regex constants module**

**New module:** `tmp_agent/brain_v9/core/session_routing_constants.py`

### Symbols to move (from session.py)
| Symbol | Current lines | Kind |
|--------|--------------|------|
| `AGENT_INTENTS` | 105 | `set[str]` |
| `AGENT_KEYWORDS` | 109-190 | `list[str]` |
| `_AGENT_PATTERNS` | 193 | `list[re.Pattern]` (derived from `AGENT_KEYWORDS`) |
| `_CODE_ANALYSIS_PATH_RE` | 195-199 | `re.Pattern` |
| `_LEAK_TAIL_RE` | 202-206 | `re.Pattern` |
| `_CONTINUE_WORDS_RE` | 212-216 | `re.Pattern` |
| `_CORRECTION_RE` | 221-236 | `re.Pattern` |

### Symbols intentionally KEPT in session.py
- `log` (line 90) — module-scoped logger.
- `_PROCESS_START_TIME` (line 211) — semantic anchor must remain at session.py module-load time.
- All path constants (`_STATE_PATH`, `_UI_*`, `_CHAT_METRICS_PATH`, `_CHAT_SESSION_DEFAULTS_PATH`, `_EPISODIC_MEMORY_PATH`, `_CAPABILITY_GOVERNOR_STATUS_PATH`) — multiple tests monkeypatch them on `session_mod`.
- `SLASH_COMMANDS` — separate concern (deferred to a future ticket).

### Re-export shim in session.py (B7-03 mirror)
Replace the seven extracted definitions with:

```python
from brain_v9.core.session_routing_constants import (  # noqa: F401  (B7-STRANGLER-04 re-export)
    AGENT_INTENTS,
    AGENT_KEYWORDS,
    _AGENT_PATTERNS,
    _CODE_ANALYSIS_PATH_RE,
    _LEAK_TAIL_RE,
    _CONTINUE_WORDS_RE,
    _CORRECTION_RE,
)
```

Estimated session.py reduction: **−95 lines** → projected post-B7-04 size **≈5830 lines** (cumulative −1807 since pre-B7-02).

## Tests recommended

1. `tests/unit/test_b7_routing_constants_import_compat.py`
   - Asserts importability from both `brain_v9.core.session` and `brain_v9.core.session_routing_constants`, with identity (`is`) check across the seven names.
2. `tests/unit/test_b7_routing_constants_behavior_smoke.py`
   - Pins regex semantics: representative match/no-match snapshots for each of the five `re.Pattern`s plus a single agent-keyword match through `_AGENT_PATTERNS`.
3. `tests/unit/test_b7_routing_constants_no_session_dependency.py`
   - Mirrors `test_b7_query_predicates_no_session_dependency.py`. Loads `session_routing_constants` in a fresh context and asserts `brain_v9.core.session` is NOT pulled into `sys.modules`.

## Validations to run during the IMPLEMENT ticket

- `phase1_local_validation.ps1`
- `tests/unit/test_phase1_import_baseline.py`
- `tests/unit/test_phase1_security_defaults.py`
- B7-02 ChatMetrics tests
- B7-03 query-predicate tests
- New B7-04 tests
- `tmp_agent/tests/core/test_session.py` (external consumer)
- `tests/unit/test_brain_chat_hygiene.py` (`session_mod._AGENT_PATTERNS`)
- `tests/unit/test_b7_routing_heuristics_characterization.py` (`session_mod.AGENT_KEYWORDS`)
- `tmp_agent/debug_routing.py` import smoke

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| External imports of `_AGENT_PATTERNS` / `AGENT_KEYWORDS` from session | Re-export shim verified by import-compat test |
| `session_mod._AGENT_PATTERNS` dynamic read by hygiene test | Re-export creates module-level binding to the same object |
| Circular import | New module imports only `re`/typing; explicit `no_session_dependency` test |
| Pattern semantics drift | Behavior smoke test pins `.search()`/`.match()` outputs |
| Accidentally moving `_PROCESS_START_TIME` (would shift uptime anchor) | Explicitly excluded; documented in plan |

## Rollback

Single-commit revert restores session.py and removes `session_routing_constants.py`. If non-trivial, manually restore the original block and delete the new module + new tests.

## Out of scope for B7-04-IMPLEMENT

- C2 `_fmt_*` bundle, C3 `SLASH_COMMANDS`, C4 `_render_*`/`_format_*`, C5 `_sanitize_llm_chat_response`, C6 path constants, C7 Tool01.
