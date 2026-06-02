# B7-STRANGLER-03 — Candidate ranking

## Summary

| ID | Block | Lines | Difficulty | Risk | Recommend |
|---|---|---:|---|---|---|
| **C1** | **Pure query predicates (`_is_*_query`, `_looks_like_*`)** | **~339** | **low** | **very low** | **YES (selected)** |
| C2 | Routing constants block | ~145 | low | very low | yes (next pass) |
| C3 | `SLASH_COMMANDS` dict | 34 | trivial | none | defer (bundle with C2) |
| C4 | `_normalize` helper | 11 | trivial | none | no (too small) |
| C5 | Chat dev-mode helpers | ~50 | low-medium | low | defer |
| C6 | Slash command handlers (`_cmd_*`) | ~740 | medium-high | medium | defer (after C1) |
| C7 | Tool01 subsystem (`_tool01_*`) | ~412 | medium | medium | defer |
| C8 | Format helpers (`_fmt_*`, `_render_*`) | ~700 | medium | medium | defer |

## Why C1 wins

- **Zero `self.*` references** in 31 method bodies (verified mechanically).
- Only deps are `re`, `json`, and one regex constant `_CODE_ANALYSIS_PATH_RE`.
- Backward compat trivially preserved by **thin instance-method shims** on `BrainSession`.
- External consumers (main.py, autonomy/proactive_scheduler.py, 3 unit tests) use them as bound methods (`session._is_*_query(msg)`) — shim pattern is invisible to them.
- ~310 LOC net reduction in `session.py`.
- Mirrors the proven B7-02 pattern (extract → re-export shim).

## Why others were deferred

- **C2** (routing constants) — equally low risk but smaller payoff; better to land C1 first and absorb constants in C3-bis pass.
- **C6** (slash commands) — biggest payoff but also biggest coupling; needs proven shim methodology first.
- **C7** (tool01) — moderate but mixes governance, file I/O and permission state; needs further audit.
- **C8** (formatters) — coupling varies per method; needs second-pass classification.

## External-consumer evidence (predicate methods)

| Predicate | External callers |
|---|---|
| `_is_brain_status_query` | main.py, tests/test_agent_self_build_resolution_p705b.py, tests/test_http_endpoints_p705.py |
| `_is_deep_brain_analysis_query` | main.py, autonomy/proactive_scheduler.py, 2 tests |
| `_is_deep_risk_analysis_query` | main.py, 2 tests |
| `_is_deep_edge_analysis_query` | main.py, 2 tests |
| `_is_deep_strategy_analysis_query` | main.py, 2 tests |
| `_is_deep_pipeline_analysis_query` | main.py, 2 tests |
| `_is_self_build_query` | main.py, 2 tests |
| `_is_self_build_resolution_query` | main.py, autonomy/proactive_scheduler.py, 1 test |
| `_is_consciousness_query` | main.py, 2 tests |
| `_is_llm_status_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_codex_role_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_codex_comparison_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_chat_interaction_review_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_brain_diagnostic_analysis_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_temporal_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_code_change_request` | tests/unit/test_brain_chat_hygiene.py |
| `_is_benign_security_audit_query` | tests/unit/test_brain_chat_hygiene.py |
| `_is_confirmation` | tests/unit/test_confirmation_bug_fix.py |
| `_is_tool_confirmation_request_response` | tests/unit/test_confirmation_bug_fix.py |
| `_is_grounded_code_analysis_query` | tests/unit/test_grounded_code_fastpath.py |
| 11 others (e.g. `_is_dashboard_query`, `_is_greeting_query`, `_is_capabilities_query`, ...) | none (internal-only) |

All consumers call them as bound methods on the `BrainSession` instance → preserved by the shim approach.
