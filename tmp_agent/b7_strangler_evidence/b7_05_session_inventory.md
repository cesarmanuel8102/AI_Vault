# B7-STRANGLER-05 — session.py inventory (post-B7-04)

Source: `tmp_agent/brain_v9/core/session.py`
Snapshot at HEAD `57a5e3a4` (refactor(b7): extract routing constants from session module).

## 1. Size and cumulative reduction

| Stage | Lines | Δ |
|---|---:|---:|
| pre-B7-02 | 7,637 | — |
| post-B7-02 (ChatMetrics) | 6,140 | −1,497 |
| post-B7-03 (query predicates) | 5,925 | −215 |
| post-B7-04 (routing constants) | **5,811** | −114 |
| **total reduction** | | **−1,826 (−23.91 %)** |

## 2. Top-level structure

- **Classes (1)**
  - `BrainSession` (lines 223-5805, 5,583 lines) — the only top-level class. Contains 174 methods.
- **Top-level functions (3)**
  - `__getattr__` (157-160) — module-level fallback for re-exports.
  - `_normalize` (210-220) — small helper.
  - `get_or_create_session` (5808-5811) — public factory.
- **Top-level constants (12)**
  - `log` (90), `_PROCESS_START_TIME` (122)
  - Path constants: `_STATE_PATH`, `_UI_PATH`, `_UI_INDEX`, `_UI_DASHBOARD`, `_UI_EDIT_STATE_PATH`, `_CHAT_METRICS_PATH`, `_CHAT_SESSION_DEFAULTS_PATH`, `_EPISODIC_MEMORY_PATH`, `_CAPABILITY_GOVERNOR_STATUS_PATH` (125-133) — all used as monkeypatch surface in tests, leave in place.
  - `SLASH_COMMANDS` (166-197, 32 lines)
- **Top-level imports**: 50 (asyncio, json, logging, os, re, …, plus `from .session_chat_metrics import …`, `from .session_query_predicates import …`, `from .session_routing_constants import …`).

## 3. BrainSession method-prefix groups

| Prefix | Count | Total lines |
|---|---:|---:|
| `_cmd_*` | 31 | 703 |
| `_fmt_*` | 17 | 295 |
| `_format_*` | 2 | 66 |
| `_render_*` | 2 | 116 |
| `_sanitize_*` | 3 | 102 |
| `_should_*` | 3 | 150 |
| `_extract_*` | 2 | 43 |
| `_route_*` | 2 | 564 |
| `_handle_*` | 1 | 69 |
| `_emit_/_log_*` | 1 | 41 |
| `_save_/_load_*` | 2 | 14 |
| other | 108 | 2,930 |

## 4. Largest remaining methods (top 10)

| Method | Lines | Kind | self / cls usage |
|---|---:|---|---|
| `chat` | 644 | method | self=111 |
| `_route_to_agent` | 448 | method | self=48 |
| `_policy_route_decision` | 187 | method | self=12 |
| `_tool01_execute` | 168 | method | self=18 |
| `_maybe_fastpath` | 129 | method | self=62 |
| `_recent_activity_fastpath` | 128 | method | self=5 |
| `_route_to_llm` | 116 | method | self=8 |
| `_maybe_grounded_ui_edit_fastpath` | 97 | method | self=10 |
| `_render_operational_agent_summary` | 81 | classmethod | cls=1 |
| `_sanitize_llm_chat_response` | 80 | staticmethod | self=0, cls=0 |

## 5. Pure static/class methods (no self) — 77 candidates

Top examples (all `self_uses == 0`):

| Method | Lines | Kind | cls |
|---|---:|---|---:|
| `_render_operational_agent_summary` | 81 | classmethod | 1 |
| `_sanitize_llm_chat_response` | 80 | staticmethod | 0 |
| `_truncate_to_budget` | 47 | classmethod | 2 |
| `_should_use_analysis_frontier` | 47 | classmethod | 7 |
| `_format_tool_result` | 45 | classmethod | 2 |
| `_build_grounded_file_excerpt` | 43 | classmethod | 1 |
| `_render_agent_failure_reply` | 35 | classmethod | 3 |
| `_prefers_no_tool_analysis` | 29 | staticmethod | 0 |
| 17× `_fmt_*` | 8-28 each (Σ 295) | classmethod | **0 for ALL 17** |
| `_extract_candidate_paths` | 26 | staticmethod | 0 |
| `_should_use_compact_chat_prompt` | 25 | classmethod | 4 |
| `_format_action_value` | 21 | staticmethod | 0 |
| `_sanitize_memory_content` | 20 | classmethod | 0 |
| `_has_explicit_tool_target` | 18 | staticmethod | 0 |
| `_extract_symbol_hint` | 17 | staticmethod | 0 |
| `_find_test_references` | 17 | classmethod | 0 |

## 6. Key dependency observations

- **`_sanitize_llm_chat_response`** body uses only the local `_re` (`import re as _re`) module + string methods. No `self`, no `cls`, zero coupling to `BrainSession`. Externally referenced by `tmp_agent/brain_v9/main.py:1257` and 3 production tests; `BrainSession._sanitize_llm_chat_response` must remain reachable as a staticmethod shim.
- **`_fmt_*` bundle (17 methods)** — confirmed by AST: every method is a `@classmethod` with signature `(cls, out)` and `cls_uses == 0` *and* `self_uses == 0`. All call only Python builtins (`isinstance`, `len`, `str`, `list`, `sum`, `sorted`). Invoked exclusively through `_format_tool_result` via `getattr(cls, _TOOL_FORMATTERS[tool])` (string lookup), which makes classmethod-shim re-export trivial. No external call site references `BrainSession._fmt_*` (the `_fmt_tools` matches in `core/llm.py` belong to a different class).
- **`_should_use_compact_chat_prompt` / `_should_use_analysis_frontier`** are pure but read class-level constants (`cls_uses` 4 and 7). Extracting requires also moving or exposing those constants — moderate complexity.
- **`_render_*` / `_format_tool_result`** depend on the `_fmt_*` group via `cls._TOOL_FORMATTERS`. Better to extract together with `_fmt_*`.
- **`_cmd_*`** group (31 methods, 703 lines) is heavily self-coupled — explicit defer.
- **`SLASH_COMMANDS`** is small (32 lines) but is the metadata table backing the `_cmd_*` dispatcher; better extracted alongside `_cmd_*` in a future ticket.
- **Path constants** (`_STATE_PATH` etc.) form the test monkeypatch surface — keep in place.

## 7. Read-only snapshot — no productive code modified

The two helper analyzer scripts (`_b7_05_analyzer.py`, `_b7_05_callers.py`, `_b7_05_extra.json`) live exclusively under `tmp_agent/b7_strangler_evidence/`. No edits were made to `session.py`, tests, or any productive module.
