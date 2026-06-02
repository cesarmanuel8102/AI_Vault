# B7-STRANGLER-04 Routing Constants Extraction Report

## Status
**SUCCESS** — 7 routing constants extracted from `tmp_agent/brain_v9/core/session.py` into a new module `tmp_agent/brain_v9/core/session_routing_constants.py`. Full backward compatibility preserved via re-export shim.

## Symbols extracted (7)
| Name | Type |
|---|---|
| `AGENT_INTENTS` | `set[str]` |
| `AGENT_KEYWORDS` | `list[str]` (~120 regex sources) |
| `_AGENT_PATTERNS` | `list[re.Pattern]` (pre-compiled, IGNORECASE) |
| `_CODE_ANALYSIS_PATH_RE` | `re.Pattern` |
| `_LEAK_TAIL_RE` | `re.Pattern` |
| `_CONTINUE_WORDS_RE` | `re.Pattern` |
| `_CORRECTION_RE` | `re.Pattern` |

## Symbols explicitly NOT moved (kept in session.py)
- `_PROCESS_START_TIME` — must anchor to session.py module-load time.
- `_r3_time` / `_threading` imports — still needed by `_PROCESS_START_TIME`.
- All `_STATE_PATH` / `_UI_*` / `_CHAT_*` / `_EPISODIC_MEMORY_PATH` / `_CAPABILITY_GOVERNOR_STATUS_PATH` constants — tests monkeypatch them on `session_mod`.
- `SLASH_COMMANDS` — deferred (separate concern).

## Re-export shim in session.py
```python
from brain_v9.core.session_routing_constants import (  # noqa: F401  (re-export)
    AGENT_INTENTS,
    AGENT_KEYWORDS,
    _AGENT_PATTERNS,
    _CODE_ANALYSIS_PATH_RE,
    _LEAK_TAIL_RE,
    _CONTINUE_WORDS_RE,
    _CORRECTION_RE,
)
```
Object identity verified: `session.AGENT_KEYWORDS is rc.AGENT_KEYWORDS` and `session._AGENT_PATTERNS is rc._AGENT_PATTERNS`.

## File metrics
- `session.py` 5925 → 5811 lines (−114).
- `session_routing_constants.py` 172 lines (new).
- `AGENT_KEYWORDS` block sha256 byte-equivalent with HEAD: `30abf8572605c32ec6bac1d41f21e4174b1eaf2dbd4e482d7e2fac25245c1eec`.

## Validations (all passed)
- `py_compile` both modules: **PASS**
- `phase1_local_validation.ps1`: **PASS** (PHASE1_LOCAL_VALIDATION: ALL PASS)
- `test_phase1_import_baseline.py`: **PASS**
- `test_phase1_security_defaults.py`: **PASS**
- B7-02 ChatMetrics tests: **15/15 PASS**
- B7-03 query predicates tests: **36/36 PASS**
- B7-04 routing constants tests (new): **16/16 PASS**
- Import smoke: **PASS**
- `tmp_agent/tests/core/test_session.py`: 56 passed / 42 failed — **0 new failures** (HEAD baseline at worktree `../baseline_b7_04` showed identical 42 preexisting failures, all coroutine/await issues unrelated to routing constants).
- `tests/unit/test_brain_chat_hygiene.py`: 58 passed / 4 failed — **0 new failures** (HEAD baseline reproduced same 4 preexisting failures in `_prefers_no_tool_analysis` and execution-gate logic, unrelated to extracted symbols).
- `tests/unit/test_b7_routing_heuristics_characterization.py`: **PASS**.

## Files created
- `tmp_agent/brain_v9/core/session_routing_constants.py`
- `tests/unit/test_b7_routing_constants_import_compat.py`
- `tests/unit/test_b7_routing_constants_behavior_smoke.py`
- `tests/unit/test_b7_routing_constants_no_session_dependency.py`

## Files modified
- `tmp_agent/brain_v9/core/session.py`

## Hard rules respected
- No commit, no push, no `git add -A/.` (only `git add -N` intent-to-add was used solely to construct the unified patch including new files; subsequently undone via path-scoped `git reset HEAD -- <files>` which only removed intent markers and did not touch working tree content).
- No protected path touched.
- No existing tests modified.
- No main.py change required.
