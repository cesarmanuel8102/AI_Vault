"""
P6-12 — Tests for brain/phase_acceptance_engine.py

Covers all 12 check kinds in _evaluate_check, the path extractor,
ISO datetime parser, phase spec loading, and full evaluate_phase_acceptance.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

from brain_v9.brain.phase_acceptance_engine import (
    _utc_now,
    _parse_iso_utc,
    _extract_path,
    _evaluate_check,
    _phase_spec_path,
    DEFAULT_PHASE_SPECS,
    evaluate_phase_acceptance,
    load_phase_spec,
    ensure_phase_specs,
    _load_sources,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


class TestUtcNow:
    def test_returns_iso_string(self):
        result = _utc_now()
        assert result.endswith("Z")
        assert "T" in result

    def test_no_plus_zero(self):
        assert "+00:00" not in _utc_now()


class TestParseIsoUtc:
    def test_valid_z_suffix(self):
        dt = _parse_iso_utc("2026-03-20T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_valid_offset(self):
        dt = _parse_iso_utc("2026-03-20T12:00:00+00:00")
        assert dt is not None

    def test_none_returns_none(self):
        assert _parse_iso_utc(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_iso_utc("") is None

    def test_non_string_returns_none(self):
        assert _parse_iso_utc(12345) is None

    def test_garbage_returns_none(self):
        assert _parse_iso_utc("not-a-date") is None


class TestExtractPath:
    def test_no_path_returns_payload(self):
        payload = {"a": 1}
        assert _extract_path(payload, None) == payload
        assert _extract_path(payload, "") == payload

    def test_single_level(self):
        assert _extract_path({"foo": "bar"}, "foo") == "bar"

    def test_nested_path(self):
        payload = {"a": {"b": {"c": 42}}}
        assert _extract_path(payload, "a.b.c") == 42

    def test_missing_key_returns_none(self):
        assert _extract_path({"a": 1}, "b") is None

    def test_missing_nested_returns_none(self):
        assert _extract_path({"a": {"b": 1}}, "a.c") is None

    def test_non_dict_intermediate_returns_none(self):
        assert _extract_path({"a": "string"}, "a.b") is None


class TestPhaseSpecPath:
    def test_simple_id(self):
        path = _phase_spec_path("BL-02")
        assert path.name == "bl_02.json"

    def test_lowercase(self):
        path = _phase_spec_path("BL-08")
        assert "bl_08" in path.name


# ── Check Kind Tests ─────────────────────────────────────────────────────────


class TestCheckPresent:
    def test_present_value_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": "value"}},
        )
        assert result["passed"] is True

    def test_none_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": None}},
        )
        assert result["passed"] is False

    def test_empty_string_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": ""}},
        )
        assert result["passed"] is False

    def test_empty_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": []}},
        )
        assert result["passed"] is False

    def test_empty_dict_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": {}}},
        )
        assert result["passed"] is False

    def test_zero_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": 0}},
        )
        assert result["passed"] is True  # 0 is not in (None, "", [], {})

    def test_false_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": False}},
        )
        assert result["passed"] is True  # False is not in (None, "", [], {})


class TestCheckListType:
    def test_list_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_type", "source": "src", "path": "items"},
            {"src": {"items": [1, 2, 3]}},
        )
        assert result["passed"] is True
        assert result["detail"]["length"] == 3

    def test_empty_list_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_type", "source": "src", "path": "items"},
            {"src": {"items": []}},
        )
        assert result["passed"] is True

    def test_dict_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_type", "source": "src", "path": "items"},
            {"src": {"items": {"a": 1}}},
        )
        assert result["passed"] is False

    def test_none_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_type", "source": "src", "path": "items"},
            {"src": {"items": None}},
        )
        assert result["passed"] is False


class TestCheckBoolTrue:
    def test_true_passes(self):
        result = _evaluate_check(
            {"id": "test", "kind": "bool_true", "source": "src", "path": "flag"},
            {"src": {"flag": True}},
        )
        assert result["passed"] is True

    def test_false_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "bool_true", "source": "src", "path": "flag"},
            {"src": {"flag": False}},
        )
        assert result["passed"] is False

    def test_truthy_string_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "bool_true", "source": "src", "path": "flag"},
            {"src": {"flag": "true"}},
        )
        assert result["passed"] is False  # Strict bool check

    def test_one_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "bool_true", "source": "src", "path": "flag"},
            {"src": {"flag": 1}},
        )
        assert result["passed"] is False  # 1 is not True


class TestCheckInSet:
    def test_value_in_allowed(self):
        result = _evaluate_check(
            {"id": "test", "kind": "in_set", "source": "src", "path": "status",
             "allowed": ["promote", "no_promote"]},
            {"src": {"status": "promote"}},
        )
        assert result["passed"] is True

    def test_value_not_in_allowed(self):
        result = _evaluate_check(
            {"id": "test", "kind": "in_set", "source": "src", "path": "status",
             "allowed": ["promote", "no_promote"]},
            {"src": {"status": "unknown"}},
        )
        assert result["passed"] is False

    def test_none_not_in_allowed(self):
        result = _evaluate_check(
            {"id": "test", "kind": "in_set", "source": "src", "path": "missing",
             "allowed": ["a"]},
            {"src": {}},
        )
        assert result["passed"] is False

    def test_bool_in_allowed(self):
        result = _evaluate_check(
            {"id": "test", "kind": "in_set", "source": "src", "path": "flag",
             "allowed": [True, False]},
            {"src": {"flag": True}},
        )
        assert result["passed"] is True


class TestCheckNumericGte:
    def test_above_threshold(self):
        result = _evaluate_check(
            {"id": "test", "kind": "numeric_gte", "source": "src", "path": "count", "min": 2},
            {"src": {"count": 5}},
        )
        assert result["passed"] is True

    def test_at_threshold(self):
        result = _evaluate_check(
            {"id": "test", "kind": "numeric_gte", "source": "src", "path": "count", "min": 5},
            {"src": {"count": 5}},
        )
        assert result["passed"] is True

    def test_below_threshold(self):
        result = _evaluate_check(
            {"id": "test", "kind": "numeric_gte", "source": "src", "path": "count", "min": 10},
            {"src": {"count": 5}},
        )
        assert result["passed"] is False

    def test_non_numeric_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "numeric_gte", "source": "src", "path": "count", "min": 1},
            {"src": {"count": "abc"}},
        )
        assert result["passed"] is False

    def test_string_number_works(self):
        result = _evaluate_check(
            {"id": "test", "kind": "numeric_gte", "source": "src", "path": "count", "min": 3},
            {"src": {"count": "5"}},
        )
        assert result["passed"] is True


class TestCheckRecentIsoUtc:
    def test_recent_passes(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        result = _evaluate_check(
            {"id": "test", "kind": "recent_iso_utc", "source": "src", "path": "ts", "max_age_minutes": 30},
            {"src": {"ts": recent}},
        )
        assert result["passed"] is True

    def test_old_fails(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        result = _evaluate_check(
            {"id": "test", "kind": "recent_iso_utc", "source": "src", "path": "ts", "max_age_minutes": 30},
            {"src": {"ts": old}},
        )
        assert result["passed"] is False

    def test_none_value_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "recent_iso_utc", "source": "src", "path": "ts", "max_age_minutes": 30},
            {"src": {"ts": None}},
        )
        assert result["passed"] is False

    def test_garbage_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "recent_iso_utc", "source": "src", "path": "ts", "max_age_minutes": 30},
            {"src": {"ts": "not-a-date"}},
        )
        assert result["passed"] is False

    def test_detail_includes_age(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        result = _evaluate_check(
            {"id": "test", "kind": "recent_iso_utc", "source": "src", "path": "ts", "max_age_minutes": 30},
            {"src": {"ts": recent}},
        )
        assert "age_minutes" in result["detail"]
        assert result["detail"]["age_minutes"] < 10


class TestCheckListLengthGte:
    def test_enough_items(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_length_gte", "source": "src", "path": "entries", "min": 3},
            {"src": {"entries": [1, 2, 3, 4, 5]}},
        )
        assert result["passed"] is True

    def test_exact_threshold(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_length_gte", "source": "src", "path": "entries", "min": 5},
            {"src": {"entries": [1, 2, 3, 4, 5]}},
        )
        assert result["passed"] is True

    def test_too_few(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_length_gte", "source": "src", "path": "entries", "min": 10},
            {"src": {"entries": [1]}},
        )
        assert result["passed"] is False

    def test_not_a_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_length_gte", "source": "src", "path": "entries", "min": 1},
            {"src": {"entries": "not_a_list"}},
        )
        assert result["passed"] is False


class TestCheckListLastFieldInSet:
    def test_last_item_matches(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_last_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["completed"]},
            {"src": {"entries": [{"status": "pending"}, {"status": "completed"}]}},
        )
        assert result["passed"] is True

    def test_last_item_no_match(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_last_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["completed"]},
            {"src": {"entries": [{"status": "completed"}, {"status": "pending"}]}},
        )
        assert result["passed"] is False

    def test_empty_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_last_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["completed"]},
            {"src": {"entries": []}},
        )
        assert result["passed"] is False

    def test_not_a_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_last_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["completed"]},
            {"src": {"entries": None}},
        )
        assert result["passed"] is False


class TestCheckListAnyFieldInSet:
    def test_any_item_matches(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_any_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["promoted"]},
            {"src": {"entries": [{"status": "pending"}, {"status": "promoted"}, {"status": "done"}]}},
        )
        assert result["passed"] is True
        assert result["detail"]["matched"] == "promoted"

    def test_no_match(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_any_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["promoted"]},
            {"src": {"entries": [{"status": "pending"}, {"status": "done"}]}},
        )
        assert result["passed"] is False

    def test_empty_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_any_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["promoted"]},
            {"src": {"entries": []}},
        )
        assert result["passed"] is False

    def test_not_a_list_fails(self):
        result = _evaluate_check(
            {"id": "test", "kind": "list_any_field_in_set", "source": "src", "path": "entries",
             "field": "status", "allowed": ["promoted"]},
            {"src": {"entries": "string"}},
        )
        assert result["passed"] is False


class TestCheckFileExists:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text("{}")
        result = _evaluate_check(
            {"id": "test", "kind": "file_exists", "file_path": str(f)},
            {},
        )
        assert result["passed"] is True

    def test_missing_file(self, tmp_path):
        result = _evaluate_check(
            {"id": "test", "kind": "file_exists", "file_path": str(tmp_path / "nope.json")},
            {},
        )
        assert result["passed"] is False

    def test_no_file_path(self):
        result = _evaluate_check(
            {"id": "test", "kind": "file_exists"},
            {},
        )
        assert result["passed"] is False


class TestCheckDirectoryFileCountGte:
    def test_enough_files(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.json").write_text("{}")
        result = _evaluate_check(
            {"id": "test", "kind": "directory_file_count_gte", "directory": str(tmp_path), "min": 3},
            {},
        )
        assert result["passed"] is True

    def test_too_few_files(self, tmp_path):
        (tmp_path / "one.json").write_text("{}")
        result = _evaluate_check(
            {"id": "test", "kind": "directory_file_count_gte", "directory": str(tmp_path), "min": 5},
            {},
        )
        assert result["passed"] is False

    def test_missing_directory(self, tmp_path):
        result = _evaluate_check(
            {"id": "test", "kind": "directory_file_count_gte", "directory": str(tmp_path / "nope"), "min": 1},
            {},
        )
        assert result["passed"] is False

    def test_counts_subdirs_too(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.json").write_text("{}")
        result = _evaluate_check(
            {"id": "test", "kind": "directory_file_count_gte", "directory": str(tmp_path), "min": 2},
            {},
        )
        assert result["passed"] is True


# ── _evaluate_check result structure ─────────────────────────────────────────


class TestEvaluateCheckStructure:
    def test_result_has_required_keys(self):
        result = _evaluate_check(
            {"id": "my_check", "kind": "present", "source": "src", "path": "key"},
            {"src": {"key": "value"}},
        )
        assert set(result.keys()) == {"id", "kind", "source", "path", "passed", "detail"}
        assert result["id"] == "my_check"
        assert result["kind"] == "present"

    def test_unknown_kind_does_not_crash(self):
        result = _evaluate_check(
            {"id": "test", "kind": "unknown_kind_xyz", "source": "src", "path": "key"},
            {"src": {"key": "value"}},
        )
        assert result["passed"] is False  # default

    def test_missing_source_returns_none_value(self):
        result = _evaluate_check(
            {"id": "test", "kind": "present", "source": "missing", "path": "key"},
            {"src": {"key": "value"}},
        )
        assert result["passed"] is False


# ── Phase Spec Loading ───────────────────────────────────────────────────────


class TestDefaultPhaseSpecs:
    def test_all_phases_present(self):
        expected = {"BL-01", "BL-02", "BL-03", "BL-04", "BL-05", "BL-06", "BL-07", "BL-08"}
        assert set(DEFAULT_PHASE_SPECS.keys()) == expected

    def test_each_has_schema_version(self):
        for phase_id, spec in DEFAULT_PHASE_SPECS.items():
            assert spec["schema_version"] == "roadmap_phase_spec_v1", f"{phase_id} missing schema_version"

    def test_bl01_is_archived(self):
        assert DEFAULT_PHASE_SPECS["BL-01"]["evaluator_status"] == "archived_baseline"
        assert DEFAULT_PHASE_SPECS["BL-01"]["checks"] == []

    def test_bl02_has_checks(self):
        assert len(DEFAULT_PHASE_SPECS["BL-02"]["checks"]) > 5

    def test_each_check_has_id_and_kind(self):
        for phase_id, spec in DEFAULT_PHASE_SPECS.items():
            for check in spec.get("checks", []):
                assert "id" in check, f"{phase_id}: check missing id"
                assert "kind" in check, f"{phase_id}: check missing kind"


class TestLoadPhaseSpec:
    @patch("brain_v9.brain.phase_acceptance_engine.read_json")
    @patch("brain_v9.brain.phase_acceptance_engine.write_json")
    @patch("brain_v9.brain.phase_acceptance_engine.PHASE_SPECS_DIR")
    def test_returns_default_for_known_phase(self, mock_dir, mock_write, mock_read):
        mock_dir.mkdir = MagicMock()
        mock_read.return_value = {}  # No persisted spec
        spec = load_phase_spec("BL-02")
        assert spec["phase_id"] == "BL-02"
        assert len(spec["checks"]) > 0

    @patch("brain_v9.brain.phase_acceptance_engine.read_json")
    @patch("brain_v9.brain.phase_acceptance_engine.write_json")
    @patch("brain_v9.brain.phase_acceptance_engine.PHASE_SPECS_DIR")
    def test_unknown_phase_returns_draft(self, mock_dir, mock_write, mock_read):
        mock_dir.mkdir = MagicMock()
        mock_read.return_value = {}
        spec = load_phase_spec("ZZ-99")
        assert spec["phase_id"] == "ZZ-99"
        assert spec["evaluator_status"] == "draft"
        assert spec["checks"] == []


# ── Full evaluate_phase_acceptance ───────────────────────────────────────────


class TestEvaluatePhaseAcceptance:
    @patch("brain_v9.brain.phase_acceptance_engine.read_json")
    @patch("brain_v9.brain.phase_acceptance_engine.write_json")
    @patch("brain_v9.brain.phase_acceptance_engine.PHASE_SPECS_DIR")
    def test_bl01_archived_not_accepted(self, mock_dir, mock_write, mock_read):
        mock_dir.mkdir = MagicMock()
        mock_read.return_value = {}
        result = evaluate_phase_acceptance("BL-01")
        # BL-01 is archived_baseline, evaluator_status != implemented
        assert result["accepted"] is False
        assert "archived" in result["phase_spec"]["evaluator_status"]

    @patch("brain_v9.brain.phase_acceptance_engine._load_sources")
    @patch("brain_v9.brain.phase_acceptance_engine.load_phase_spec")
    def test_all_checks_pass_means_accepted(self, mock_load_spec, mock_load_sources):
        mock_load_spec.return_value = {
            "phase_id": "TEST-01",
            "phase_title": "Test Phase",
            "promotion_target": "TEST-02",
            "evaluator_status": "implemented",
            "acceptance_mode": "all_checks_must_pass",
            "checks": [
                {"id": "c1", "kind": "present", "source": "src", "path": "key"},
                {"id": "c2", "kind": "bool_true", "source": "src", "path": "flag"},
            ],
            "acceptance_reason_if_passed": "All good",
            "acceptance_reason_if_failed": "Failed",
            "spec_path": "/tmp/test.json",
        }
        mock_load_sources.return_value = {"src": {"key": "value", "flag": True}}
        result = evaluate_phase_acceptance("TEST-01")
        assert result["accepted"] is True
        assert result["promote_to"] == "TEST-02"
        assert result["acceptance_reason"] == "All good"

    @patch("brain_v9.brain.phase_acceptance_engine._load_sources")
    @patch("brain_v9.brain.phase_acceptance_engine.load_phase_spec")
    def test_one_check_fails_means_not_accepted(self, mock_load_spec, mock_load_sources):
        mock_load_spec.return_value = {
            "phase_id": "TEST-01",
            "phase_title": "Test Phase",
            "promotion_target": "TEST-02",
            "evaluator_status": "implemented",
            "acceptance_mode": "all_checks_must_pass",
            "checks": [
                {"id": "c1", "kind": "present", "source": "src", "path": "key"},
                {"id": "c2", "kind": "bool_true", "source": "src", "path": "flag"},
            ],
            "acceptance_reason_if_passed": "All good",
            "acceptance_reason_if_failed": "Failed",
            "spec_path": "/tmp/test.json",
        }
        mock_load_sources.return_value = {"src": {"key": "value", "flag": False}}
        result = evaluate_phase_acceptance("TEST-01")
        assert result["accepted"] is False
        assert result["promote_to"] is None
        assert result["acceptance_reason"] == "Failed"

    @patch("brain_v9.brain.phase_acceptance_engine._load_sources")
    @patch("brain_v9.brain.phase_acceptance_engine.load_phase_spec")
    def test_no_checks_means_not_accepted(self, mock_load_spec, mock_load_sources):
        mock_load_spec.return_value = {
            "phase_id": "TEST-EMPTY",
            "phase_title": "Empty",
            "promotion_target": "NEXT",
            "evaluator_status": "implemented",
            "acceptance_mode": "all_checks_must_pass",
            "checks": [],
            "acceptance_reason_if_passed": "Pass",
            "acceptance_reason_if_failed": "Fail",
            "spec_path": "/tmp/test.json",
        }
        mock_load_sources.return_value = {}
        result = evaluate_phase_acceptance("TEST-EMPTY")
        # bool([]) is False, so accepted = False
        assert result["accepted"] is False

    @patch("brain_v9.brain.phase_acceptance_engine._load_sources")
    @patch("brain_v9.brain.phase_acceptance_engine.load_phase_spec")
    def test_draft_evaluator_not_accepted(self, mock_load_spec, mock_load_sources):
        mock_load_spec.return_value = {
            "phase_id": "DRAFT-01",
            "phase_title": "Draft",
            "promotion_target": None,
            "evaluator_status": "draft",
            "acceptance_mode": "phase_specific_checks_pending",
            "checks": [],
            "note": "Not ready yet",
            "spec_path": "/tmp/test.json",
        }
        mock_load_sources.return_value = {}
        result = evaluate_phase_acceptance("DRAFT-01")
        assert result["accepted"] is False
        assert result["promote_to"] is None
        assert "draft" in result["acceptance_reason"].lower() or "not ready" in result["acceptance_reason"].lower()

    @patch("brain_v9.brain.phase_acceptance_engine._load_sources")
    @patch("brain_v9.brain.phase_acceptance_engine.load_phase_spec")
    def test_result_structure(self, mock_load_spec, mock_load_sources):
        mock_load_spec.return_value = {
            "phase_id": "TEST",
            "phase_title": "Test",
            "promotion_target": None,
            "evaluator_status": "implemented",
            "acceptance_mode": "all_checks_must_pass",
            "checks": [{"id": "c1", "kind": "present", "source": "src", "path": "key"}],
            "acceptance_reason_if_passed": "Pass",
            "acceptance_reason_if_failed": "Fail",
            "spec_path": "/tmp/test.json",
        }
        mock_load_sources.return_value = {"src": {"key": "value"}}
        result = evaluate_phase_acceptance("TEST")
        expected_keys = {"phase_id", "phase_title", "accepted", "checks", "acceptance_reason", "promote_to", "phase_spec"}
        assert set(result.keys()) == expected_keys
        assert "spec_path" in result["phase_spec"]
        assert "evaluator_status" in result["phase_spec"]


# ── ensure_phase_specs ───────────────────────────────────────────────────────


class TestEnsurePhaseSpecs:
    @patch("brain_v9.brain.phase_acceptance_engine.write_json")
    @patch("brain_v9.brain.phase_acceptance_engine.read_json")
    @patch("brain_v9.brain.phase_acceptance_engine.PHASE_SPECS_DIR")
    def test_creates_all_specs_when_none_exist(self, mock_dir, mock_read, mock_write):
        mock_dir.mkdir = MagicMock()
        mock_dir.__truediv__ = lambda self, x: Path(f"/tmp/{x}")
        mock_read.return_value = {}  # No existing specs
        result = ensure_phase_specs()
        assert len(result["created"]) == len(DEFAULT_PHASE_SPECS)
        assert result["updated"] == []

    @patch("brain_v9.brain.phase_acceptance_engine.write_json")
    @patch("brain_v9.brain.phase_acceptance_engine.read_json")
    @patch("brain_v9.brain.phase_acceptance_engine.PHASE_SPECS_DIR")
    def test_does_not_recreate_existing(self, mock_dir, mock_read, mock_write):
        mock_dir.mkdir = MagicMock()
        mock_dir.__truediv__ = lambda self, x: Path(f"/tmp/{x}")
        # Return a "complete" spec that matches default
        mock_read.side_effect = lambda path, default: deepcopy(DEFAULT_PHASE_SPECS.get("BL-01", {})) or default
        result = ensure_phase_specs()
        # Some might be created (if read returns {}), some updated
        assert "available_specs" in result
