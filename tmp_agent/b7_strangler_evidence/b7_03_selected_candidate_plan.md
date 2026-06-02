# B7-STRANGLER-03 — Selected candidate plan

**Selected:** `C1_query_predicates_pure`
**New module:** `tmp_agent/brain_v9/core/session_query_predicates.py`
**Estimated `session.py` reduction:** ~308 lines net (extract 339, add 31 thin shims).
**Expected `session.py` size after:** ~5832 lines (from 6140).

## Why selected

Among 8 candidates evaluated, this block has the **lowest coupling-to-payoff ratio**:

- Mechanical verification: all 31 method bodies have **0 occurrences of `self.X`**.
- Module-level deps reduced to: `re`, `json`, `_CODE_ANALYSIS_PATH_RE`.
- Pattern reuses the proven B7-02 strangler approach (extract → re-export shim).
- All external consumers (main.py, autonomy/proactive_scheduler.py, 5 unit/integration tests) call these predicates as **bound methods on a `BrainSession` instance**. Thin shim methods preserve that exact API.

## Symbols to move (31 functions)

| Old method (BrainSession) | New module-level function |
|---|---|
| `_looks_like_canned_failure` | `looks_like_canned_failure` |
| `_is_benign_security_audit_query` | `is_benign_security_audit_query` |
| `_is_confirmation` | `is_confirmation` |
| `_is_code_change_request` | `is_code_change_request` |
| `_is_tool_confirmation_request_response` | `is_tool_confirmation_request_response` |
| `_is_dashboard_query` | `is_dashboard_query` |
| `_is_greeting_query` | `is_greeting_query` |
| `_is_capabilities_query` | `is_capabilities_query` |
| `_is_llm_status_query` | `is_llm_status_query` |
| `_is_codex_role_query` | `is_codex_role_query` |
| `_is_codex_comparison_query` | `is_codex_comparison_query` |
| `_is_recent_activity_query` | `is_recent_activity_query` |
| `_is_chat_interaction_review_query` | `is_chat_interaction_review_query` |
| `_is_brain_diagnostic_analysis_query` | `is_brain_diagnostic_analysis_query` |
| `_is_grounded_code_analysis_query` | `is_grounded_code_analysis_query` |
| `_is_chat_ui_background_change_query` | `is_chat_ui_background_change_query` |
| `_is_chat_ui_background_restore_query` | `is_chat_ui_background_restore_query` |
| `_is_chat_send_button_move_query` | `is_chat_send_button_move_query` |
| `_is_brain_status_query` | `is_brain_status_query` |
| `_is_deep_brain_analysis_query` | `is_deep_brain_analysis_query` |
| `_looks_like_deep_analysis` | `looks_like_deep_analysis` |
| `_is_deep_risk_analysis_query` | `is_deep_risk_analysis_query` |
| `_is_deep_edge_analysis_query` | `is_deep_edge_analysis_query` |
| `_is_deep_strategy_analysis_query` | `is_deep_strategy_analysis_query` |
| `_is_deep_pipeline_analysis_query` | `is_deep_pipeline_analysis_query` |
| `_is_self_build_query` | `is_self_build_query` |
| `_is_self_build_resolution_query` | `is_self_build_resolution_query` |
| `_is_consciousness_query` | `is_consciousness_query` |
| `_is_abstract_reasoning_query` | `is_abstract_reasoning_query` |
| `_is_operational_agent_query` | `is_operational_agent_query` |
| `_is_temporal_query` | `is_temporal_query` |

## Symbols to re-export (compat surface)

All 31 names remain on `BrainSession` as bound instance methods via thin one-line shims. **No public API change.** External consumers continue to call `session._is_*_query(msg)` exactly as before.

## Shim pattern

```python
# session.py module level (above class)
from brain_v9.core import session_query_predicates as _qp

class BrainSession:
    ...
    def _is_dashboard_query(self, message: str) -> bool:
        return _qp.is_dashboard_query(message)
    # ... 30 more identical-shape shims
```

## Imports in new module

```python
from __future__ import annotations
import json
import re
from typing import Optional
```

`_CODE_ANALYSIS_PATH_RE` will be **recompiled locally** in the new module (cheap, decouples and avoids any back-import from session.py).

## Tests recommended

- `tests/unit/test_b7_query_predicates_import_compat.py` (~90L) — verifies every predicate is still bound to `BrainSession` and returns identical results to the standalone function for representative inputs.
- `tests/unit/test_b7_query_predicates_behavior_smoke.py` (~130L) — small input matrix per predicate (positive + negative + edge case) to lock behavior.

## Validations recommended (when implementing B7-03)

- `py_compile session.py` and `session_query_predicates.py`
- `phase1_local_validation.ps1` (must remain ALL PASS)
- `tests/unit/test_phase1_import_baseline.py`, `test_phase1_security_defaults.py`
- B7-02 carryover: `test_b7_chatmetrics_import_compat.py`, `test_b7_chatmetrics_behavior_smoke.py`
- Predicate consumers: `test_brain_chat_hygiene.py`, `test_confirmation_bug_fix.py`, `test_grounded_code_fastpath.py`, `test_b7_routing_heuristics_characterization.py`
- Routing regressions: `test_chat_metrics_extended.py`, `test_contradiction_learning_layer.py`, `test_semantic_coherence_validation.py`, `test_fases_2_3_4_routing_analytics.py`

## Risk assessment

| Vector | Level | Notes |
|---|---|---|
| Circular import | very low | New module imports only stdlib |
| Behavior change | very low | Verbatim body copy; only `self` dropped |
| External consumer break | very low | Bound-method API preserved via shims |
| Test regression | very low | Tests call methods on instance — covered 1:1 |
| Performance | negligible | One extra Python frame per shim |

## Rollback plan

Single-commit revert (`git revert <b7-03 commit>`) is sufficient: one new module + edits to `session.py` + 2 new test files. No state-machine, persistence-layout, or import-graph changes — purely mechanical.

## Out of scope for B7-03-IMPLEMENT

- Routing constants (deferred — C2)
- Slash command handlers `_cmd_*` (deferred — C6)
- Tool01 subsystem (deferred — C7)
- Format helpers (deferred — C8)
- Any change to `main.py`, `config.py`, `api_security.py`, governance/UI
