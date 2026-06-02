# B7-STRANGLER-08-IMPLEMENT — Token-aware truncation extraction report

## Summary

Extracted the token-aware context truncation helpers from
`tmp_agent/brain_v9/core/session.py` into a new dedicated module
`tmp_agent/brain_v9/core/session_context_budget.py`, preserving exact
behaviour and full backward compatibility on `BrainSession`.

| Metric | Before | After | Δ |
|---|---|---|---|
| `session.py` lines | 5396 | 5385 | **−11** |
| New module lines  |    0 |  133 | +133 |
| BrainSession class attr `_MAX_MSG_CHARS` | inline `6000` | `_cb.MAX_MSG_CHARS` re-bind | preserved |
| BrainSession `_truncate_message` | full body | 1-line `@staticmethod` shim | preserved |
| BrainSession `_truncate_to_budget` | 47-line `@classmethod` | 1-line `@classmethod` shim | preserved |

`session.py` cumulative reduction (since pre-B7-02): ~7637 → 5385 = **−2252 LOC**.

## Symbols moved

| Source (`session.py` BrainSession) | Destination (`session_context_budget`) |
|---|---|
| `_MAX_MSG_CHARS` (class attr `= 6000`)         | `MAX_MSG_CHARS: int = 6000` (module const) |
| `_truncate_message` (`@staticmethod`, L1919-1925) | `truncate_message(msg, max_chars)` |
| `_truncate_to_budget` (`@classmethod`, L1928-1974) | `truncate_to_budget(history, *, budget_tokens, max_msg_chars=0, max_msg_chars_default=MAX_MSG_CHARS)` |

## Symbols explicitly NOT moved

- `_context_budget` — uses `self.config`; stays on `BrainSession` (lines 1976-2015 unchanged).
- `_route_to_llm` (consumer at L2170) — unchanged.
- `_route_to_agent` (consumer at L3256) — unchanged.
- `LLMManager` — already in `brain_v9.core.llm`; imported by new module.
- `log` — re-defined in new module as `logging.getLogger("session_context_budget")`.

## Shim form used

```python
# session.py (top of file, near other B7 imports)
from brain_v9.core import session_context_budget as _cb

# inside BrainSession
_MAX_MSG_CHARS = _cb.MAX_MSG_CHARS

@staticmethod
def _truncate_message(msg: Dict, max_chars: int) -> Dict:
    return _cb.truncate_message(msg, max_chars)

@classmethod
def _truncate_to_budget(cls, history, *, budget_tokens, max_msg_chars=0):
    return _cb.truncate_to_budget(
        history,
        budget_tokens=budget_tokens,
        max_msg_chars=max_msg_chars,
        max_msg_chars_default=cls._MAX_MSG_CHARS,
    )
```

Descriptor types preserved (`staticmethod` / `classmethod`) so external
consumers calling `BrainSession._truncate_message(...)` /
`BrainSession._truncate_to_budget(...)` directly continue to work.

## Tests created

| File | Lines | Tests |
|---|---|---|
| `tests/unit/test_b7_context_budget_import_compat.py`        | 148 | 16 |
| `tests/unit/test_b7_context_budget_behavior_smoke.py`       | 175 | 15 |
| `tests/unit/test_b7_context_budget_no_session_dependency.py`| 159 |  8 |
| **Total** | **482** | **39** |

## Validations

| Check | Result |
|---|---|
| `py_compile` session.py + new module             | PASS |
| `phase1_local_validation.ps1` (PowerShell)       | ALL PASS |
| Phase1 pytest baseline                            | 5/5 PASS |
| B7 carryover suite (18 files)                    | 155/155 PASS |
| **B7-08 new tests (3 files)**                    | **39/39 PASS** |
| Existing `TestTruncateMessage` (4) + `TestTruncateToBudget` (8) | 12/12 PASS |
| Import smoke (`B7_08_CONTEXT_BUDGET_IMPORT_OK`)  | PASS |
| Consumer tests (main worktree)                   | 48 fail / 112 pass |
| Consumer tests (baseline `ef7b3770` worktree)    | 48 fail / 112 pass — **identical failure set** (verified with `diff`) |

**Conclusion: B7-08 introduced 0 new test failures.** The 48 consumer
failures are pre-existing at `ef7b3770` and unrelated to this extraction.

## Hard-rule compliance

- ✅ No commit, no push, no `git add -A`, no `reset/checkout/clean/stash`.
- ✅ No protected paths touched (`main.py`, `config.py`, `execution_gate.py`,
  `api_security.py`, `ui/*`, `memory/semantic/*`, `strategies/*`, ledger,
  ROADMAP_STATUS.json).
- ✅ No Tool01 / routing core / fastpaths touched.
- ✅ No already-extracted modules touched.
- ✅ No existing tests modified.
- ✅ `git add -N` used only to make untracked files visible to `git diff`
  for patch generation; `git diff --cached --name-status` is empty.

## Next recommended action

`B7-STRANGLER-08-COMMIT-PUSH` (or carry into a B7-09 inventory). Suggested
next candidate (from B7-08 inventory runner-up): **C-D — tool-analysis
prefs** (`_prefers_no_tool_analysis`, `_has_explicit_tool_target`,
~50 LOC, low risk, no circular deps).
