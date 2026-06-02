# B7-STRANGLER-06-IMPLEMENT — Extraction Report

**Status:** ✅ COMPLETE
**HEAD:** `aabe4a84` (no commits made by this task)
**Branch:** `codex/own-capital-sustainable-return`

## Summary

Extracted the 17 `_fmt_*` tool-result formatter classmethods from
`BrainSession` (in `tmp_agent/brain_v9/core/session.py`) into a new pure-function
module `tmp_agent/brain_v9/core/session_fmt_helpers.py`. Same-arity classmethod
shims remain on `BrainSession` so the existing `_TOOL_FORMATTERS` registry
(incl. the `check_url` → `_fmt_check_http_service` alias) and the
`getattr(cls, method_name)` dispatch path in `_format_tool_result` keep
resolving identically.

## Metrics

| Quantity                                           | Before | After  | Delta   |
|----------------------------------------------------|-------:|-------:|--------:|
| `tmp_agent/brain_v9/core/session.py` lines         | 5,743  | 5,491  |  -252   |
| `tmp_agent/brain_v9/core/session_fmt_helpers.py`   | 0      | 378    |  +378   |
| Cumulative B7 strangler reduction (since 7,637)    | —      | 5,491  |  -2,146 (-28.1%) |

## Modules / files touched

| Path                                                              | Status     |
|-------------------------------------------------------------------|------------|
| `tmp_agent/brain_v9/core/session.py`                              | Modified (1 import added; 17 method bodies replaced with shims) |
| `tmp_agent/brain_v9/core/session_fmt_helpers.py`                  | **NEW** (17 pure functions + `__all__`) |
| `tests/unit/test_b7_fmt_helpers_import_compat.py`                 | **NEW** (6 tests) |
| `tests/unit/test_b7_fmt_helpers_behavior_smoke.py`                | **NEW** (31 tests) |
| `tests/unit/test_b7_fmt_helpers_no_session_dependency.py`         | **NEW** (4 tests) |

## Shim form

```python
@classmethod
def _fmt_check_port(cls, out: Dict) -> str:
    return _fmt_helpers.fmt_check_port(out)
```

**Rationale:** The alternative `_fmt_check_port = classmethod(fmt_check_port)`
would inject `cls` into `fmt_check_port`'s `(out)`-only signature, breaking
the dispatcher contract `formatter = getattr(cls, method_name); formatter(out)`.
The explicit classmethod wrapper preserves both the descriptor type and the
binding semantics.

## Invariants preserved

- `BrainSession._TOOL_FORMATTERS` (18 entries: 17 canonical + `check_url` alias) — kept verbatim in `session.py`.
- `BrainSession._format_tool_result(tool, ok, output, error=None)` — kept in `session.py`; uses `getattr(cls, method_name)`.
- `BrainSession._format_action_value` — out of scope, untouched in `session.py`.
- All 17 shims remain `@classmethod` descriptors; `getattr(BrainSession, name)` returns a callable bound method.
- Module `session_fmt_helpers.py` has zero coupling to `session`: no imports, no class references, only `typing.{Any,Dict}`.

## Validation results

| Validation                                            | Result |
|-------------------------------------------------------|--------|
| `python -m py_compile session.py`                     | PASS   |
| `python -m py_compile session_fmt_helpers.py`         | PASS   |
| `phase1_local_validation.ps1`                         | ALL PASS |
| `pytest test_phase1_import_baseline + security_defaults` | 5 passed |
| `pytest -k b7_` (carryover + new B7-06)               | 138 passed (97 prior + 41 new) |
| New B7-06 tests (3 files)                             | 41 passed |
| Dispatcher smoke (iterate `_TOOL_FORMATTERS`)         | `B7_06_FMT_DISPATCHER_OK` |
| Import smoke `from … import fmt_check_port`           | `IMPORT_OK` |
| Import smoke `BrainSession._fmt_check_port` callable  | `SHIM_OK` |
| Consumer suites (test_session.py + 2 others)          | 48 failed / 112 passed — **identical to baseline at `aabe4a84`** (pre-existing, unrelated to extraction; verified via `git worktree add` against unmodified HEAD) |

## Protected paths — untouched

`main.py`, `config.py`, `governance/execution_gate.py`, `api_security.py`,
`tmp_agent/brain_v9/ui/*`, `memory/semantic/*`, `tmp_agent/strategies/*`,
`docs/MIGRATION_CONTROL_LEDGER.md`, `ROADMAP_STATUS.json`, Tool01 internals,
routing core, fastpath helpers, and the four already-extracted B7 modules
(`session_chat_metrics.py`, `session_query_predicates.py`,
`session_routing_constants.py`, `session_response_hygiene.py`).

## Evidence emitted

- `b7_06_implement_preflight.json`
- `b7_06_implement_confirm_inventory.json`
- `b7_06_fmt_helpers_extraction_report.json` / `.md` (this file)
- `b7_06_fmt_helpers_validation_report.json`
- `b7_06_fmt_helpers_patch_manifest.json`
- `b7_06_fmt_helpers_extraction.patch` (1,240 lines)
