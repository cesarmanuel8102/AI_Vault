# B7-STRANGLER-03-IMPLEMENT — Extraction Report

## Ticket
- **ID:** B7-STRANGLER-03-IMPLEMENT
- **Branch:** `codex/own-capital-sustainable-return`
- **HEAD (start = end, no commit performed):** `de3b61f013c9d58c953c7828cf7bd5e9bbfe8fbc`
- **Pattern:** Strangler (mirror of B7-STRANGLER-02 ChatMetrics)

## Goal
Extract 31 pure query/intent predicate methods from `tmp_agent/brain_v9/core/session.py` into a new side-effect-free module, while preserving full backward compatibility through thin shim delegators on `BrainSession`.

## Result Summary
| Metric | Value |
|---|---|
| Predicates extracted | **31** |
| New module | `tmp_agent/brain_v9/core/session_query_predicates.py` (414 lines) |
| `session.py` lines before | 6140 |
| `session.py` lines after | **5925** |
| `session.py` net delta | **−215 lines** |
| Shim methods retained on `BrainSession` | 31 (preserve `@staticmethod` / `@classmethod`) |
| Tests added | 3 files / 36 test cases |
| Tests added passing | 36 / 36 |
| Existing tests modified | **0** |
| Protected paths touched | **0** |

## Extracted Functions (31)
`looks_like_canned_failure`, `is_benign_security_audit_query`, `is_confirmation`, `is_code_change_request`, `is_tool_confirmation_request_response`, `is_dashboard_query`, `is_greeting_query`, `is_capabilities_query`, `is_llm_status_query`, `is_codex_role_query`, `is_codex_comparison_query`, `is_recent_activity_query`, `is_chat_interaction_review_query`, `is_brain_diagnostic_analysis_query`, `is_grounded_code_analysis_query`, `is_chat_ui_background_change_query`, `is_chat_ui_background_restore_query`, `is_chat_send_button_move_query`, `is_brain_status_query`, `is_deep_brain_analysis_query`, `looks_like_deep_analysis`, `is_deep_risk_analysis_query`, `is_deep_edge_analysis_query`, `is_deep_strategy_analysis_query`, `is_deep_pipeline_analysis_query`, `is_self_build_query`, `is_self_build_resolution_query`, `is_consciousness_query`, `is_abstract_reasoning_query`, `is_operational_agent_query`, `is_temporal_query`.

## Design Decisions
1. **Mirrored constants (intentional duplication)** — `_CODE_ANALYSIS_PATH_RE`, `_CONFIRM_PATTERNS`, `_TEMPORAL_QUERY_RE`, `_RECENT_ACTIVITY_PATTERNS` are duplicated byte-equivalent in `session_query_predicates.py` so the new module avoids any circular import on `brain_v9.core.session`. The originals on `BrainSession` are intentionally kept (no breakage to reflection callers).
2. **Decorator preservation** — Each shim retains the original `@staticmethod` (21) or `@classmethod` (10) decorator and signature. Only the body is replaced by a single-line `return _qp.<new_name>(...)`.
3. **No `self.X` refs** to remove (verified pre-extraction = 0). The 8 `cls.X` refs were rewritten to module-level constants / peer pure functions in the new module.
4. **Pure module rules** — `from __future__ import annotations` + `import re` only. No imports of `brain_v9.core.session`. No references to `BrainSession`. No `self.` / `cls.` tokens. Verified by `test_b7_query_predicates_no_session_dependency.py`.

## Files
| Path | Kind | Lines | MD5 |
|---|---|---|---|
| `tmp_agent/brain_v9/core/session.py` | modified | 5925 | `951f97909c5a1b4533e49eb77826d9ae` |
| `tmp_agent/brain_v9/core/session_query_predicates.py` | added | 414 | `2163ebc3969e9d1871e0824c4349a81c` |
| `tests/unit/test_b7_query_predicates_import_compat.py` | added | 135 | `b0108013c80761f126760603c454e144` |
| `tests/unit/test_b7_query_predicates_behavior_smoke.py` | added | 232 | `979506446d3d53887aedf3b97f0533e5` |
| `tests/unit/test_b7_query_predicates_no_session_dependency.py` | added | 111 | `62dc8c9acacb1efba399080d6df11ca5` |

## Validation
See `b7_03_query_predicates_validation_report.json`.

## Notes
- All `_should_use_agent` / `_prefers_no_tool_analysis` / `_has_explicit_tool_target` test failures observed in `test_brain_chat_hygiene.py` and `test_confirmation_bug_fix.py` are **pre-existing on origin HEAD `de3b61f0`** and unrelated to B7-03 (verified by stashing the session.py changes — failures persist). None of those methods are in the 31 extracted predicates.
- LSP errors in `governance_health.py`, `proposal_governance.py`, `main.py`, `session.py`, `agent/loop.py` are pre-existing and unrelated.
