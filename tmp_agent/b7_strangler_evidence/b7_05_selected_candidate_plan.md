# B7-STRANGLER-05 — Selected candidate plan

(No implementation in this ticket; this is the executable plan for B7-STRANGLER-05-IMPLEMENT.)

## Selected: C1 — `_sanitize_llm_chat_response`

- Source location: `tmp_agent/brain_v9/core/session.py`, `BrainSession._sanitize_llm_chat_response`, lines **1993-2072** (80 lines).
- Decorator: `@staticmethod`. AST: `self_uses = 0`, `cls_uses = 0`.
- New module: **`tmp_agent/brain_v9/core/session_response_hygiene.py`**.

## Symbols to move

| Symbol | Kind | New name |
|---|---|---|
| `BrainSession._sanitize_llm_chat_response` body | pure logic | `session_response_hygiene.sanitize_llm_chat_response(content: str) -> str` |

Body is copied verbatim. The local `_re` alias inside the function may be replaced with the module-level `import re` in the new file (semantic equivalence preserved).

## Symbols to keep as shim / re-export on `BrainSession`

```python
# inside BrainSession (session.py)
from .session_response_hygiene import sanitize_llm_chat_response as _sanitize_llm_chat_response_impl
_sanitize_llm_chat_response = staticmethod(_sanitize_llm_chat_response_impl)
```

This preserves:
- `session._sanitize_llm_chat_response(content)` (instance-attribute access — used by `main.py:1257`)
- `BrainSession._sanitize_llm_chat_response(content)` (class-attribute access — used in tests)
- `self._sanitize_llm_chat_response(content)` (internal `chat` flow)

## Symbols explicitly excluded

- `_sanitize_memory_content` — different concern (memory record sanitization). Defer.
- `_prefers_no_tool_analysis`, `_has_explicit_tool_target` — routing predicates. Defer.
- All `_fmt_*` methods — runner-up bundle, plan as **B7-STRANGLER-06**.
- `_PROCESS_START_TIME`, all `_STATE_PATH` / `_UI_*` / `_CHAT_*` / `_EPISODIC_*` / `_CAPABILITY_*` path constants — kept in `session.py` (test monkeypatch surface).
- `SLASH_COMMANDS` — defer to slash-commands extraction.

## New tests (proposed)

1. **`tests/unit/test_b7_response_hygiene_import_compat.py`**
   - `BrainSession._sanitize_llm_chat_response` is callable and is the same underlying function as `session_response_hygiene.sanitize_llm_chat_response`.
   - Direct module import works without importing `session`.
2. **`tests/unit/test_b7_response_hygiene_behavior_smoke.py`** (8+ pinned cases)
   - theater prose removed
   - fake tool-call block removed
   - ORAV markers removed
   - placeholder lines removed
   - banned lines removed
   - empty / whitespace-only input → empty
   - idempotency: `sanitize(sanitize(x)) == sanitize(x)`
   - Unicode preservation
3. **`tests/unit/test_b7_response_hygiene_no_session_dependency.py`**
   - Import the new module *without* importing `brain_v9.core.session`; assert callable and stateless. Mirrors B7-03's pattern.

No existing test is modified.

## Validation matrix (must all pass before final report)

- `python -m py_compile tmp_agent/brain_v9/core/session.py tmp_agent/brain_v9/core/session_response_hygiene.py`
- `powershell -ExecutionPolicy Bypass -File tmp_agent/brain_v9/ops/phase1_local_validation.ps1` → ALL PASS
- `python tests/unit/test_phase1_import_baseline.py` → OK
- `python tests/unit/test_phase1_security_defaults.py` → OK
- B7-02 ChatMetrics suites — green
- B7-03 query predicates suites — green
- B7-04 routing constants suites — green
- B7-05 new suites — green
- `tests/unit/test_brain_chat_hygiene.py`, `test_agent_ghost_completion_hardening.py`, `test_real_verification_tool_trace_required.py`, `tmp_agent/tests/core/test_session.py` — **0 new failures** vs. HEAD baseline (worktree comparison protocol from B7-04).
- Import smoke:
  ```
  from brain_v9.core.session import BrainSession
  from brain_v9.core import session_response_hygiene as srh
  assert callable(BrainSession._sanitize_llm_chat_response)
  assert BrainSession.__dict__['_sanitize_llm_chat_response'].__func__ is srh.sanitize_llm_chat_response
  ```

## Rollback plan

- Single revert of the IMPLEMENT commit restores byte-identical `session.py`.
- Pre-commit: `git restore tmp_agent/brain_v9/core/session.py` + `rm` of the new module + 3 test files.
- The shim is a one-liner; trivial to remove if regression detected post-merge.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Regex literal mutation during copy → silent drift | sha256 the lifted source range pre/post; behavior-smoke tests pin outputs |
| `main.py` instance-style call breaks if shim form is wrong | Use `staticmethod(...)` form; add explicit identity test |
| Circular import as the new module grows | New module imports `re` only; forbid `session` imports; validated by no-session-dependency test |
| Pre-existing failures blamed on this change | MANDATORY git-worktree baseline comparison (B7-04 protocol) |

## Paths allowed for implementation

- `tmp_agent/brain_v9/core/session.py` — replace method body with shim + add import line.
- `tmp_agent/brain_v9/core/session_response_hygiene.py` — create.
- `tests/unit/test_b7_response_hygiene_*.py` — create three.
- `tmp_agent/b7_strangler_evidence/*` — evidence files.

## Paths forbidden

- `tmp_agent/brain_v9/main.py`, `config.py`, `governance/execution_gate.py`, `api_security.py`
- `tmp_agent/brain_v9/ui/*`, `memory/semantic/*`, `tmp_agent/strategies/*`
- `docs/MIGRATION_CONTROL_LEDGER.md`, `ROADMAP_STATUS.json`
- Any existing test file (no mutations allowed).

## Estimated impact

- session.py: **5,811 → ~5,732 lines (−~79)**.
- New module: ~85 lines.
- Cumulative reduction since pre-B7-02: ~1,905 lines (~24.9 %).
- Risk: **low** (mirrors B7-02/03/04 strangler pattern almost identically — single pure function, single shim).
