# B7-STRANGLER-03 — session.py inventory (post-B7-02)

**HEAD:** `22c2b6af`  **File:** `tmp_agent/brain_v9/core/session.py`  **Total lines:** 6140

## Top-level structure

| Kind | Name | Line | Notes |
|---|---|---|---|
| function | `__getattr__` | 265 | PEP 562 proxy (B7-02 shim) |
| function | `_normalize` | 318 | 11-line utility |
| class | `BrainSession` | 331 | 158 methods, ~5800 lines |
| function | `get_or_create_session` | 6137 | Tiny registry accessor |

## Section separators

- L103 `── Routing Constants ──`
- L250 `── Chat Metrics Collector ──` (B7-02 re-export shim, untouched)
- L272 `── Slash Commands ──`
- L308 `═══ CONSOLIDATED HEURISTIC CONSTANTS (FASE B) ═══`

## Module-level constants (18)

`AGENT_INTENTS`, `AGENT_KEYWORDS`, `_AGENT_PATTERNS`, `_CODE_ANALYSIS_PATH_RE`, `_LEAK_TAIL_RE`, `_PROCESS_START_TIME`, `_CONTINUE_WORDS_RE`, `_CORRECTION_RE`, `_STATE_PATH`, `_UI_PATH`, `_UI_INDEX`, `_UI_DASHBOARD`, `_UI_EDIT_STATE_PATH`, `_CHAT_METRICS_PATH`, `_CHAT_SESSION_DEFAULTS_PATH`, `_EPISODIC_MEMORY_PATH`, `_CAPABILITY_GOVERNOR_STATUS_PATH`, `SLASH_COMMANDS`.

## BrainSession method group sizing

| Group | Methods | Approx lines | Coupling |
|---|---:|---:|---|
| Main chat orchestrator (`chat`, `_handle_command`, utility scoring) | 4 | ~727 | Critical runtime — DO NOT extract |
| Slash command handlers (`_cmd_*`) | 31 | ~740 | Heavy `self.*` usage — defer |
| Routing decisions (`_route_*`, `_should_use_*`, `_policy_route_decision`, `_maybe_fastpath`) | 12 | ~1450 | Critical runtime |
| Tool01 subsystem (`_tool01_*`) | 13 | ~412 | Medium coupling — defer |
| **Pure query predicates (`_is_*_query`, `_looks_like_*`, etc.)** | **31** | **~339** | **Zero `self.*` references — EXCELLENT** |
| Fastpath renderers (`*_fastpath`) | ~28 | ~800 | Heavy `self.*` — defer |
| Format helpers (`_fmt_*`, `_format_*`, `_render_*`) | ~23 | ~700 | Medium coupling — defer |
| Memory/persistence helpers (`_save_turn`, `_truncate_*`, `_sanitize_*`, etc.) | ~20 | ~700 | High coupling |
| Lifecycle (`__init__`, `close`, `_load/_persist_chat_dev_mode_default`) | 4 | ~50 | Class-level state |

## Largest single methods (top 10)

| Method | Lines | Size |
|---|---|---:|
| `chat` | 400-1047 | 648 |
| `_route_to_agent` | 3178-3637 | 460 |
| `_policy_route_decision` | 5357-5544 | 188 |
| `_tool01_execute` | 3009-3177 | 169 |
| `_maybe_fastpath` | 3743-3873 | 131 |
| `_recent_activity_fastpath` | 4084-4212 | 129 |
| `_route_to_llm` | 2243-2360 | 118 |
| `_llm_agent_salvage` | 2493-2610 | 118 |
| `_maybe_grounded_ui_edit_fastpath` | 4517-4615 | 99 |
| `_should_use_agent` | 1917-2001 | 85 |

## Key observation

The 31 `_is_*_query` / `_looks_like_*` predicates collectively span **~339 lines** with **zero references to `self.*`** in their bodies. They use only:
- `re` module
- `json` module
- `_CODE_ANALYSIS_PATH_RE` (one of the routing constants)

This makes them a **mechanically-verifiable, behavior-preserving extraction** with the lowest coupling-to-payoff ratio in the file.
