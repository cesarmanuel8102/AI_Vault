"""
Tests for brain_v9.brain.roadmap_governance (P6-16).
Covers pure helpers, legacy reconciliation, phase acceptance,
promotion logic, development status, and the orchestrator.
"""
import copy
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch, call

import pytest

import brain_v9.config as _cfg

# Module under test — imported AFTER conftest patches BASE_PATH
import brain_v9.brain.roadmap_governance as gov

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

NOW = "2025-01-15T12:00:00Z"

_PATCH_NOW = patch("brain_v9.brain.roadmap_governance._utc_now", return_value=NOW)


def _make_roadmap(
    phase="BL-03",
    stage="in_progress",
    roadmap_id="brain_lab_transition_v3",
    title="Stabilize Financial Telemetry",
    next_item="expand_governed_workers",
    work_items=None,
):
    return {
        "roadmap_id": roadmap_id,
        "active_program": roadmap_id,
        "current_phase": phase,
        "current_stage": stage,
        "active_title": title,
        "next_item": next_item,
        "counts": {},
        "work_items": work_items or [
            {"id": "BL-01", "status": "done", "title": "Align SSOT"},
            {"id": "BL-02", "status": "done", "title": "Make Utility"},
            {"id": "BL-03", "status": "in_progress", "title": "Stabilize", "room_id": "room_bl03", "objective": "obj3", "deliverable": "del3"},
            {"id": "BL-04", "status": "pending", "title": "Expand Workers", "room_id": "room_bl04"},
            {"id": "BL-05", "status": "pending", "title": "Version Missions"},
            {"id": "BL-06", "status": "pending", "title": "Capital Layers"},
            {"id": "BL-07", "status": "pending", "title": "Local First Routing"},
            {"id": "BL-08", "status": "pending", "title": "Maintain Readiness"},
        ],
    }


def _make_cycle(**overrides):
    base = {
        "current_phase": "BL-03",
        "phase": "BL-03",
        "phase_id": "BL-03",
        "current_stage": "in_progress",
        "stage": "in_progress",
        "active_title": "Stabilize",
        "next_item": "expand_governed_workers",
        "room_id": "room_bl03",
    }
    base.update(overrides)
    return base


def _make_acceptance(accepted=True, promote_to="BL-04", reason="all checks pass", checks=None):
    return {
        "accepted": accepted,
        "promote_to": promote_to,
        "acceptance_reason": reason,
        "checks": checks or [],
    }


def _make_phase_spec(evaluator_status="implemented", phase_id="BL-03", acceptance_mode="evidence", spec_path=None, checks=None):
    return {
        "phase_id": phase_id,
        "evaluator_status": evaluator_status,
        "acceptance_mode": acceptance_mode,
        "spec_path": spec_path or f"/specs/{phase_id}.json",
        "checks": checks or [],
    }


# ===================================================================
# _recalculate_counts
# ===================================================================

class TestRecalculateCounts:
    def test_empty_list(self):
        assert gov._recalculate_counts([]) == {"total": 0, "done": 0, "in_progress": 0, "pending": 0, "blocked": 0}

    def test_mixed_statuses(self):
        items = [
            {"status": "done"},
            {"status": "done"},
            {"status": "in_progress"},
            {"status": "pending"},
            {"status": "blocked"},
        ]
        result = gov._recalculate_counts(items)
        assert result == {"total": 5, "done": 2, "in_progress": 1, "pending": 1, "blocked": 1}

    def test_unknown_statuses_counted_in_total_only(self):
        items = [{"status": "cancelled"}, {"status": "done"}]
        result = gov._recalculate_counts(items)
        assert result["total"] == 2
        assert result["done"] == 1
        assert result["cancelled"] if "cancelled" in result else True  # unknown not tracked
        # Ensure unknown status is NOT a key
        assert "cancelled" not in result

    def test_all_done(self):
        items = [{"status": "done"}] * 4
        assert gov._recalculate_counts(items)["done"] == 4

    def test_no_status_key(self):
        items = [{"id": "x"}, {"status": "done"}]
        result = gov._recalculate_counts(items)
        assert result["total"] == 2
        assert result["done"] == 1

    def test_single_item_in_progress(self):
        items = [{"status": "in_progress"}]
        result = gov._recalculate_counts(items)
        assert result == {"total": 1, "done": 0, "in_progress": 1, "pending": 0, "blocked": 0}


# ===================================================================
# _phase_artifact_path
# ===================================================================

class TestPhaseArtifactPath:
    def test_with_room_id(self):
        result = gov._phase_artifact_path("my_room", "BL-03", "complete")
        assert result.name == "bl03_complete.json"
        assert "my_room" in str(result)

    def test_without_room_id(self):
        result = gov._phase_artifact_path(None, "BL-05", "activation")
        assert result.name == "bl05_activation.json"
        assert "phase_bl_05" in str(result)

    def test_special_chars_in_phase_id(self):
        result = gov._phase_artifact_path(None, "BL-08", "complete")
        assert result.name == "bl08_complete.json"
        assert "phase_bl_08" in str(result)

    def test_path_is_under_rooms(self):
        result = gov._phase_artifact_path("r1", "BL-01", "x")
        assert "rooms" in str(result) or "state" in str(result)

    def test_lowercase_conversion(self):
        result = gov._phase_artifact_path(None, "BL-03", "Complete")
        assert "bl03" in result.name.lower()


# ===================================================================
# _current_phase_item
# ===================================================================

class TestCurrentPhaseItem:
    def test_found(self):
        roadmap = {"work_items": [{"id": "BL-03", "title": "X"}]}
        assert gov._current_phase_item(roadmap, "BL-03") == {"id": "BL-03", "title": "X"}

    def test_not_found(self):
        roadmap = {"work_items": [{"id": "BL-01"}]}
        assert gov._current_phase_item(roadmap, "BL-99") == {}

    def test_empty_work_items(self):
        assert gov._current_phase_item({"work_items": []}, "BL-01") == {}

    def test_no_work_items_key(self):
        assert gov._current_phase_item({}, "BL-01") == {}

    def test_multiple_items_returns_first_match(self):
        roadmap = {"work_items": [{"id": "BL-03", "v": 1}, {"id": "BL-03", "v": 2}]}
        assert gov._current_phase_item(roadmap, "BL-03")["v"] == 1

    def test_none_phase_id(self):
        roadmap = {"work_items": [{"id": "BL-01"}]}
        assert gov._current_phase_item(roadmap, None) == {}


# ===================================================================
# _stringify_detail
# ===================================================================

class TestStringifyDetail:
    def test_none(self):
        assert gov._stringify_detail(None) == "sin_detalle"

    def test_string(self):
        assert gov._stringify_detail("hello") == "hello"

    def test_empty_string(self):
        assert gov._stringify_detail("") == ""

    def test_dict_with_values(self):
        result = gov._stringify_detail({"a": 1, "b": "x"})
        assert "a=1" in result
        assert "b=x" in result

    def test_dict_all_empty(self):
        result = gov._stringify_detail({"a": None, "b": "", "c": [], "d": {}})
        assert result == "sin_detalle"

    def test_dict_partial(self):
        result = gov._stringify_detail({"a": 1, "b": None})
        assert "a=1" in result
        assert "b" not in result

    def test_non_string_non_dict(self):
        assert gov._stringify_detail(42) == "42"

    def test_list(self):
        assert gov._stringify_detail([1, 2]) == "[1, 2]"

    def test_bool(self):
        assert gov._stringify_detail(True) == "True"


# ===================================================================
# _check_repair_hint — all 12 kinds + unknown
# ===================================================================

class TestCheckRepairHint:
    def test_file_exists_with_detail(self):
        check = {"kind": "file_exists", "detail": {"file_path": "/a/b.json"}}
        result = gov._check_repair_hint(check)
        assert "/a/b.json" in result

    def test_file_exists_fallback_to_file_path_key(self):
        check = {"kind": "file_exists", "file_path": "/x.json", "detail": None}
        result = gov._check_repair_hint(check)
        assert "/x.json" in result

    def test_file_exists_no_detail_no_filepath(self):
        check = {"kind": "file_exists"}
        result = gov._check_repair_hint(check)
        assert "artifact" in result.lower() or "Emitir" in result

    def test_directory_file_count_gte(self):
        check = {"kind": "directory_file_count_gte", "directory": "/artifacts"}
        result = gov._check_repair_hint(check)
        assert "/artifacts" in result

    def test_recent_iso_utc(self):
        check = {"kind": "recent_iso_utc", "source": "roadmap", "path": "updated_utc"}
        result = gov._check_repair_hint(check)
        assert "roadmap" in result and "updated_utc" in result

    def test_present(self):
        check = {"kind": "present", "source": "cycle", "path": "phase_id"}
        result = gov._check_repair_hint(check)
        assert "cycle" in result and "phase_id" in result

    def test_bool_true(self):
        check = {"kind": "bool_true", "source": "policy", "path": "enabled"}
        result = gov._check_repair_hint(check)
        assert "true" in result.lower()

    def test_in_set(self):
        check = {"kind": "in_set", "source": "roadmap", "path": "stage", "allowed": ["active", "done"]}
        result = gov._check_repair_hint(check)
        assert "active" in result or "allowed" in result.lower()

    def test_list_type(self):
        check = {"kind": "list_type", "source": "roadmap", "path": "items"}
        result = gov._check_repair_hint(check)
        assert "lista" in result.lower()

    def test_list_length_gte(self):
        check = {"kind": "list_length_gte", "source": "utility", "path": "samples"}
        result = gov._check_repair_hint(check)
        assert "utility" in result

    def test_list_last_field_in_set(self):
        check = {"kind": "list_last_field_in_set", "source": "ledger", "path": "entries", "field": "status"}
        result = gov._check_repair_hint(check)
        assert "status" in result

    def test_list_any_field_in_set(self):
        check = {"kind": "list_any_field_in_set", "source": "ledger", "path": "entries", "field": "outcome"}
        result = gov._check_repair_hint(check)
        assert "outcome" in result

    def test_numeric_gte(self):
        check = {"kind": "numeric_gte", "source": "utility", "path": "u_value", "min": 0.5}
        result = gov._check_repair_hint(check)
        assert "0.5" in result

    def test_unknown_kind(self):
        check = {"kind": "magic_check"}
        result = gov._check_repair_hint(check)
        assert "Investigar" in result

    def test_no_kind(self):
        check = {}
        result = gov._check_repair_hint(check)
        assert "Investigar" in result


# ===================================================================
# _legacy_definitions
# ===================================================================

class TestLegacyDefinitions:
    def test_returns_8_items(self):
        defs = gov._legacy_definitions()
        assert len(defs) == 8

    def test_required_keys_present(self):
        for item in gov._legacy_definitions():
            assert "label" in item
            assert "path" in item
            assert "decision" in item
            assert "reason" in item
            assert "mapped_to" in item
            assert "visibility" in item

    def test_specific_labels(self):
        labels = [d["label"] for d in gov._legacy_definitions()]
        assert "runtime_v2" in labels
        assert "dashboard_px" in labels
        assert "financial_motor_v1" in labels
        assert "acceptance_and_evidence_framework_v2" in labels

    def test_all_decisions_valid(self):
        valid = {"archived_certified", "legacy_mapped_to_bl", "legacy_absorbed_into_bl"}
        for item in gov._legacy_definitions():
            assert item["decision"] in valid

    def test_mapped_to_is_list(self):
        for item in gov._legacy_definitions():
            assert isinstance(item["mapped_to"], list)

    def test_paths_are_path_objects(self):
        for item in gov._legacy_definitions():
            assert isinstance(item["path"], Path)


# ===================================================================
# reconcile_legacy_roadmaps
# ===================================================================

@_PATCH_NOW
class TestReconcileLegacyRoadmaps:
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_all_legacy_exist(self, mock_read, mock_write, _now):
        """When all legacy files have content, stamps legacy_governance on each."""
        mock_read.side_effect = lambda path, default=None: {
            "roadmap_id": "some_legacy",
            "current_phase": "X",
        }
        result = gov.reconcile_legacy_roadmaps()
        # 8 legacy + registry + roadmap (initial) => reads
        assert result["schema_version"] == "roadmap_legacy_reconciliation_v1"
        assert all(row["exists"] for row in result["legacy_roadmaps"])
        assert result["updated_utc"] == NOW

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_some_legacy_missing(self, mock_read, mock_write, _now):
        """Files returning {} are marked exists=False."""
        call_count = [0]
        def side_effect(path, default=None):
            call_count[0] += 1
            # First call is roadmap, return content
            if call_count[0] == 1:
                return {"roadmap_id": "bl_v3", "current_phase": "BL-03"}
            # Return empty for odd legacy files, content for even
            if call_count[0] % 2 == 0:
                return {}
            return {"roadmap_id": "leg", "phase": "P1"}
        mock_read.side_effect = side_effect
        result = gov.reconcile_legacy_roadmaps()
        missing = [r for r in result["legacy_roadmaps"] if not r.get("exists", True)]
        present = [r for r in result["legacy_roadmaps"] if r.get("exists", True)]
        assert len(missing) > 0
        assert len(present) > 0

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_registry_exists_with_roadmaps(self, mock_read, mock_write, _now):
        """When registry exists, updates roadmaps list and adds canonical if missing."""
        def side_effect(path, default=None):
            path_str = str(path)
            if "registry" in path_str:
                return {
                    "roadmaps": [
                        {"roadmap_id": "old_one", "state": "active"},
                    ]
                }
            if "roadmap.json" in path_str:
                return {"roadmap_id": "brain_lab_transition_v3", "current_phase": "BL-03"}
            return {"roadmap_id": "leg"}
        mock_read.side_effect = side_effect
        result = gov.reconcile_legacy_roadmaps()
        # Verify write_json was called for registry
        registry_writes = [c for c in mock_write.call_args_list if "registry" in str(c)]
        assert len(registry_writes) >= 1

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_registry_missing(self, mock_read, mock_write, _now):
        """Empty registry: no registry update written."""
        def side_effect(path, default=None):
            path_str = str(path)
            if "registry" in path_str:
                return {}  # registry missing
            if "roadmap.json" in path_str:
                return {"roadmap_id": "bl_v3", "current_phase": "BL-03"}
            return {"roadmap_id": "leg"}
        mock_read.side_effect = side_effect
        result = gov.reconcile_legacy_roadmaps()
        # When registry is empty, write_json should NOT be called with the registry path
        registry_path = gov.FILES["legacy_registry"]
        registry_writes = [c for c in mock_write.call_args_list if c[0][0] == registry_path]
        assert len(registry_writes) == 0

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_summary_counts(self, mock_read, mock_write, _now):
        mock_read.side_effect = lambda path, default=None: (
            {"roadmap_id": "bl_v3", "current_phase": "BL-03"}
            if "roadmap.json" in str(path) else {"roadmap_id": "x"}
        )
        result = gov.reconcile_legacy_roadmaps()
        s = result["summary"]
        assert s["archived_certified"] == 1
        assert s["legacy_mapped_to_bl"] == 5
        assert s["legacy_absorbed_into_bl"] == 2

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_canonical_id_fallback(self, mock_read, mock_write, _now):
        """Uses active_program when roadmap_id is missing."""
        mock_read.side_effect = lambda path, default=None: (
            {"active_program": "fallback_id", "current_phase": "BL-01"}
            if "roadmap.json" in str(path) else {"roadmap_id": "x"}
        )
        result = gov.reconcile_legacy_roadmaps()
        assert result["canonical_active_roadmap"] == "fallback_id"

    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_canonical_id_default(self, mock_read, mock_write, _now):
        """Uses 'brain_lab_transition_v3' when both roadmap_id and active_program are missing."""
        mock_read.side_effect = lambda path, default=None: (
            {"current_phase": "BL-01"}
            if "roadmap.json" in str(path) else {"roadmap_id": "x"}
        )
        result = gov.reconcile_legacy_roadmaps()
        assert result["canonical_active_roadmap"] == "brain_lab_transition_v3"


# ===================================================================
# evaluate_phase_acceptance
# ===================================================================

class TestEvaluatePhaseAcceptance:
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    def test_delegates_with_provided_state(self, mock_eval):
        mock_eval.return_value = {"accepted": True}
        state = {"roadmap": {"current_phase": "BL-03"}, "cycle": {}}
        result = gov.evaluate_phase_acceptance(state)
        mock_eval.assert_called_once_with("BL-03", state)
        assert result == {"accepted": True}

    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance._load_state")
    def test_delegates_with_default_state(self, mock_load, mock_eval):
        mock_load.return_value = {"roadmap": {"current_phase": "BL-05"}, "cycle": {}}
        mock_eval.return_value = {"accepted": False}
        result = gov.evaluate_phase_acceptance()
        mock_load.assert_called_once()
        mock_eval.assert_called_once_with("BL-05", mock_load.return_value)

    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    def test_returns_acceptance_result(self, mock_eval):
        expected = {"accepted": True, "promote_to": "BL-04", "checks": []}
        mock_eval.return_value = expected
        result = gov.evaluate_phase_acceptance({"roadmap": {"current_phase": "BL-03"}})
        assert result == expected


# ===================================================================
# _build_meta_brain_handoff
# ===================================================================

class TestBuildMetaBrainHandoff:
    def test_with_failed_checks(self):
        roadmap = _make_roadmap()
        phase_item = {"objective": "obj", "deliverable": "del"}
        failed = [{"id": "c1", "kind": "present", "source": "s", "path": "p", "detail": "missing"}]
        result = gov._build_meta_brain_handoff(
            roadmap, phase_item,
            {"promotion_state": "not_ready"},
            failed, "blocked", ["fix evidence"],
        )
        assert "blocking_checks=" in result
        assert "c1" in result
        assert "current_work=fix evidence" in result

    def test_without_failed_checks(self):
        roadmap = _make_roadmap()
        result = gov._build_meta_brain_handoff(
            roadmap, {}, {"promotion_state": "active"}, [], "active", [],
        )
        assert "blocking_checks=none" in result

    def test_with_current_work_items(self):
        roadmap = _make_roadmap()
        result = gov._build_meta_brain_handoff(
            roadmap, {}, {"promotion_state": "x"}, [], "active",
            ["item1", "item2"],
        )
        assert "item1 | item2" in result

    def test_without_current_work_items(self):
        roadmap = _make_roadmap()
        result = gov._build_meta_brain_handoff(
            roadmap, {}, {"promotion_state": "x"}, [], "active", [],
        )
        assert "current_work=" not in result

    def test_contains_phase_info(self):
        roadmap = _make_roadmap(phase="BL-05", title="Version Missions")
        result = gov._build_meta_brain_handoff(
            roadmap, {"objective": "o", "deliverable": "d"},
            {"promotion_state": "active"}, [], "active", [],
        )
        assert "BL-05" in result
        assert "Version Missions" in result

    def test_objective_and_deliverable_na_fallback(self):
        roadmap = _make_roadmap()
        result = gov._build_meta_brain_handoff(
            roadmap, {}, {"promotion_state": "x"}, [], "active", [],
        )
        assert "objective=n/a" in result
        assert "deliverable=n/a" in result


# ===================================================================
# _build_development_status — 5 work_status branches
# ===================================================================

@_PATCH_NOW
class TestBuildDevelopmentStatus:
    def test_completed(self, _now):
        roadmap = _make_roadmap(stage="done")
        pp = {"promotion_state": "terminal_phase_accepted", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "completed"
        assert result["blocker_count"] == 0

    def test_needs_phase_spec(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "phase_active_spec_draft", "acceptance": {"acceptance_reason": "no spec", "checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "needs_phase_spec"
        assert result["last_error"] == "no spec"

    def test_blocked(self, _now):
        failed = [{"id": "c1", "kind": "present", "source": "s", "path": "p", "detail": "missing", "passed": False}]
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": failed}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "blocked"
        assert result["blocker_count"] == 1
        assert len(result["blockers"]) == 1

    def test_transitioning(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "promoted", "to_phase": "BL-04", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "transitioning"

    def test_active_fallback(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"accepted": False, "acceptance_reason": "pending", "checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "active"
        assert result["last_error"] == "pending"

    def test_active_no_error_when_no_acceptance_false(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["work_status"] == "active"
        assert result["last_error"] is None

    def test_evidence_paths_present(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec(spec_path="/spec.json")
        result = gov._build_development_status(roadmap, pp, spec)
        assert isinstance(result["evidence_paths"], list)
        assert len(result["evidence_paths"]) > 0

    def test_meta_brain_handoff_present(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert "meta_brain_handoff" in result
        assert isinstance(result["meta_brain_handoff"], str)

    def test_blocked_with_multiple_checks(self, _now):
        failed = [
            {"id": f"c{i}", "kind": "present", "source": "s", "path": "p", "detail": f"d{i}", "passed": False}
            for i in range(6)
        ]
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": failed}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["blocker_count"] == 6
        # last_error joins at most first 3
        assert result["last_error"].count(";") <= 2  # up to 3 items separated by ;
        # current_work_items capped at 5
        assert len(result["current_work_items"]) <= 5

    def test_next_recommended_actions_empty_when_no_blockers(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["next_recommended_actions"] == []

    def test_schema_fields(self, _now):
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert result["schema_version"] == "roadmap_development_status_v1"
        assert result["roadmap_id"] == "brain_lab_transition_v3"
        assert result["phase_id"] == "BL-03"
        assert "evaluator_status" in result
        assert "acceptance_mode" in result


# ===================================================================
# _promote_bl_phase — pure transform
# ===================================================================

@_PATCH_NOW
class TestPromoteBlPhase:
    def test_normal_promotion_bl03_to_bl04(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, updated_c, artifacts = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_r["current_phase"] == "BL-04"
        assert updated_r["current_stage"] == "in_progress"

    def test_previous_item_gets_done(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, _, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        prev = next(i for i in updated_r["work_items"] if i["id"] == "BL-03")
        assert prev["status"] == "done"
        assert prev["completed_utc"] == NOW
        assert prev["autopromoted_completion"] is True

    def test_next_item_gets_in_progress(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, _, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        nxt = next(i for i in updated_r["work_items"] if i["id"] == "BL-04")
        assert nxt["status"] == "in_progress"
        assert nxt["started_utc"] == NOW

    def test_counts_recalculated(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, _, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_r["counts"]["done"] == 3  # BL-01, BL-02, BL-03
        assert updated_r["counts"]["in_progress"] == 1  # BL-04

    def test_artifacts_generated(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        _, _, artifacts = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert "completion_artifact_path" in artifacts
        assert "activation_artifact_path" in artifacts
        assert artifacts["completion_artifact"]["phase_id"] == "BL-03"
        assert artifacts["activation_artifact"]["phase_id"] == "BL-04"

    def test_bl_next_items_lookup(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, updated_c, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_r["next_item"] == gov.BL_NEXT_ITEMS["BL-04"]
        assert updated_c["next_item"] == gov.BL_NEXT_ITEMS["BL-04"]

    def test_cycle_updated(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        _, updated_c, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_c["current_phase"] == "BL-04"
        assert updated_c["phase"] == "BL-04"
        assert updated_c["phase_id"] == "BL-04"
        assert updated_c["current_stage"] == "in_progress"

    def test_does_not_mutate_original(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        original_phase = roadmap["current_phase"]
        gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert roadmap["current_phase"] == original_phase

    def test_completion_artifact_schema(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04", reason="all pass")
        _, _, artifacts = gov._promote_bl_phase(roadmap, cycle, acceptance)
        ca = artifacts["completion_artifact"]
        assert ca["schema_version"] == "brain_lab_phase_completion_v1"
        assert ca["autopromoted"] is True
        assert ca["promoted_to"] == "BL-04"

    def test_activation_artifact_schema(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        _, _, artifacts = gov._promote_bl_phase(roadmap, cycle, acceptance)
        aa = artifacts["activation_artifact"]
        assert aa["schema_version"] == "brain_lab_phase_activation_v1"
        assert aa["source_phase"] == "BL-03"
        assert aa["activation_mode"] == "autonomous_roadmap_promotion"


# ===================================================================
# _complete_terminal_phase — pure transform
# ===================================================================

@_PATCH_NOW
class TestCompleteTerminalPhase:
    def test_terminal_phase_bl08(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle(current_phase="BL-08")
        acceptance = _make_acceptance(promote_to=None, reason="terminal acceptance")
        updated_r, updated_c, artifacts = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert updated_r["current_stage"] == "done"
        assert updated_r["next_item"] is None

    def test_current_item_marked_done(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        updated_r, _, _ = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        item = next((i for i in updated_r["work_items"] if i["id"] == "BL-08"), None)
        assert item is not None
        assert item["status"] == "done"
        assert item["completed_utc"] == NOW
        assert item["autonomous_terminal_acceptance"] is True

    def test_cycle_set_to_done(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        _, updated_c, _ = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert updated_c["current_stage"] == "done"
        assert updated_c["stage"] == "done"
        assert updated_c["next_item"] is None

    def test_completion_artifact(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        _, _, artifacts = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert "completion_artifact_path" in artifacts
        ca = artifacts["completion_artifact"]
        assert ca["schema_version"] == "brain_lab_terminal_phase_completion_v1"
        assert ca["terminal_phase"] is True
        assert ca["phase_id"] == "BL-08"

    def test_no_activation_artifact(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        _, _, artifacts = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert "activation_artifact_path" not in artifacts
        assert "activation_artifact" not in artifacts

    def test_does_not_mutate_original(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert roadmap["current_stage"] == "in_progress"  # unchanged

    def test_counts_recalculated(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        updated_r, _, _ = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        # BL-08 was pending, now done -> 3 done (BL-01, BL-02, BL-08)
        assert updated_r["counts"]["total"] == 8


# ===================================================================
# promote_roadmap_if_ready — integration with heavy mocking
# ===================================================================

@_PATCH_NOW
class TestPromoteRoadmapIfReady:
    """Integration tests for the orchestrator function."""

    def _setup_mocks(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                     roadmap=None, cycle=None, acceptance=None, spec=None,
                     previous_promotion=None, activation_exists=False):
        rm = roadmap or _make_roadmap()
        cy = cycle or _make_cycle()
        acc = acceptance or _make_acceptance()
        sp = spec or _make_phase_spec()
        pp = previous_promotion or {}

        def read_side_effect(path, default=None):
            path_str = str(path)
            if "roadmap.json" in path_str and "roadmap_" not in path_str.split("roadmap.json")[0].split("/")[-1]:
                return copy.deepcopy(rm)
            if "cycle" in path_str:
                return copy.deepcopy(cy)
            if "utility_u_latest" in path_str:
                return {}
            if "utility_u_promotion" in path_str:
                return {}
            if "strategy_ranking" in path_str:
                return {}
            if "trading_autonomy" in path_str:
                return {}
            if "promotion_state" in path_str:
                return copy.deepcopy(pp)
            if "activation" in path_str:
                return {"next_item": "old_value"} if activation_exists else {}
            return default if default is not None else {}

        mock_read.side_effect = read_side_effect
        mock_ensure.return_value = {"specs_dir": "/specs"}
        mock_eval.return_value = copy.deepcopy(acc)
        mock_load_spec.return_value = copy.deepcopy(sp)

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_not_ready(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=False, promote_to=None, reason="checks failed")
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec)
            result = gov.promote_roadmap_if_ready()
        assert result["promotion"]["promotion_state"] == "not_ready"

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_spec_not_implemented(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        spec = _make_phase_spec(evaluator_status="draft")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, spec=spec)
            result = gov.promote_roadmap_if_ready()
        assert result["promotion"]["promotion_state"] == "phase_active_spec_draft"

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_accepted_with_promote_to(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=True, promote_to="BL-04", reason="all pass")
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec)
            result = gov.promote_roadmap_if_ready()
        assert result["promotion"]["promotion_state"] == "promoted"
        assert result["promotion"]["promoted"] is True
        assert result["promotion"]["from_phase"] == "BL-03"
        assert result["promotion"]["to_phase"] == "BL-04"

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_accepted_without_promote_to_terminal(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=True, promote_to=None, reason="terminal")
        spec = _make_phase_spec(evaluator_status="implemented", phase_id="BL-08")
        roadmap = _make_roadmap(phase="BL-08")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              roadmap=roadmap, acceptance=acceptance, spec=spec)
            result = gov.promote_roadmap_if_ready()
        assert result["promotion"]["promotion_state"] == "terminal_phase_accepted"

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_next_item_alignment(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        """When roadmap.next_item doesn't match BL_NEXT_ITEMS, it gets fixed."""
        roadmap = _make_roadmap(phase="BL-03", next_item="wrong_value")
        acceptance = _make_acceptance(accepted=False, promote_to=None, reason="x")
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              roadmap=roadmap, acceptance=acceptance, spec=spec)
            result = gov.promote_roadmap_if_ready()
        # The roadmap.json write should include the fixed next_item
        # (at least one write_json call for roadmap.json)
        roadmap_writes = [c for c in mock_write.call_args_list if "roadmap.json" in str(c)]
        assert len(roadmap_writes) >= 1

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_previous_promotion_state_handling(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        prev_promo = {
            "promoted": True,
            "from_phase": "BL-02",
            "to_phase": "BL-03",
            "updated_utc": "2025-01-10T00:00:00Z",
            "completion_artifact": "/old/completion.json",
            "activation_artifact": "/old/activation.json",
        }
        acceptance = _make_acceptance(accepted=False, promote_to=None, reason="x")
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec, previous_promotion=prev_promo)
            result = gov.promote_roadmap_if_ready()
        lt = result["promotion"].get("last_transition", {})
        assert lt.get("from_phase") == "BL-02"
        assert lt.get("to_phase") == "BL-03"

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_governance_status_schema(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=False)
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec)
            result = gov.promote_roadmap_if_ready()
        assert result["schema_version"] == "roadmap_governance_status_v1"
        assert "canonical" in result
        assert "promotion" in result
        assert "phase_spec" in result
        assert "legacy_reconciliation" in result
        assert "development_status" in result

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_writes_three_json_files_at_end(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=False)
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec)
            gov.promote_roadmap_if_ready()
        paths_written = [str(c[0][0]) for c in mock_write.call_args_list]
        # Must write promotion_state, governance_status, development_status
        assert any("promotion_state" in p for p in paths_written)
        assert any("governance_status" in p for p in paths_written)
        assert any("development_status" in p for p in paths_written)

    @patch("brain_v9.brain.roadmap_governance.load_phase_spec")
    @patch("brain_v9.brain.roadmap_governance.evaluate_phase_acceptance_from_specs")
    @patch("brain_v9.brain.roadmap_governance.ensure_phase_specs")
    @patch("brain_v9.brain.roadmap_governance.write_json")
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_promotion_writes_completion_and_activation(self, mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec, _now):
        acceptance = _make_acceptance(accepted=True, promote_to="BL-04")
        spec = _make_phase_spec(evaluator_status="implemented")
        with patch.object(Path, "exists", return_value=False):
            self._setup_mocks(mock_read, mock_write, mock_ensure, mock_eval, mock_load_spec,
                              acceptance=acceptance, spec=spec)
            gov.promote_roadmap_if_ready()
        paths_written = [str(c[0][0]) for c in mock_write.call_args_list]
        assert any("complete" in p for p in paths_written)
        assert any("activation" in p for p in paths_written)


# ===================================================================
# read_roadmap_governance_status
# ===================================================================

class TestReadRoadmapGovernanceStatus:
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_returns_governance_status(self, mock_read):
        mock_read.return_value = {"schema_version": "roadmap_governance_status_v1", "data": "x"}
        result = gov.read_roadmap_governance_status()
        assert result["schema_version"] == "roadmap_governance_status_v1"

    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_returns_empty_when_missing(self, mock_read):
        mock_read.return_value = {}
        result = gov.read_roadmap_governance_status()
        assert result == {}


# ===================================================================
# BL_NEXT_ITEMS constant
# ===================================================================

class TestBLNextItems:
    def test_has_8_entries(self):
        assert len(gov.BL_NEXT_ITEMS) == 8

    def test_all_keys_bl_format(self):
        for key in gov.BL_NEXT_ITEMS:
            assert key.startswith("BL-")

    def test_bl01_value(self):
        assert gov.BL_NEXT_ITEMS["BL-01"] == "align_ssot_runtime_and_control_plane_canonically"

    def test_bl08_value(self):
        assert gov.BL_NEXT_ITEMS["BL-08"] == "maintain_operational_readiness_and_auditability"


# ===================================================================
# FILES constant
# ===================================================================

class TestFilesConstant:
    def test_has_19_entries(self):
        assert len(gov.FILES) == 19

    def test_all_values_are_paths(self):
        for key, val in gov.FILES.items():
            assert isinstance(val, Path), f"FILES[{key}] is not a Path"


# ===================================================================
# _load_state
# ===================================================================

class TestLoadState:
    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_returns_expected_keys(self, mock_read):
        mock_read.return_value = {}
        result = gov._load_state()
        expected_keys = {"roadmap", "cycle", "utility_latest", "utility_gate", "strategy_ranking", "trading_policy"}
        assert set(result.keys()) == expected_keys

    @patch("brain_v9.brain.roadmap_governance.read_json")
    def test_reads_6_files(self, mock_read):
        mock_read.return_value = {}
        gov._load_state()
        assert mock_read.call_count == 6


# ===================================================================
# Additional edge-case tests
# ===================================================================

class TestEdgeCases:
    def test_recalculate_counts_all_blocked(self):
        items = [{"status": "blocked"}] * 3
        result = gov._recalculate_counts(items)
        assert result["blocked"] == 3
        assert result["total"] == 3

    def test_stringify_detail_dict_with_zero_value(self):
        # 0 is falsy in Python but NOT in (None, "", [], {})
        result = gov._stringify_detail({"score": 0})
        assert "score=0" in result

    def test_stringify_detail_dict_with_false_value(self):
        result = gov._stringify_detail({"active": False})
        assert "active=False" in result

    def test_phase_artifact_path_different_kinds(self):
        p1 = gov._phase_artifact_path(None, "BL-01", "complete")
        p2 = gov._phase_artifact_path(None, "BL-01", "activation")
        assert p1 != p2

    @_PATCH_NOW
    def test_promote_bl_phase_reconciled_reason(self, _now):
        roadmap = _make_roadmap(phase="BL-03")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, updated_c, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert "BL-03" in updated_r["reconciled_reason"]
        assert "BL-04" in updated_r["reconciled_reason"]

    @_PATCH_NOW
    def test_complete_terminal_reconciled_reason(self, _now):
        roadmap = _make_roadmap(phase="BL-08")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        updated_r, updated_c, _ = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert "BL-08" in updated_r["reconciled_reason"]
        assert "BL-08" in updated_c["reconciled_reason"]

    def test_check_repair_hint_file_exists_detail_not_dict(self):
        check = {"kind": "file_exists", "detail": "some_string", "file_path": "/x.json"}
        result = gov._check_repair_hint(check)
        assert "/x.json" in result

    @_PATCH_NOW
    def test_promote_bl_phase_with_unknown_promote_to(self, _now):
        """When promote_to is not in BL_NEXT_ITEMS, falls back to roadmap's next_item."""
        roadmap = _make_roadmap(phase="BL-03", next_item="fallback_item")
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-99")  # not in BL_NEXT_ITEMS
        updated_r, _, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_r["next_item"] == "fallback_item"

    @_PATCH_NOW
    def test_promote_bl_phase_when_previous_item_not_found(self, _now):
        """When current phase item doesn't exist in work_items."""
        roadmap = _make_roadmap(phase="BL-99", work_items=[
            {"id": "BL-04", "status": "pending", "title": "Expand", "room_id": "r4"},
        ])
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to="BL-04")
        updated_r, _, _ = gov._promote_bl_phase(roadmap, cycle, acceptance)
        assert updated_r["current_phase"] == "BL-04"

    @_PATCH_NOW
    def test_complete_terminal_phase_item_not_found(self, _now):
        """When current phase item not in work_items, still completes."""
        roadmap = _make_roadmap(phase="BL-99", work_items=[])
        cycle = _make_cycle()
        acceptance = _make_acceptance(promote_to=None)
        updated_r, updated_c, artifacts = gov._complete_terminal_phase(roadmap, cycle, acceptance)
        assert updated_r["current_stage"] == "done"

    def test_build_meta_brain_handoff_multiple_failed_checks(self):
        roadmap = _make_roadmap()
        failed = [
            {"id": f"c{i}", "kind": "present", "source": "s", "path": "p", "detail": f"d{i}"}
            for i in range(3)
        ]
        result = gov._build_meta_brain_handoff(
            roadmap, {}, {"promotion_state": "not_ready"}, failed, "blocked", [],
        )
        assert "c0" in result
        assert "c1" in result
        assert "c2" in result

    @_PATCH_NOW
    def test_development_status_evidence_paths_include_files(self, _now):
        """Evidence paths should include canonical file paths."""
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": []}, "updated_utc": NOW,
              "completion_artifact": "/artifact/complete.json"}
        spec = _make_phase_spec(spec_path="/spec/bl03.json")
        result = gov._build_development_status(roadmap, pp, spec)
        paths = result["evidence_paths"]
        assert any("roadmap" in p for p in paths)
        assert any("spec" in p for p in paths)

    @_PATCH_NOW
    def test_development_status_blocked_evidence_from_checks(self, _now):
        """Failed checks with file_path detail should appear in evidence_paths."""
        failed = [{"id": "c1", "kind": "file_exists", "source": "s", "path": "p",
                    "detail": {"file_path": "/evidence/missing.json"}, "passed": False}]
        roadmap = _make_roadmap()
        pp = {"promotion_state": "not_ready", "acceptance": {"checks": failed}, "updated_utc": NOW}
        spec = _make_phase_spec()
        result = gov._build_development_status(roadmap, pp, spec)
        assert any("missing.json" in p for p in result["evidence_paths"])


# ===================================================================
# _utc_now
# ===================================================================

class TestUtcNow:
    def test_returns_string(self):
        result = gov._utc_now()
        assert isinstance(result, str)

    def test_ends_with_z(self):
        result = gov._utc_now()
        assert result.endswith("Z")

    def test_is_iso_format(self):
        from datetime import datetime
        result = gov._utc_now()
        # Should parse without error
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt is not None
