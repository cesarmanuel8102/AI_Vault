# B7-STRANGLER-06-INVENTORY — Phase D: Selected Candidate Plan

## Selection: **C1 — `_fmt_*` tool result formatters bundle**

## New module
`tmp_agent/brain_v9/core/session_fmt_helpers.py`

## Move list (17 symbols)

Each `BrainSession._fmt_<name>` (classmethod) → module-level `fmt_<name>(out: Dict) -> str` (drop `_` prefix and `cls`).

| Old | New | Old lines |
|---|---|---|
| `_fmt_check_port` | `fmt_check_port` | L4447–4473 |
| `_fmt_check_http_service` | `fmt_check_http_service` | L4476–4486 |
| `_fmt_check_all_services` | `fmt_check_all_services` | L4489–4502 |
| `_fmt_check_service_status` | `fmt_check_service_status` | L4505–4517 |
| `_fmt_get_live_autonomy_status` | `fmt_get_live_autonomy_status` | L4520–4537 |
| `_fmt_run_diagnostic` | `fmt_run_diagnostic` | L4540–4552 |
| `_fmt_get_system_info` | `fmt_get_system_info` | L4555–4568 |
| `_fmt_run_command` | `fmt_run_command` | L4571–4581 |
| `_fmt_read_file` | `fmt_read_file` | L4584–4591 |
| `_fmt_list_directory` | `fmt_list_directory` | L4594–4608 |
| `_fmt_search_files` | `fmt_search_files` | L4611–4625 |
| `_fmt_list_processes` | `fmt_list_processes` | L4628–4642 |
| `_fmt_grep_codebase` | `fmt_grep_codebase` | L4646–4665 |
| `_fmt_list_recent_brain_changes` | `fmt_list_recent_brain_changes` | L4668–4694 |
| `_fmt_get_chat_metrics` | `fmt_get_chat_metrics` | L4697–4720 |
| `_fmt_semantic_memory_search` | `fmt_semantic_memory_search` | L4723–4744 |
| `_fmt_get_technical_introspection` | `fmt_get_technical_introspection` | L4747–4774 |

## Shim form (kept on `BrainSession`)

```python
@classmethod
def _fmt_check_port(cls, out):
    return fmt_check_port(out)
```

…repeated for all 17. Estimated +51 lines of shims, −295 lines removed → **net ≈ −244 lines**.

## Symbols explicitly NOT extracted

- `_TOOL_FORMATTERS` (registry; stays with dispatcher)
- `_format_tool_result` (uses `getattr(cls, name)`; stays with shims)
- `_format_action_value` (separate concern)

## Tests (3 new)

1. `tests/unit/test_b7_fmt_helpers_import_compat.py` — module symbols importable; shims still classmethods.
2. `tests/unit/test_b7_fmt_helpers_dispatcher_compat.py` — for each of 18 `_TOOL_FORMATTERS` keys, `_format_tool_result` dispatches correctly through shims; output equals direct module-level call.
3. `tests/unit/test_b7_fmt_helpers_no_session_dependency.py` — module usable in isolation without importing BrainSession.

## Validations post-implement

- `phase1_local_validation.ps1`
- `pytest tests/unit/test_phase1_import_baseline.py tests/unit/test_phase1_security_defaults.py`
- `pytest -k b7_` (carryover: 97 + new B7-06 tests)
- import smoke for new module + shimmed `_fmt_check_port`

## Rollback

```
git restore tmp_agent/brain_v9/core/session.py
rm tmp_agent/brain_v9/core/session_fmt_helpers.py
rm tests/unit/test_b7_fmt_helpers_*.py
```

## Risks

| Risk | Mitigation |
|---|---|
| Shim arity mismatch | Use `@classmethod def _fmt_x(cls, out): return fmt_x(out)` (verified safe; preserves descriptor binding) |
| `check_url` alias breakage | Alias maps to `_fmt_check_http_service`, which IS shimmed |
| Patch indentation drift | Surgical edit of contiguous L4447–L4774 block |
| Hidden state coupling | AST analysis confirmed `self_uses=0`, `cls_uses=0` for all 17 |

## Allowed paths for B7-06-IMPLEMENT

- `tmp_agent/brain_v9/core/session.py` (replace `_fmt_*` block with shims only)
- `tmp_agent/brain_v9/core/session_fmt_helpers.py` (NEW)
- `tests/unit/test_b7_fmt_helpers_*.py` (NEW, 3 files)
- `tmp_agent/b7_strangler_evidence/b7_06_*` (evidence)
