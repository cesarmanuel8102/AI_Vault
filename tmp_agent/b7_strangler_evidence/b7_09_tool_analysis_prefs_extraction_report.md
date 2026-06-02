# B7-STRANGLER-09-IMPLEMENT — Extraction Report (post follow-up)

**Status:** COMPLETE
**Timestamp (UTC):** 2026-06-02T17:17:20Z
**Branch:** `codex/own-capital-sustainable-return`
**HEAD before/after:** `1e8a67dd` / `1e8a67dd` (no commit, no push)

## Follow-up note (shim cleanliness)

Operator suspected inline duplicate logic remained inside the two BrainSession
shims. Investigation (manual read + AST audit) confirms the shims were already
clean from the original implementation:

```python
@staticmethod
def _prefers_no_tool_analysis(message: str) -> bool:
    """Detect explicit user preference for pure analysis/chat without tools.

    B7-STRANGLER-09 shim — delegates to ...prefers_no_tool_analysis.
    """
    return _tap.prefers_no_tool_analysis(message)

@staticmethod
def _has_explicit_tool_target(message: str) -> bool:
    """Keep agent routing when the user names a concrete file/service/command target.

    B7-STRANGLER-09 shim — delegates to ...has_explicit_tool_target.
    """
    return _tap.has_explicit_tool_target(message)
```

No edit to `session.py` or `session_tool_analysis_prefs.py` was required.
A new AST audit script was added under
`tmp_agent/b7_strangler_evidence/_b7_09_shim_cleanliness_audit.py` and produces
`B7_09_SHIM_CLEANLINESS_AST_AUDIT: PASS`.

The patch was regenerated with a binary-safe synthesizer to fix encoding
artifacts in the new-file blocks; the new patch passes
`git apply --reverse --check` against the working tree.

## Symbols

| Original (BrainSession) | Extracted (new module)              | Shim kind                                |
|-------------------------|-------------------------------------|------------------------------------------|
| `_prefers_no_tool_analysis` | `prefers_no_tool_analysis`      | `@staticmethod` — docstring + 1 Return  |
| `_has_explicit_tool_target` | `has_explicit_tool_target`      | `@staticmethod` — docstring + 1 Return  |

Out-of-scope (per spec): `routing/guards.py` parallel duplicates were **not** consolidated.

## Module shape

`session_tool_analysis_prefs.py` — 95 lines. Imports only:
- `__future__.annotations`
- `re` (stdlib)
- `brain_v9.core.session_routing_constants._CODE_ANALYSIS_PATH_RE`

No `BrainSession` import (text mentions only in module docstring; no `ast.Name`/`ast.Attribute` reference).

## session.py delta

- Lines: **5385 → 5366** (-19)
- Diff: 26 insertions, 45 deletions
- Edits applied during original implementation:
  1. Added `from brain_v9.core import session_tool_analysis_prefs as _tap` (with B7-09 banner comment block) right after the `_cb` import.
  2. Replaced the two method bodies with 1-line `@staticmethod` shims `return _tap.<func>(message)`.

## AST audit (new)

Script: `tmp_agent/b7_strangler_evidence/_b7_09_shim_cleanliness_audit.py`. Verifies for both shims:
- `@staticmethod` decorator present
- effective body = optional docstring + single `Return`
- `Return` calls `_tap.<expected_name>(message)` with single Name arg
- no `ast.Name 'msg'`, no `any(...)` Call, no `.search(...)` Call, no inline tuple-of-string-markers

For `session_tool_analysis_prefs.py`:
- contains both `prefers_no_tool_analysis` and `has_explicit_tool_target` FunctionDefs
- no `ast.Name('BrainSession')`, no `.BrainSession` attribute access
- no import from `brain_v9.core.session`

Result: **PASS**.

## Validations (all PASS)

| Bucket                                | Result                                |
|---------------------------------------|---------------------------------------|
| `py_compile` (both files)             | PASS                                  |
| Phase1 PowerShell                     | PASS                                  |
| Phase1 pytest                         | 5/5 PASS                              |
| New B7-09 tests                       | 83/83 PASS                            |
| B7 carryover (21 files)               | 194/194 PASS (2.11s)                  |
| Shim cleanliness AST audit            | PASS                                  |
| Consumer-test baseline equivalence    | 0 regressions vs `1e8a67dd` (48 == 48) |

## Guard-rails

- Protected paths touched: **false**
- Routing core / fastpaths / Tool01 / `routing/guards.py` touched: **false**
- Existing tests modified: **false**
- Productive files modified outside `session.py`: **false**
- `git add -N` used during patch generation: **false**
- Commit / push: **false / false**

## Patch

`tmp_agent/b7_strangler_evidence/b7_09_tool_analysis_prefs_extraction.patch`
- size: 25061 bytes
- sha256: `f94fbbb519c67e5d616845bd6c9dd31edc5a04a72ce7b7bc9ad65f993625cc2f`
- method: binary-safe custom Python script (`_b7_09_generate_patch.py`)
- `git apply --reverse --check` against working tree: **PASS**

## Next action

Operator review of patch, then manual commit/push. Afterwards: proceed to **B7-STRANGLER-10-INVENTORY**.
