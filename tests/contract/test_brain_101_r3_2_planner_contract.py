"""BRAIN-101-R3-2 Agent V2 planner contract tests.

Front: BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
Surface: C3 Planner contract

Deterministic contract tests for the planner input/output schema, planner
class inventory, explicit tool-request detection, diagnostic phrase mapping,
and evidence-policy gating.  No server starts, no HTTP calls, no real writes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

PLANNER_MODULE = "brain_v9.core.agent_kernel_v2.planner"


# ---------------------------------------------------------------------------
# 1. Planner classification inventory
# ---------------------------------------------------------------------------

def test_planner_classes_inventory_is_complete():
    from brain_v9.core.agent_kernel_v2.planner import PLANNER_CLASSES

    required = {
        "repo_audit",
        "code_search",
        "endpoint_probe",
        "memory_question",
        "dashboard_diagnosis",
        "provider_diagnosis",
        "frontend_diagnosis",
        "smoke_test",
        "documentation_task",
        "safe_patch_dry_run",
        "approval_required_write",
        "general_reasoning",
        "mandatory_multitool",
        "explicit_tool_request",
        "autonomy_diagnosis",
        "recent_changes_diagnosis",
        "teacher_codex_search",
        "memory_structure_diagnosis",
        "semantic_memory_status",
        "promotion_queue_status",
        "trace_inspect",
        "capability_registry_read",
        "financial_autonomy_diagnosis",
        "evidence_required_diagnosis",
        "brain_self_knowledge_lookup",
    }
    assert required.issubset(set(PLANNER_CLASSES))
    assert "god_mode" not in PLANNER_CLASSES
    assert "live_trading_request" not in PLANNER_CLASSES


# ---------------------------------------------------------------------------
# 2. build_plan output schema contract
# ---------------------------------------------------------------------------

def test_build_plan_returns_required_schema():
    from brain_v9.core.agent_kernel_v2.planner import build_plan

    classification, plan, metadata = build_plan("What is the current repo status?", mode="read_only")
    assert isinstance(classification, str)
    assert classification in {
        "repo_audit",
        "code_search",
        "endpoint_probe",
        "memory_question",
        "dashboard_diagnosis",
        "provider_diagnosis",
        "frontend_diagnosis",
        "smoke_test",
        "documentation_task",
        "safe_patch_dry_run",
        "approval_required_write",
        "general_reasoning",
        "mandatory_multitool",
        "explicit_tool_request",
        "autonomy_diagnosis",
        "recent_changes_diagnosis",
        "teacher_codex_search",
        "memory_structure_diagnosis",
        "semantic_memory_status",
        "promotion_queue_status",
        "trace_inspect",
        "capability_registry_read",
        "financial_autonomy_diagnosis",
        "evidence_required_diagnosis",
        "brain_self_knowledge_lookup",
    }
    assert isinstance(plan, list)
    assert isinstance(metadata, dict)
    required_meta_keys = {"requested_checks", "scheduled_tools", "executed_tools"}
    assert required_meta_keys.issubset(metadata.keys())
    for step in plan:
        assert isinstance(step, dict)
        assert "step_id" in step
        assert "kind" in step
        assert "title" in step
        assert "status" in step
        assert step["status"] == "planned"


def test_build_plan_for_repo_audit_schedules_read_only_tools():
    from brain_v9.core.agent_kernel_v2.planner import build_plan

    classification, plan, _metadata = build_plan("git status", mode="read_only")
    assert classification == "repo_audit"
    tool_names = [s["tool_name"] for s in plan if s.get("tool_name")]
    assert "repo_status_read" in tool_names


def test_build_plan_for_financial_autonomy_diagnosis():
    from brain_v9.core.agent_kernel_v2.planner import build_plan

    classification, plan, _metadata = build_plan(
        "financial autonomy broker_execution_enabled real_money_enabled", mode="read_only"
    )
    assert classification == "financial_autonomy_diagnosis"
    tool_names = [s["tool_name"] for s in plan if s.get("tool_name")]
    assert "repo_file_search" in tool_names
    assert "file_patch_apply_approval_required" not in tool_names


def test_build_plan_for_dashboard_diagnosis_schedules_read_only_probe():
    from brain_v9.core.agent_kernel_v2.planner import build_plan

    classification, plan, _metadata = build_plan("dashboard failure status", mode="read_only")
    assert classification == "evidence_required_diagnosis"
    tool_names = {s["tool_name"] for s in plan if s.get("tool_name")}
    assert "route_probe" in tool_names or "grep_search" in tool_names or "repo_status_read" in tool_names
    assert "file_patch_apply_approval_required" not in tool_names


# ---------------------------------------------------------------------------
# 3. Explicit tool request detection contract
# ---------------------------------------------------------------------------

def test_detect_explicit_tool_requests_extracts_named_tools():
    from brain_v9.core.agent_kernel_v2.planner import _detect_explicit_tool_requests

    requests = _detect_explicit_tool_requests("Use repo_status_read and run grep_search for agent")
    names = {r["tool_name"] for r in requests}
    assert "repo_status_read" in names
    assert "grep_search" in names
    for r in requests:
        assert r.get("confidence") == "high"
        assert r.get("source") == "explicit_request"


def test_detect_explicit_tool_requests_ignores_generic_tool_words():
    from brain_v9.core.agent_kernel_v2.planner import _detect_explicit_tool_requests

    requests = _detect_explicit_tool_requests("What tools can you use?")
    assert "tool" not in {r["tool_name"] for r in requests}
    assert "tools" not in {r["tool_name"] for r in requests}


# ---------------------------------------------------------------------------
# 4. Diagnostic phrase mapping contract
# ---------------------------------------------------------------------------

def test_diagnostic_phrases_have_required_intents():
    from brain_v9.core.agent_kernel_v2.planner import DIAGNOSTIC_PHRASES

    required = {"autonomy_heartbeat", "recent_changes", "git_history"}
    assert required.issubset(set(DIAGNOSTIC_PHRASES))
    for name, config in DIAGNOSTIC_PHRASES.items():
        assert {"triggers", "tools"}.issubset(config)
        assert isinstance(config["triggers"], list)
        assert isinstance(config["tools"], list)
        for tool, args in config["tools"]:
            assert isinstance(tool, str)
            assert isinstance(args, dict)


def test_detect_diagnostic_phrases_maps_symptoms_to_tools():
    from brain_v9.core.agent_kernel_v2.planner import _detect_diagnostic_phrases

    diagnostics = _detect_diagnostic_phrases("Show me the git log and recent commits")
    names = {d["diagnosis"] for d in diagnostics}
    assert "git_history" in names


# ---------------------------------------------------------------------------
# 5. Evidence-policy gate contract
# ---------------------------------------------------------------------------

def test_requires_generic_evidence_detects_brain_internal_questions():
    from brain_v9.core.agent_kernel_v2.planner import _requires_generic_evidence

    assert _requires_generic_evidence("How is semantic memory structured?") is True
    assert _requires_generic_evidence("What is the weather today?") is False


# ---------------------------------------------------------------------------
# 6. classify_goal entry contract
# ---------------------------------------------------------------------------

def test_classify_goal_rejects_write_requests_in_read_only_mode():
    from brain_v9.core.agent_kernel_v2.planner import classify_goal

    classification = classify_goal("edit README.md", mode="read_only")
    assert classification in {"approval_required_write", "general_reasoning"}


def test_classify_goal_does_not_classify_greetings_as_evidence():
    from brain_v9.core.agent_kernel_v2.planner import classify_goal

    classification = classify_goal("Hello, how are you?", mode="read_only")
    assert classification == "general_reasoning"


# ---------------------------------------------------------------------------
# 7. Tool resolution contract
# ---------------------------------------------------------------------------

def test_resolve_tool_maps_canonical_read_tools():
    from brain_v9.core.agent_kernel_v2.planner import _resolve_tool

    canonical, args, note = _resolve_tool("repo_status_read")
    assert canonical == "repo_status_read"
    assert isinstance(args, dict)
    assert isinstance(note, str)


def test_resolve_tool_returns_empty_for_unknown_tool():
    from brain_v9.core.agent_kernel_v2.planner import _resolve_tool

    canonical, args, note = _resolve_tool("rm_rf_everything")
    assert canonical == ""
    assert args == {}
    assert "not found" in note.lower()


# ---------------------------------------------------------------------------
# 8. Mandatory multi-tool detection contract
# ---------------------------------------------------------------------------

def test_mandatory_tool_detection_preserves_required_output_schema():
    from brain_v9.core.agent_kernel_v2.mandatory_tools import parse_mandatory_tool_requests

    result = parse_mandatory_tool_requests(
        "Mandatory tool test: you must perform repo_status_read and route_probe http://127.0.0.1:8091/health."
    )
    assert isinstance(result, dict)
    assert "mandatory_detected" in result
    assert "requested_checks" in result
    assert result["mandatory_detected"] is True
    for check in result["requested_checks"]:
        assert "tool_name" in check or check.get("is_final_answer_requirement")
        if check.get("tool_name"):
            assert check["expected"] == "ok"
            assert check["requested_by_user"] is True


# ---------------------------------------------------------------------------
# 9. Safety: planner does not expose forbidden server surfaces
# ---------------------------------------------------------------------------

def test_planner_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/planner.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem(", "sub" + "process.run("]
    assert not any(token in src for token in forbidden)


def test_mandatory_tools_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/mandatory_tools.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem(", "sub" + "process.run("]
    assert not any(token in src for token in forbidden)


# ---------------------------------------------------------------------------
# Runner for direct invocation
# ---------------------------------------------------------------------------

_TESTS = [
    test_planner_classes_inventory_is_complete,
    test_build_plan_returns_required_schema,
    test_build_plan_for_repo_audit_schedules_read_only_tools,
    test_build_plan_for_financial_autonomy_diagnosis,
    test_build_plan_for_dashboard_diagnosis_schedules_read_only_probe,
    test_detect_explicit_tool_requests_extracts_named_tools,
    test_detect_explicit_tool_requests_ignores_generic_tool_words,
    test_diagnostic_phrases_have_required_intents,
    test_detect_diagnostic_phrases_maps_symptoms_to_tools,
    test_requires_generic_evidence_detects_brain_internal_questions,
    test_classify_goal_rejects_write_requests_in_read_only_mode,
    test_classify_goal_does_not_classify_greetings_as_evidence,
    test_resolve_tool_maps_canonical_read_tools,
    test_resolve_tool_returns_empty_for_unknown_tool,
    test_mandatory_tool_detection_preserves_required_output_schema,
    test_planner_source_does_not_import_server_starters,
    test_mandatory_tools_source_does_not_import_server_starters,
]


if __name__ == "__main__":
    passed = failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
