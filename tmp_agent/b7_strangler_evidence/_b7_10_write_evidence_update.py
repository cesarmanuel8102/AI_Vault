"""Update evidence files post-fix."""
import json, textwrap, pathlib, hashlib

EV = pathlib.Path(r"C:\AI_VAULT\tmp_agent\b7_strangler_evidence")

# Update extraction report
report = {
    "ticket": "B7-STRANGLER-10-IMPLEMENT-FIX",
    "head_base": "ec8766bf",
    "session_py_lines_before": 5366,
    "session_py_lines_after": 5325,
    "session_py_net_reduction": 41,
    "new_module": "tmp_agent/brain_v9/core/session_llm_chain_select.py",
    "new_module_lines": 154,
    "helpers_extracted_count": 5,
    "symbols": [
        "MODEL_PRIORITY_ALIASES",
        "normalize_model_priority",
        "should_use_compact_chat_prompt",
        "should_use_analysis_frontier",
        "select_llm_chain",
    ],
    "internal_consumers_preserved": [
        "chat()",
        "_route_to_llm()",
        "_select_llm_chain()",
        "_select_agent_model_priority()",
        "_llm_status_fastpath()",
        "_codex_role_fastpath()",
    ],
    "external_consumers_preserved": [
        "tests/unit/test_brain_chat_hygiene.py",
        "tests/unit/test_llm_codex_integration.py",
    ],
    "shim_form": "4 @classmethod 1-line delegators + 1 class attr rebind to _llm_chain_select.MODEL_PRIORITY_ALIASES",
    "model_priority_aliases_rebound": True,
    "protected_paths_touched": False,
    "routing_core_touched": False,
    "fastpaths_touched": False,
    "tool01_touched": False,
    "routing_guards_touched": False,
    "already_extracted_modules_touched": False,
    "tests_created": [
        "tests/unit/test_b7_llm_chain_select_import_compat.py",
        "tests/unit/test_b7_llm_chain_select_behavior_smoke.py",
        "tests/unit/test_b7_llm_chain_select_no_session_dependency.py",
    ],
    "validations_summary": {
        "phase1_local_validation": "PASS",
        "b7_carryover_tests": "PASS (283 passed, 0 failed)",
        "llm_chain_select_tests": "PASS (52 passed, 0 failed)",
        "consumer_tests_brain_chat_hygiene": "BASELINE_EQUIVALENT (40 pre-existing failures)",
        "consumer_tests_llm_codex_integration": "BASELINE_EQUIVALENT (8 pre-existing failures)",
        "import_smoke": "PASS",
        "shim_cleanliness_ast_audit": "PASS",
        "py_compile_session_py": "PASS",
        "py_compile_new_module": "PASS",
        "patch_reverse_apply_check": "PASS (PATCH_REVERSES_CLEAN)",
    },
}
open(EV / "b7_10_llm_chain_select_extraction_report.json", "w", encoding="utf-8").write(json.dumps(report, indent=2))

md = textwrap.dedent("""\
# B7-STRANGLER-10 — LLM Chain Select Extraction Report (Post-Fix)

## Summary

- **Head base:** ec8766bf
- **session.py before:** 5366 lines
- **session.py after:** 5325 lines
- **Net reduction:** 41 lines
- **New module:** `tmp_agent/brain_v9/core/session_llm_chain_select.py` (154 lines)
- **Symbols extracted (5):** MODEL_PRIORITY_ALIASES, normalize_model_priority, should_use_compact_chat_prompt, should_use_analysis_frontier, select_llm_chain

## _MODEL_PRIORITY_ALIASES rebind

```python
# session.py — class attribute rebind (not duplicated inline dict)
_MODEL_PRIORITY_ALIASES = _llm_chain_select.MODEL_PRIORITY_ALIASES
```

This ensures a single source of truth in the new module while preserving
BrainSession._MODEL_PRIORITY_ALIASES access for all internal and external consumers.

## Shim form

```python
# session.py
from brain_v9.core import session_llm_chain_select as _llm_chain_select

class BrainSession:
    _MODEL_PRIORITY_ALIASES = _llm_chain_select.MODEL_PRIORITY_ALIASES

    @classmethod
    def _normalize_model_priority(cls, model_priority: str) -> str:
        return _llm_chain_select.normalize_model_priority(
            model_priority, aliases=cls._MODEL_PRIORITY_ALIASES,
        )

    @classmethod
    def _should_use_compact_chat_prompt(cls, message, intent, history, model_priority):
        return _llm_chain_select.should_use_compact_chat_prompt(...)

    @classmethod
    def _should_use_analysis_frontier(cls, message, intent, history, model_priority):
        return _llm_chain_select.should_use_analysis_frontier(...)

    @classmethod
    def _select_llm_chain(cls, message, intent, history, model_priority):
        return _llm_chain_select.select_llm_chain(...)
```

All shims are AST-clean: docstring optional + single Return statement.

## Consumers preserved

- Internal: chat(), _route_to_llm(), _select_llm_chain(), _select_agent_model_priority(), _llm_status_fastpath(), _codex_role_fastpath()
- External: test_brain_chat_hygiene.py (6 assertions), test_llm_codex_integration.py (3 assertions)

## Protected paths touched

None. Tool01, fastpaths, routing core, routing/guards.py, UI, memory, strategies, main.py, config.py, execution_gate.py, api_security.py all untouched.

## Already-extracted modules touched

None. Read-only imports from session_query_predicates (B7-03) and llm (already imported in session.py).

## Validation results

| validation | result |
|------------|--------|
| Phase1 local validation | PASS |
| B7 carryover (24 files) | PASS (283 passed, 0 failed) |
| B7-10 new tests (3 files) | PASS (52 passed, 0 failed) |
| test_brain_chat_hygiene.py | BASELINE_EQUIVALENT (40 pre-existing failures) |
| test_llm_codex_integration.py | BASELINE_EQUIVALENT (8 pre-existing failures) |
| Import smoke | PASS |
| AST shim audit | PASS |
| py_compile session.py | PASS |
| py_compile new module | PASS |
| Patch reverse apply check | PASS (PATCH_REVERSES_CLEAN) |

## Patch details

- **Path:** `tmp_agent/b7_strangler_evidence/b7_10_llm_chain_select_extraction.patch`
- **Size:** ~33 KB
- **Includes untracked files:** Yes (4 new files synthesized without `git add -N`)
- **git add -N used:** No
""")
open(EV / "b7_10_llm_chain_select_extraction_report.md", "w", encoding="utf-8").write(md)

# validation report
val = {
    "ticket": "B7-STRANGLER-10-IMPLEMENT-FIX",
    "head": "ec8766bf",
    "session_py_lines_before": 5366,
    "session_py_lines_after": 5325,
    "new_module": "tmp_agent/brain_v9/core/session_llm_chain_select.py",
    "new_module_lines": 154,
    "helpers_extracted_count": 5,
    "model_priority_aliases_rebound": True,
    "shim_cleanliness_ast_audit": "PASS",
    "patch_regenerated": True,
    "patch_includes_untracked_files": True,
    "patch_reverse_apply_check": "PASS",
    "patch_path": "tmp_agent/b7_strangler_evidence/b7_10_llm_chain_select_extraction.patch",
    "patch_size_bytes": 33115,
    "patch_sha256": hashlib.sha256(open(EV / "b7_10_llm_chain_select_extraction.patch", "rb").read()).hexdigest(),
    "validations_passed": [
        "phase1_local_validation",
        "b7_carryover_24_files",
        "llm_chain_select_new_tests_52",
        "import_smoke",
        "shim_cleanliness_ast_audit",
        "py_compile_session_py",
        "py_compile_new_module",
        "baseline_worktree_consumer_tests",
        "patch_reverse_apply_check",
    ],
    "validations_failed": [],
    "protected_paths_touched": False,
    "routing_core_touched": False,
    "fastpaths_touched": False,
    "tool01_touched": False,
    "routing_guards_touched": False,
    "already_extracted_modules_touched": False,
    "commit_created": False,
    "push_done": False,
    "blockers": [],
    "next_recommended_action": "Commit and push B7-STRANGLER-10-IMPLEMENT, then run full CI suite.",
}
open(EV / "b7_10_llm_chain_select_validation_report.json", "w", encoding="utf-8").write(json.dumps(val, indent=2))

print("Evidence updated.")
