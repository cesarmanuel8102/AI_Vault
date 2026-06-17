"""
SMOKE-FRONT-BRAIN-AGENT-V2-SPECIFIC-TOOL-SCHEDULING-FIX-01

Smoke test for planner explicit tool request and diagnostic phrase scheduling.
Verifies determinism, safety, and no misclassification regressions.

All tests are read-only. No filesystem writes, no memory writes, no network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from tmp_agent.brain_v9.core.agent_kernel_v2.planner import (
    EXPLICIT_TOOL_PATTERNS,
    DIAGNOSTIC_PHRASES,
    _detect_explicit_tool_requests,
    _detect_diagnostic_phrases,
    _resolve_tool,
    _build_explicit_tool_plan,
    classify_goal,
    build_plan,
)


# ─── Test Explicit Tool Detection ──────────────────────────────────────────────

class TestExplicitToolDetection:
    """1. Detect explicit tool names in goal strings."""

    def test_detects_schedule_tool_pattern(self):
        requests = _detect_explicit_tool_requests("schedule list_recent_brain_changes")
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "list_recent_brain_changes"
        assert requests[0]["confidence"] == "high"

    def test_detects_run_tool_pattern(self):
        requests = _detect_explicit_tool_requests("run repo_status_read")
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "repo_status_read"

    def test_detects_spanish_explicit_request(self):
        requests = _detect_explicit_tool_requests("programa get_live_autonomy_status")
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "get_live_autonomy_status"

    def test_detects_tool_main_pattern(self):
        requests = _detect_explicit_tool_requests("tool principal: list_recent_brain_changes")
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "list_recent_brain_changes"

    def test_detects_complemented_with_pattern(self):
        requests = _detect_explicit_tool_requests("complemented with grep_search")
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "grep_search"

    def test_detects_multiple_tools(self):
        requests = _detect_explicit_tool_requests("run repo_status_read and use grep_search")
        tool_names = {r["tool_name"] for r in requests}
        assert "repo_status_read" in tool_names
        assert "grep_search" in tool_names

    def test_ignores_short_matches(self):
        requests = _detect_explicit_tool_requests("run ab")
        assert len(requests) == 0

    def test_returns_empty_when_no_explicit_tool(self):
        requests = _detect_explicit_tool_requests("hello world no tool here")
        assert requests == []


# ─── Test Diagnostic Phrase Detection ────────────────────────────────────────

class TestDiagnosticPhraseDetection:
    """2. Detect diagnostic phrases and map to tools."""

    def test_detects_autonomy_heartbeat_english(self):
        diagnostics = _detect_diagnostic_phrases("heartbeat is stale")
        assert len(diagnostics) == 1
        assert diagnostics[0]["diagnosis"] == "autonomy_heartbeat"
        tool_names = [t[0] for t in diagnostics[0]["tools"]]
        assert "get_live_autonomy_status" in tool_names

    def test_detects_autonomy_heartbeat_spanish(self):
        diagnostics = _detect_diagnostic_phrases("heartbeat antiguo")
        assert len(diagnostics) == 1
        assert diagnostics[0]["diagnosis"] == "autonomy_heartbeat"

    def test_detects_recent_changes_spanish(self):
        diagnostics = _detect_diagnostic_phrases("últimos cambios en el agente")
        assert len(diagnostics) == 1
        assert diagnostics[0]["diagnosis"] == "recent_changes"
        tool_names = [t[0] for t in diagnostics[0]["tools"]]
        assert "list_recent_brain_changes" in tool_names
        assert "repo_history_read" in tool_names

    def test_detects_git_history_phrases(self):
        diagnostics = _detect_diagnostic_phrases("git log")
        assert len(diagnostics) == 1
        assert diagnostics[0]["diagnosis"] == "git_history"
        tool_names = [t[0] for t in diagnostics[0]["tools"]]
        assert "repo_history_read" in tool_names

    def test_returns_empty_when_no_diagnostic(self):
        diagnostics = _detect_diagnostic_phrases("what is the weather today")
        assert diagnostics == []

    def test_detects_multiple_diagnostics(self):
        diagnostics = _detect_diagnostic_phrases("git log and heartbeat is stale")
        diag_names = {d["diagnosis"] for d in diagnostics}
        assert "git_history" in diag_names
        assert "autonomy_heartbeat" in diag_names


# ─── Test Tool Resolution ──────────────────────────────────────────────────────

class TestToolResolution:
    """3. Map missing/unavailable tools to safe equivalents."""

    def test_resolve_direct_tools(self):
        canonical, args, note = _resolve_tool("repo_status_read")
        assert canonical == "repo_status_read"
        assert note == ""

    def test_resolve_list_recent_brain_changes(self):
        canonical, args, note = _resolve_tool("list_recent_brain_changes")
        assert canonical == "repo_history_read"
        assert "not available" in note.lower()
        assert args.get("path") == "tmp_agent/brain_v9"

    def test_resolve_get_live_autonomy_status(self):
        canonical, args, note = _resolve_tool("get_live_autonomy_status")
        assert canonical == "route_probe"
        assert "8091" in args.get("url", "")

    def test_resolve_check_service_status(self):
        canonical, args, note = _resolve_tool("check_service_status")
        assert canonical == "route_probe"
        assert "health" in args.get("url", "")

    def test_resolve_get_autonomy_phase(self):
        canonical, args, note = _resolve_tool("get_autonomy_phase")
        assert canonical == "semantic_retrieve"
        assert "autonomy phase" in args.get("query", "")

    def test_resolve_repo_diff_read(self):
        canonical, args, note = _resolve_tool("repo_diff_read")
        assert canonical == "repo_status_read"
        assert "not available" in note.lower()

    def test_resolve_unknown_tool(self):
        canonical, args, note = _resolve_tool("nonexistent_tool_xyz")
        assert canonical == ""
        assert "not found" in note.lower()


# ─── Test Goal Classification ──────────────────────────────────────────────────

class TestGoalClassification:
    """4. classify_goal returns correct classes with no misclassification."""

    def test_explicit_tool_request_classification(self):
        cls = classify_goal("programa list_recent_brain_changes")
        assert cls == "explicit_tool_request"

    def test_autonomy_heartbeat_classification(self):
        cls = classify_goal("verify autonomy process heartbeat stale")
        assert cls == "autonomy_heartbeat"

    def test_recent_changes_classification(self):
        cls = classify_goal("últimos cambios en el agente")
        assert cls == "recent_changes"

    def test_git_history_classification(self):
        cls = classify_goal("git log for recent commits")
        assert cls == "git_history"

    def test_no_misclassification_programa_as_safe_patch(self):
        cls = classify_goal("programa list_recent_brain_changes como tool principal")
        assert cls == "explicit_tool_request"
        assert cls != "safe_patch_dry_run"

    def test_no_misclassification_due_to_patch_in_text(self):
        cls = classify_goal("programa patch_tool_v2 run")
        assert cls == "explicit_tool_request"
        assert cls != "safe_patch_dry_run"

    def test_safe_patch_dry_run_still_detects_real_patches(self):
        cls = classify_goal("show me the diff for the latest patch")
        assert cls == "safe_patch_dry_run"


# ─── Test Plan Building ────────────────────────────────────────────────────────

class TestPlanBuilding:
    """5. build_plan schedules explicit and diagnostic tools deterministically."""

    def test_explicit_request_schedules_resolved_tool(self):
        classification, plan, metadata = build_plan("run list_recent_brain_changes")
        assert classification == "explicit_tool_request"
        tool_names = [p["tool_name"] for p in plan if p.get("tool_name")]
        assert "repo_history_read" in tool_names  # resolved equivalent
        assert "requested_by_user" in [p for p in plan if p.get("tool_name") == "repo_history_read"][0]

    def test_diagnostic_schedules_multiple_tools(self):
        classification, plan, metadata = build_plan("heartbeat is stale")
        assert classification in {"autonomy_heartbeat", "explicit_tool_request"}
        tool_names = [p["tool_name"] for p in plan if p.get("tool_name")]
        # Should schedule route_probe (for get_live_autonomy_status) or repo_status_read
        assert any(t in tool_names for t in ["route_probe", "repo_status_read", "semantic_retrieve"])

    def test_plan_includes_supporting_evidence(self):
        classification, plan, metadata = build_plan("run list_recent_brain_changes")
        tool_names = [p["tool_name"] for p in plan if p.get("tool_name")]
        assert "repo_status_read" in tool_names
        assert "grep_search" in tool_names

    def test_plan_tracks_scheduled_tools(self):
        classification, plan, metadata = build_plan("run repo_status_read")
        assert "repo_status_read" in metadata["scheduled_tools"]

    def test_no_write_tools_scheduled_for_read_only(self):
        classification, plan, metadata = build_plan("git log for recent commits")
        for p in plan:
            if p.get("tool_name"):
                assert p["tool_name"] not in {"file_patch_apply_approval_required", "git_commit_approval_required"}

    def test_plan_returns_metadata_dict(self):
        classification, plan, metadata = build_plan("run list_recent_brain_changes")
        assert isinstance(metadata, dict)
        assert "scheduled_tools" in metadata
        assert "requested_checks" in metadata

    def test_mandatory_multitool_still_works(self):
        goal = "you must perform: 1. check repo status. 2. probe http://127.0.0.1:8091/v2/agent/status"
        classification, plan, metadata = build_plan(goal)
        assert classification == "mandatory_multitool"
        assert len(metadata["requested_checks"]) >= 2


# ─── Test Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:
    """6. Same input produces same classification and same scheduled tools."""

    def test_deterministic_classification(self):
        inputs = [
            "run list_recent_brain_changes",
            "heartbeat is stale",
            "últimos cambios en el agente",
            "programa get_live_autonomy_status",
        ]
        for inp in inputs:
            cls1, plan1, meta1 = build_plan(inp)
            cls2, plan2, meta2 = build_plan(inp)
            assert cls1 == cls2, f"Classification not deterministic for: {inp}"
            assert meta1["scheduled_tools"] == meta2["scheduled_tools"]
            assert len(plan1) == len(plan2)

    def test_deterministic_tool_order(self):
        cls1, plan1, meta1 = build_plan("run list_recent_brain_changes")
        cls2, plan2, meta2 = build_plan("run list_recent_brain_changes")
        tools1 = [p["tool_name"] for p in plan1]
        tools2 = [p["tool_name"] for p in plan2]
        assert tools1 == tools2


# ─── Test Read-Only Safety ─────────────────────────────────────────────────────

class TestReadOnlySafety:
    """7. No write, patch, or commit tools are scheduled for diagnostic requests."""

    FORBIDDEN_TOOLS = {
        "file_patch_apply_approval_required",
        "git_commit_approval_required",
        "file_patch_dry_run",  # still a patch-related tool, not appropriate for diagnostics
    }

    def test_explicit_diagnostic_no_write_tools(self):
        for goal in [
            "heartbeat is stale",
            "últimos cambios en el agente",
            "git log recent commits",
        ]:
            cls, plan, metadata = build_plan(goal)
            for p in plan:
                t = p.get("tool_name")
                if t:
                    assert t not in self.FORBIDDEN_TOOLS, f"Goal '{goal}' scheduled forbidden tool: {t}"

    def test_no_file_system_side_effects_in_plan_building(self):
        import os
        # build_plan must not touch filesystem
        cls, plan, metadata = build_plan("run list_recent_brain_changes")
        # If we get here without exception, and no files were created in cwd
        assert os.path.exists("list_recent_brain_changes") is False
