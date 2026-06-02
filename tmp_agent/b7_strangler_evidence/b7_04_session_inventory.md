# B7-STRANGLER-04 — session.py Structural Inventory (post-B7-03)

**File:** `tmp_agent/brain_v9/core/session.py`
**Total lines:** 5925

## Cumulative B7 line reduction

| Stage | Lines | Δ |
|-------|-------|---|
| pre-B7-02 | 7637 | — |
| post-B7-02 | 6140 | −1497 |
| post-B7-03 | **5925** | −215 |
| **Cumulative** | | **−1712** |

## Top-level shape

- 26 imports
- **1 class:** `BrainSession` lines 337..5919 (5583 body lines, 174 methods, 13 class attrs)
- **3 top-level functions:** `__getattr__` (271-274, PEP 562 proxy for `_GLOBAL_CHAT_METRICS`), `_normalize` (324-334), `get_or_create_session` (5922-5925)
- **19 top-level constants** (lines 90-311)

## Top-level constants

| Name | Lines | Notes |
|------|-------|-------|
| `log` | 90 | logger |
| `AGENT_INTENTS` | 105 | set[str] |
| `AGENT_KEYWORDS` | 109-190 | **82 lines** list[str] |
| `_AGENT_PATTERNS` | 193 | derived from AGENT_KEYWORDS |
| `_CODE_ANALYSIS_PATH_RE` | 195-199 | re.Pattern |
| `_LEAK_TAIL_RE` | 202-206 | re.Pattern |
| `_PROCESS_START_TIME` | 211 | monotonic baseline |
| `_CONTINUE_WORDS_RE` | 212-216 | re.Pattern |
| `_CORRECTION_RE` | 221-236 | re.Pattern |
| Path constants block | 239-247 | `_STATE_PATH`, `_UI_PATH`, `_UI_INDEX`, `_UI_DASHBOARD`, `_UI_EDIT_STATE_PATH`, `_CHAT_METRICS_PATH`, `_CHAT_SESSION_DEFAULTS_PATH`, `_EPISODIC_MEMORY_PATH`, `_CAPABILITY_GOVERNOR_STATUS_PATH` |
| `SLASH_COMMANDS` | 280-311 | **32-line dict** |

## BrainSession method groups (by prefix)

| Group | Count | Total lines | Notes |
|-------|-------|------------|-------|
| `_other_` | 47 | 1263 | Misc, includes fastpaths, salvage |
| `_chat_*` | 2 | 708 | `chat` (644!), `_chat_interaction_review_fastpath` — **routing core** |
| `_cmd_*` | 31 | 703 | Slash command handlers; mostly use `self` |
| `_route_*` | 2 | 564 | `_route_to_agent` (448), `_route_to_llm` (116) — **routing core** |
| `_maybe_*` | 8 | 461 | Includes `_maybe_fastpath` — **routing core** |
| `_tool01_*` | 12 | 363 | **OFF-LIMITS** (permission gate) |
| `_predicate_*` | 39 | 312 | 35 already shims (post-B7-03) |
| **`_fmt_*`** | 17 | **295** | classmethods, 0 self refs ← strong future candidate |
| `_render_*` | 2 | 116 | classmethods |
| `_handle_*` | 1 | 69 | `_handle_command` |
| `_format_*` | 2 | 66 | classmethod + staticmethod |
| Other small groups | — | <70 each | |

## Largest pure (no `self`) methods (top 10)

| Name | Lines | Decorator | self_refs | cls_refs |
|------|-------|-----------|-----------|----------|
| `_render_operational_agent_summary` | 81 | classmethod | 0 | 1 |
| `_sanitize_llm_chat_response` | 80 | staticmethod | 0 | 0 |
| `_truncate_to_budget` | 47 | classmethod | 0 | 2 |
| `_should_use_analysis_frontier` | 47 | classmethod | 0 | 7 |
| `_format_tool_result` | 45 | classmethod | 0 | 2 |
| `_build_grounded_file_excerpt` | 43 | classmethod | 0 | 1 |
| `_render_agent_failure_reply` | 35 | classmethod | 0 | 3 |
| `_prefers_no_tool_analysis` | 29 | staticmethod | 0 | 0 |
| `_fmt_get_technical_introspection` | 28 | classmethod | 0 | 0 |
| `_fmt_check_port` | 27 | classmethod | 0 | 0 |

## External consumers of routing/path constants

Scan: ripgrep over `C:/AI_VAULT/**/*.py`, excluding `session.py`, `b7_strangler_evidence`, `__pycache__`. See `_b7_04_external_consumers.json` for full detail.

| Symbol | External consumers |
|--------|-------------------|
| `AGENT_KEYWORDS` | tmp_agent/tests/core/test_session.py (import), tests/unit/test_b7_routing_heuristics_characterization.py (attr) |
| `_AGENT_PATTERNS` | tmp_agent/tests/core/test_session.py (import), tmp_agent/debug_routing.py (import), tests/unit/test_brain_chat_hygiene.py (attr) |
| `SLASH_COMMANDS` | tmp_agent/tests/core/test_session.py (import) |
| `_STATE_PATH` | tmp_agent/tests/conftest.py (**monkeypatch**) |
| `_UI_INDEX`, `_UI_EDIT_STATE_PATH` | tests/unit/test_brain_chat_hygiene.py (**monkeypatch**) |
| `_CHAT_SESSION_DEFAULTS_PATH` | tests/unit/test_brain_chat_hygiene.py (**monkeypatch**) |
| `AGENT_INTENTS`, `_CODE_ANALYSIS_PATH_RE`, `_LEAK_TAIL_RE`, `_CONTINUE_WORDS_RE`, `_CORRECTION_RE`, `_PROCESS_START_TIME`, `_UI_PATH`, `_UI_DASHBOARD`, `_EPISODIC_MEMORY_PATH`, `_CAPABILITY_GOVERNOR_STATUS_PATH`, `_CHAT_METRICS_PATH` | none (internal only) |

Notes:
- `agent/loop.py:2224` defines its OWN class-level `_LEAK_TAIL_RE` (same name, separate symbol — no impact).
- `session_query_predicates.py` (post-B7-03) keeps its own copy of `_CODE_ANALYSIS_PATH_RE`.
- `session_chat_metrics.py` (post-B7-02) keeps its own `_STATE_PATH` and `_CHAT_METRICS_PATH`.

## Class-level patterns inside BrainSession

- `_TEMPORAL_QUERY_RE` (L364) — duplicated in session_query_predicates after B7-03.
- `_CONFIRM_PATTERNS` (L3615) — duplicated in session_query_predicates after B7-03.
- `_RECENT_ACTIVITY_PATTERNS` (L3937) — duplicated in session_query_predicates after B7-03.

## Conclusions feeding candidate selection

- Routing regex constants (7 names) are pure, no-self, **safe to extract with re-export shim** to satisfy `tmp_agent/tests/core/test_session.py`, `tmp_agent/debug_routing.py`, and the hygiene/characterization tests.
- Path constants are tied to monkeypatch semantics — extracting them is a high-risk, low-payoff move and is rejected for this round.
- `_tool01_*` is off-limits per task rules.
- The `_fmt_*` (295 lines), `_render_*` + `_format_*` (182 lines), and `_sanitize_llm_chat_response` (80 lines) are good follow-up candidates, but require a method-rebinding pattern that has not yet been established in the strangler series.
