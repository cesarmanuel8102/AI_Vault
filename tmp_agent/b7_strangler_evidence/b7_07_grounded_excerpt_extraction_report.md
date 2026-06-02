# B7-STRANGLER-07-IMPLEMENT — Extraction Report

**Ticket:** B7-STRANGLER-07-IMPLEMENT
**Selected candidate:** C1 — Grounded code excerpt cluster
**HEAD at start:** `f1ed722dd59607eb6669a9155a7e3381b34169a4`
**Branch:** `codex/own-capital-sustainable-return`
**Status:** ✅ Complete (uncommitted, working tree)

## Summary

Extracted 6 pure helpers used by `BrainSession._maybe_grounded_code_analysis_fastpath`
out of `tmp_agent/brain_v9/core/session.py` (lines 3990–4117) into a new module
`tmp_agent/brain_v9/core/session_grounded_excerpt.py`. The 6 original methods on
`BrainSession` are preserved as one-line shims, keeping the original descriptor
type (3 `@staticmethod` + 3 `@classmethod`) — required because
`tests/unit/test_grounded_code_fastpath.py:17` binds
`BrainSession._extract_candidate_paths` as a staticmethod directly.

## Line-count delta

| File | Before | After | Δ |
|---|---:|---:|---:|
| `tmp_agent/brain_v9/core/session.py` | 5491 | 5396 | **−95** |
| `tmp_agent/brain_v9/core/session_grounded_excerpt.py` (new) | — | 178 | +178 |

## Symbol map

| BrainSession method (kept as shim) | New module function |
|---|---|
| `_extract_candidate_paths` (staticmethod) | `extract_candidate_paths` |
| `_extract_symbol_hint` (staticmethod) | `extract_symbol_hint` |
| `_slice_lines` (staticmethod) | `slice_lines` |
| `_build_grounded_file_excerpt` (classmethod) | `build_grounded_file_excerpt` |
| `_find_test_references` (classmethod) | `find_test_references` |
| `_build_test_reference_excerpt` (classmethod) | `build_test_reference_excerpt` |

Inside the new module, `build_grounded_file_excerpt` and
`build_test_reference_excerpt` (which previously called `cls._slice_lines`) now
call module-level `slice_lines()` directly.

## Tests added

| File | Test count |
|---|---:|
| `tests/unit/test_b7_grounded_excerpt_import_compat.py` | 7 |
| `tests/unit/test_b7_grounded_excerpt_behavior_smoke.py` | 12 |
| `tests/unit/test_b7_grounded_excerpt_no_session_dependency.py` | 4 |
| **Total** | **23** |

All 23 pass.

## Validation

- **New B7-07 tests:** 23 passed / 0 failed
- **Full B7 carryover (incl. consumer `test_grounded_code_fastpath`):** 155 passed / 0 failed
- **Consumer baseline (`test_session.py` + routing chars + chat hygiene):** 112 passed / 48 failed. Verified identical failing-test-name set against fresh worktree at `f1ed722d` (`git worktree add --detach`). 0 new regressions.
- **Phase 1 import smoke:** OK (`BrainSession` imports cleanly; new module exposes 6 helpers).

## Contract preservation

- Descriptor type preserved per shim (verified via `BrainSession.__dict__[name]` `type().__name__`).
- No existing test modified.
- No modifications to: `main.py`, `config.py`, `governance/*`, routing core, fastpaths, UI, strategies, MIGRATION_CONTROL_LEDGER, ROADMAP_STATUS.
- No modifications to previously extracted modules (`session_chat_metrics.py`, `session_query_predicates.py`, `session_routing_constants.py`, `session_response_hygiene.py`, `session_fmt_helpers.py`).
- `_CODE_ANALYSIS_PATH_RE` continues to live in `session_routing_constants` and is imported by both the new module and `session.py` (re-exported there).

## LSP

All diagnostic errors are pre-existing in unrelated files (`main.py`, `loop.py`,
`session.py:59,499,661,2447,2474,2870-2918`, `governance_health.py`,
`proposal_governance.py`). No new code-level errors introduced by the new
module or shims.

## Patch

`tmp_agent/b7_strangler_evidence/b7_07_grounded_excerpt_extraction.patch`
(diff of `session.py` only; new module/test files are unstaged adds).
