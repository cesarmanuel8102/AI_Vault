"""
Comprehensive tests for brain_v9.brain.meta_improvement
Covers pure helpers, memory/model builders, gap logic, and public API.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

import pytest

import brain_v9.brain.meta_improvement as mi
from brain_v9.brain.meta_improvement import (
    _utc_now,
    _round,
    _clamp,
    _parse_utc,
    _hours_since,
    _gap,
    _build_memory_snapshot,
    _build_self_model,
    _build_gaps,
    _update_memory_resolution_state,
    _select_gap_method,
    _build_meta_roadmap,
    _build_handoff,
    refresh_meta_improvement_status,
    read_meta_improvement_status,
    append_meta_execution,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_state():
    """Minimal state dict that satisfies all builder functions."""
    return {
        "previous_meta_status": {},
        "roadmap": {"current_stage": "in_progress", "counts": {}},
        "roadmap_governance": {},
        "roadmap_dev": {"work_status": "active"},
        "utility_latest": {"u_proxy_score": 0.5},
        "utility_gate": {"blockers": []},
        "utility_governance_status": {"accepted_baseline": True},
        "strategy_ranking": {
            "top_strategy": {
                "sample_quality": 0.5,
                "consistency_score": 0.3,
                "expectancy": 0.1,
            }
        },
        "strategy_scorecards": {},
        "self_improvement_ledger": {"entries": []},
        "action_ledger": {"entries": []},
        "trading_policy": {
            "global_rules": {"paper_only": True, "live_trading_forbidden": True}
        },
        "ibkr_probe": {},
        "ibkr_order_check": {"order_api_ready": True},
        "po_bridge": {"captured_at_utc": _utc_now()},
        "execution_ledger": {"entries": []},
        "chat_product_status": {
            "accepted_baseline": True,
            "acceptance_checks": [],
            "work_status": "ready_for_chat_improvement",
        },
    }


def _minimal_memory():
    """Minimal memory dict for builders that need it."""
    return {
        "playbooks": [
            {"playbook_id": f"pb{i}", "title": f"PB {i}", "description": f"desc {i}"}
            for i in range(4)
        ],
        "lessons": [],
        "resolved_gaps": [],
        "recurring_gaps": {},
        "summary": {
            "playbook_count": 4,
            "lessons_count": 0,
            "promoted_changes": 0,
            "rolled_back_changes": 0,
            "validated_changes": 0,
            "meta_executions": 0,
            "last_successful_method": None,
        },
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. TestUtcNow
# ═════════════════════════════════════════════════════════════════════════════
class TestUtcNow:
    def test_ends_with_z(self):
        assert _utc_now().endswith("Z")

    def test_iso_format_parseable(self):
        raw = _utc_now()
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_no_plus_suffix(self):
        """Ensure +00:00 is replaced by Z."""
        assert "+00:00" not in _utc_now()


# ═════════════════════════════════════════════════════════════════════════════
# 2. TestRound
# ═════════════════════════════════════════════════════════════════════════════
class TestRound:
    def test_basic(self):
        assert _round(1.23456789) == 1.2346

    def test_custom_digits(self):
        assert _round(1.23456789, 2) == 1.23

    def test_negative(self):
        assert _round(-0.123456, 3) == -0.123

    def test_zero(self):
        assert _round(0.0) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 3. TestClamp
# ═════════════════════════════════════════════════════════════════════════════
class TestClamp:
    def test_within_range(self):
        assert _clamp(0.5) == 0.5

    def test_below(self):
        assert _clamp(-0.5) == 0.0

    def test_above(self):
        assert _clamp(1.5) == 1.0

    def test_exact_low_boundary(self):
        assert _clamp(0.0) == 0.0

    def test_exact_high_boundary(self):
        assert _clamp(1.0) == 1.0

    def test_custom_range(self):
        assert _clamp(5.0, low=2.0, high=4.0) == 4.0

    def test_custom_range_below(self):
        assert _clamp(1.0, low=2.0, high=4.0) == 2.0


# ═════════════════════════════════════════════════════════════════════════════
# 4. TestParseUtc
# ═════════════════════════════════════════════════════════════════════════════
class TestParseUtc:
    def test_valid_z_suffix(self):
        dt = _parse_utc("2025-06-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2025

    def test_valid_offset(self):
        dt = _parse_utc("2025-06-15T12:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_none_input(self):
        assert _parse_utc(None) is None

    def test_empty_string(self):
        assert _parse_utc("") is None

    def test_garbage(self):
        assert _parse_utc("not-a-date") is None


# ═════════════════════════════════════════════════════════════════════════════
# 5. TestHoursSince
# ═════════════════════════════════════════════════════════════════════════════
class TestHoursSince:
    def test_recent_timestamp(self):
        now_str = _utc_now()
        hours = _hours_since(now_str)
        assert hours is not None
        assert 0.0 <= hours < 0.05  # within ~3 minutes

    def test_old_timestamp(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        hours = _hours_since(old)
        assert hours is not None
        assert 4.9 < hours < 5.1

    def test_none_input(self):
        assert _hours_since(None) is None

    def test_garbage_input(self):
        assert _hours_since("garbage") is None


# ═════════════════════════════════════════════════════════════════════════════
# 6. TestGap
# ═════════════════════════════════════════════════════════════════════════════
class TestGap:
    def test_priority_formula(self):
        g = _gap("g1", "d1", "t", "d", "o", benefit=1.0, readiness=1.0,
                 execution_mode="internal", suggested_actions=[], evidence_paths=[])
        assert g["priority_score"] == _round(1.0 * 0.65 + 1.0 * 0.35)

    def test_priority_formula_unequal(self):
        g = _gap("g2", "d2", "t", "d", "o", benefit=0.8, readiness=0.4,
                 execution_mode="internal", suggested_actions=[], evidence_paths=[])
        expected = _round(0.8 * 0.65 + 0.4 * 0.35)
        assert g["priority_score"] == expected

    def test_all_fields_present(self):
        g = _gap("gid", "dom", "title", "desc", "obj",
                 benefit=0.9, readiness=0.8, execution_mode="internal_candidate",
                 suggested_actions=["a1"], evidence_paths=["p1"], target_metric="tm")
        for key in ("gap_id", "domain_id", "title", "description", "objective",
                     "benefit_score", "readiness_score", "priority_score",
                     "current_state", "execution_mode", "suggested_actions",
                     "blockers", "target_metric", "evidence_paths"):
            assert key in g

    def test_blockers_default_empty(self):
        g = _gap("g", "d", "t", "d", "o", 0.5, 0.5, "i", [], [])
        assert g["blockers"] == []

    def test_custom_blockers(self):
        g = _gap("g", "d", "t", "d", "o", 0.5, 0.5, "i", [], [],
                 blockers=["b1", "b2"])
        assert g["blockers"] == ["b1", "b2"]

    def test_custom_current_state(self):
        g = _gap("g", "d", "t", "d", "o", 0.5, 0.5, "i", [], [],
                 current_state="closed")
        assert g["current_state"] == "closed"

    def test_default_current_state(self):
        g = _gap("g", "d", "t", "d", "o", 0.5, 0.5, "i", [], [])
        assert g["current_state"] == "open"


# ═════════════════════════════════════════════════════════════════════════════
# 7. TestBuildMemorySnapshot
# ═════════════════════════════════════════════════════════════════════════════
class TestBuildMemorySnapshot:
    """Tests for _build_memory_snapshot."""

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_static_playbooks_always_present(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        for expected in ("validate_before_promote", "rollback_preserves_operability",
                         "phase_specs_enable_autopromotion", "paper_only_first"):
            assert expected in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_has_four_static_playbooks_minimum(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        mem = _build_memory_snapshot(state)
        assert len(mem["playbooks"]) >= 4

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_dynamic_playbook_improve_expectancy_below_threshold(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "improve_expectancy_or_reduce_penalties"}
            for _ in range(2)
        ]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "expectancy_tuning_iterative" not in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_dynamic_playbook_improve_expectancy_at_threshold(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "improve_expectancy_or_reduce_penalties"}
            for _ in range(3)
        ]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "expectancy_tuning_iterative" in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_dynamic_playbook_select_and_compare_below_threshold(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "select_and_compare_strategies"}
        ]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "compare_before_commit" not in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_dynamic_playbook_select_and_compare_at_threshold(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "select_and_compare_strategies"}
            for _ in range(2)
        ]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "compare_before_commit" in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_dynamic_playbook_meta_gap_delegation(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["execution_ledger"]["entries"] = [{"a": 1}, {"b": 2}]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "meta_gap_delegation_loop" in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_meta_gap_delegation_not_at_one(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["execution_ledger"]["entries"] = [{"a": 1}]
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert "meta_gap_delegation_loop" not in ids

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_lessons_generated_with_dynamic_playbooks(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "improve_expectancy_or_reduce_penalties"}
            for _ in range(3)
        ]
        mem = _build_memory_snapshot(state)
        assert len(mem["lessons"]) >= 1
        assert mem["lessons"][0]["lesson_id"] == "lesson_expectancy_tuning"

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_summary_counts(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["self_improvement_ledger"]["entries"] = [
            {"status": "promoted", "validation": "passed", "restart": "ok"},
            {"status": "rolled_back"},
        ]
        mem = _build_memory_snapshot(state)
        assert mem["summary"]["promoted_changes"] == 1
        assert mem["summary"]["rolled_back_changes"] == 1
        assert mem["summary"]["validated_changes"] == 1

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_deduplication_of_playbooks(self, mock_rj):
        # Previous memory already has a static playbook_id — ensure no duplication
        mock_rj.return_value = {
            "playbooks": [{"playbook_id": "validate_before_promote"}],
            "recurring_gaps": {},
            "resolved_gaps": [],
        }
        state = _minimal_state()
        mem = _build_memory_snapshot(state)
        ids = [p["playbook_id"] for p in mem["playbooks"]]
        assert ids.count("validate_before_promote") == 1

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_last_successful_method(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        state["action_ledger"]["entries"] = [
            {"status": "completed", "action_name": "first_method"},
            {"status": "failed", "action_name": "bad_method"},
            {"status": "completed", "action_name": "last_good"},
        ]
        mem = _build_memory_snapshot(state)
        assert mem["summary"]["last_successful_method"] == "last_good"

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_last_successful_method_none_when_empty(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        mem = _build_memory_snapshot(state)
        assert mem["summary"]["last_successful_method"] is None

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_schema_version(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        mem = _build_memory_snapshot(state)
        assert mem["schema_version"] == "brain_self_improvement_memory_v1"

    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_lessons_capped_at_six(self, mock_rj):
        mock_rj.return_value = {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
        state = _minimal_state()
        # Trigger all three dynamic playbooks (each adds a lesson)
        state["action_ledger"]["entries"] = (
            [{"status": "completed", "action_name": "improve_expectancy_or_reduce_penalties"} for _ in range(3)]
            + [{"status": "completed", "action_name": "select_and_compare_strategies"} for _ in range(2)]
        )
        state["execution_ledger"]["entries"] = [{"a": 1}, {"b": 2}]
        mem = _build_memory_snapshot(state)
        assert len(mem["lessons"]) <= 6


# ═════════════════════════════════════════════════════════════════════════════
# 8. TestBuildSelfModel
# ═════════════════════════════════════════════════════════════════════════════
class TestBuildSelfModel:
    def test_six_domains_present(self):
        state = _minimal_state()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        assert len(model["domains"]) == 6

    def test_domain_ids(self):
        state = _minimal_state()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        ids = {d["domain_id"] for d in model["domains"]}
        expected = {"utility_governance", "strategy_learning", "venue_execution",
                    "meta_governance", "self_improvement_memory", "chat_product"}
        assert ids == expected

    def test_overall_score_is_average(self):
        state = _minimal_state()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        domain_scores = [d["score"] for d in model["domains"]]
        expected = _round(sum(domain_scores) / len(domain_scores))
        assert model["overall_score"] == expected

    def test_healthy_utility_governance(self):
        state = _minimal_state()
        state["utility_governance_status"]["accepted_baseline"] = True
        state["utility_latest"]["u_proxy_score"] = 0.9
        state["utility_gate"]["blockers"] = []
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        ug = next(d for d in model["domains"] if d["domain_id"] == "utility_governance")
        assert ug["status"] == "healthy"

    def test_needs_work_utility_governance(self):
        state = _minimal_state()
        state["utility_governance_status"]["accepted_baseline"] = False
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        ug = next(d for d in model["domains"] if d["domain_id"] == "utility_governance")
        assert ug["status"] == "needs_work"

    def test_strategy_healthy_high_quality(self):
        state = _minimal_state()
        state["strategy_ranking"]["top_strategy"]["sample_quality"] = 0.9
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        sl = next(d for d in model["domains"] if d["domain_id"] == "strategy_learning")
        assert sl["status"] == "healthy"

    def test_strategy_needs_work_low_quality(self):
        state = _minimal_state()
        state["strategy_ranking"]["top_strategy"]["sample_quality"] = 0.5
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        sl = next(d for d in model["domains"] if d["domain_id"] == "strategy_learning")
        assert sl["status"] == "needs_work"

    def test_venue_execution_healthy(self):
        state = _minimal_state()
        state["ibkr_order_check"]["order_api_ready"] = True
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        ve = next(d for d in model["domains"] if d["domain_id"] == "venue_execution")
        assert ve["status"] == "healthy"

    def test_venue_execution_needs_work_no_po(self):
        state = _minimal_state()
        state["po_bridge"] = {"captured_at_utc": "2020-01-01T00:00:00Z"}
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        ve = next(d for d in model["domains"] if d["domain_id"] == "venue_execution")
        assert ve["status"] == "needs_work"

    def test_meta_governance_healthy(self):
        state = _minimal_state()
        state["roadmap"]["current_stage"] = "done"
        state["roadmap_dev"]["work_status"] = "completed"
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        mg = next(d for d in model["domains"] if d["domain_id"] == "meta_governance")
        assert mg["status"] == "healthy"
        assert mg["score"] == 1.0

    def test_self_improvement_memory_healthy(self):
        state = _minimal_state()
        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 5
        model = _build_self_model(state, mem)
        si = next(d for d in model["domains"] if d["domain_id"] == "self_improvement_memory")
        assert si["status"] == "healthy"

    def test_self_improvement_memory_needs_work(self):
        state = _minimal_state()
        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 2
        model = _build_self_model(state, mem)
        si = next(d for d in model["domains"] if d["domain_id"] == "self_improvement_memory")
        assert si["status"] == "needs_work"

    def test_chat_product_healthy(self):
        state = _minimal_state()
        state["chat_product_status"]["accepted_baseline"] = True
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        cp = next(d for d in model["domains"] if d["domain_id"] == "chat_product")
        assert cp["status"] == "healthy"

    def test_chat_product_needs_work(self):
        state = _minimal_state()
        state["chat_product_status"]["accepted_baseline"] = False
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        cp = next(d for d in model["domains"] if d["domain_id"] == "chat_product")
        assert cp["status"] == "needs_work"

    def test_schema_version(self):
        state = _minimal_state()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        assert model["schema_version"] == "brain_self_model_v1"

    def test_identity_present(self):
        state = _minimal_state()
        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        assert "identity" in model
        assert "current_mode" in model["identity"]


# ═════════════════════════════════════════════════════════════════════════════
# 9. TestBuildGaps
# ═════════════════════════════════════════════════════════════════════════════
class TestBuildGaps:
    def _run(self, state, self_model=None, memory=None, monkeypatch=None):
        """Helper to run _build_gaps with patched file existence."""
        if self_model is None:
            self_model = _build_self_model(state, memory or _minimal_memory())
        if memory is None:
            memory = _minimal_memory()
        return _build_gaps(state, self_model, memory)

    def test_strategy_sample_depth_gap_when_low_quality(self, monkeypatch):
        state = _minimal_state()
        state["strategy_ranking"]["top_strategy"]["sample_quality"] = 0.5
        # utility high enough to skip utility gaps
        state["utility_latest"]["u_proxy_score"] = 0.8
        # po_bridge fresh
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        # mock FILES paths
        mock_path_ug = MagicMock()
        mock_path_ug.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path_ug)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "strategy_sample_depth" in ids

    def test_no_strategy_gap_when_high_quality(self, monkeypatch):
        state = _minimal_state()
        state["strategy_ranking"]["top_strategy"]["sample_quality"] = 0.9
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mock_path_ug = MagicMock()
        mock_path_ug.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path_ug)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "strategy_sample_depth" not in ids

    def test_utility_sensitivity_gap_when_accepted_baseline(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.5
        state["utility_governance_status"]["accepted_baseline"] = True
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "utility_sensitivity_and_lift" in ids

    def test_utility_governance_contract_missing_gap(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.3
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "utility_governance_contract_missing" in ids

    def test_utility_baseline_finish_gap(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.3
        state["utility_governance_status"]["accepted_baseline"] = False
        state["utility_governance_status"]["acceptance_checks"] = [
            {"check_id": "ck1", "passed": False}
        ]
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "utility_governance_baseline_finish" in ids

    def test_pocket_option_freshness_gap_when_stale(self, monkeypatch):
        state = _minimal_state()
        state["po_bridge"]["captured_at_utc"] = "2020-01-01T00:00:00Z"
        state["utility_latest"]["u_proxy_score"] = 0.8
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "pocket_option_freshness" in ids

    def test_memory_playbook_depth_gap_when_few_playbooks(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 3
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "memory_playbook_depth" in ids

    def test_no_memory_playbook_depth_gap_when_enough(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 6
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "memory_playbook_depth" not in ids

    def test_chat_product_acceptance_missing_gap(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = False
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 6
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "chat_product_acceptance_missing" in ids

    def test_chat_product_quality_and_ux_gap(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        state["chat_product_status"]["accepted_baseline"] = True
        state["chat_product_status"]["work_status"] = "ready_for_chat_improvement"
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 6
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "chat_product_quality_and_ux" in ids

    def test_gaps_sorted_by_priority_descending(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.5
        state["po_bridge"]["captured_at_utc"] = "2020-01-01T00:00:00Z"
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        priorities = [g["priority_score"] for g in registry["open_gaps"]]
        assert priorities == sorted(priorities, reverse=True)

    def test_recurrence_count_incremented(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.5
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["recurring_gaps"] = {"utility_sensitivity_and_lift": 5}
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        gap = next(g for g in registry["open_gaps"] if g["gap_id"] == "utility_sensitivity_and_lift")
        assert gap["recurrence_count"] == 6

    def test_attempt_count_from_execution_ledger(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.5
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        state["execution_ledger"]["entries"] = [
            {"gap_id": "utility_sensitivity_and_lift"},
            {"gap_id": "utility_sensitivity_and_lift"},
        ]
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        gap = next(g for g in registry["open_gaps"] if g["gap_id"] == "utility_sensitivity_and_lift")
        assert gap["attempt_count"] == 2

    def test_summary_counts(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.5
        state["po_bridge"]["captured_at_utc"] = "2020-01-01T00:00:00Z"
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        assert registry["summary"]["open_count"] == len(registry["open_gaps"])
        assert registry["summary"]["open_count"] > 0

    def test_chat_product_baseline_finish_gap(self, monkeypatch):
        state = _minimal_state()
        state["utility_latest"]["u_proxy_score"] = 0.8
        state["po_bridge"]["captured_at_utc"] = _utc_now()
        state["chat_product_status"]["accepted_baseline"] = False
        state["chat_product_status"]["acceptance_checks"] = [
            {"check_id": "chk_ui", "passed": False}
        ]
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "utility_governance_status", mock_path)
        mock_path_cp = MagicMock()
        mock_path_cp.exists.return_value = True
        monkeypatch.setitem(mi.FILES, "chat_product_status", mock_path_cp)

        mem = _minimal_memory()
        mem["summary"]["playbook_count"] = 6
        model = _build_self_model(state, mem)
        registry = _build_gaps(state, model, mem)
        ids = [g["gap_id"] for g in registry["open_gaps"]]
        assert "chat_product_baseline_finish" in ids


# ═════════════════════════════════════════════════════════════════════════════
# 10. TestUpdateMemoryResolutionState
# ═════════════════════════════════════════════════════════════════════════════
class TestUpdateMemoryResolutionState:
    def test_resolved_gap_added(self):
        memory = {"resolved_gaps": [], "summary": {}, "recurring_gaps": {}}
        gap_registry = {"open_gaps": []}  # gap disappeared
        previous_status = {
            "gap_registry": {
                "open_gaps": [{"gap_id": "old_gap", "title": "Old", "priority_score": 0.5, "execution_mode": "internal"}]
            }
        }
        result = _update_memory_resolution_state(memory, gap_registry, previous_status)
        assert len(result["resolved_gaps"]) == 1
        assert result["resolved_gaps"][0]["gap_id"] == "old_gap"

    def test_no_duplicate_resolution(self):
        memory = {
            "resolved_gaps": [{"gap_id": "old_gap", "resolved_utc": "2025-01-01T00:00:00Z"}],
            "summary": {},
            "recurring_gaps": {},
        }
        gap_registry = {"open_gaps": []}
        previous_status = {
            "gap_registry": {
                "open_gaps": [{"gap_id": "old_gap", "title": "Old", "priority_score": 0.5}]
            }
        }
        result = _update_memory_resolution_state(memory, gap_registry, previous_status)
        assert sum(1 for r in result["resolved_gaps"] if r["gap_id"] == "old_gap") == 1

    def test_still_open_not_resolved(self):
        memory = {"resolved_gaps": [], "summary": {}, "recurring_gaps": {}}
        gap_registry = {"open_gaps": [{"gap_id": "still_open"}]}
        previous_status = {
            "gap_registry": {
                "open_gaps": [{"gap_id": "still_open", "title": "Still"}]
            }
        }
        result = _update_memory_resolution_state(memory, gap_registry, previous_status)
        assert len(result["resolved_gaps"]) == 0

    def test_max_eight_cap(self):
        memory = {
            "resolved_gaps": [{"gap_id": f"rg{i}"} for i in range(7)],
            "summary": {},
            "recurring_gaps": {},
        }
        gap_registry = {"open_gaps": []}
        previous_status = {
            "gap_registry": {
                "open_gaps": [
                    {"gap_id": "new1", "title": "N1"},
                    {"gap_id": "new2", "title": "N2"},
                ]
            }
        }
        result = _update_memory_resolution_state(memory, gap_registry, previous_status)
        # 7 existing + 2 new = 9, capped at 8
        assert len(result["resolved_gaps"]) == 8

    def test_summary_updated(self):
        memory = {"resolved_gaps": [], "summary": {}, "recurring_gaps": {"a": 1, "b": 2}}
        gap_registry = {"open_gaps": []}
        previous_status = {"gap_registry": {"open_gaps": []}}
        result = _update_memory_resolution_state(memory, gap_registry, previous_status)
        assert result["summary"]["resolved_gap_count"] == 0
        assert result["summary"]["recurring_gap_count"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# 11. TestSelectGapMethod
# ═════════════════════════════════════════════════════════════════════════════
class TestSelectGapMethod:
    def test_utility_gap_prefers_comparison(self):
        gap = {
            "gap_id": "utility_sensitivity_and_lift",
            "suggested_actions": ["improve_expectancy_or_reduce_penalties", "select_and_compare_strategies"],
        }
        memory = {
            "playbooks": [{"playbook_id": "compare_before_commit"}],
            "summary": {"last_successful_method": "improve_expectancy_or_reduce_penalties"},
        }
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] == "select_and_compare_strategies"
        assert "compare_before_commit" in result["selected_playbooks"]
        assert result["reason"] == "utility_gap_prefers_comparison_before_tuning"

    def test_utility_gap_reuses_expectancy_tuning(self):
        gap = {
            "gap_id": "utility_sensitivity_and_lift",
            "suggested_actions": ["improve_expectancy_or_reduce_penalties", "select_and_compare_strategies"],
        }
        memory = {
            "playbooks": [{"playbook_id": "expectancy_tuning_iterative"}],
            "summary": {"last_successful_method": "select_and_compare_strategies"},
        }
        result = _select_gap_method(gap, memory)
        # compare_before_commit not in playbooks, so fall to expectancy tuning
        assert result["selected_action"] == "improve_expectancy_or_reduce_penalties"
        assert result["reason"] == "utility_gap_reuses_expectancy_tuning_playbook"

    def test_utility_gap_fallback_when_no_playbooks(self):
        gap = {
            "gap_id": "utility_sensitivity_and_lift",
            "suggested_actions": ["improve_expectancy_or_reduce_penalties"],
        }
        memory = {"playbooks": [], "summary": {"last_successful_method": None}}
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] == "improve_expectancy_or_reduce_penalties"
        assert result["reason"] == "fallback_to_first_suggested_action"

    def test_chat_product_gap_routing(self):
        gap = {
            "gap_id": "chat_product_quality_and_ux",
            "domain_id": "chat_product",
            "suggested_actions": ["improve_chat_product_quality"],
        }
        memory = {"playbooks": [], "summary": {}}
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] == "improve_chat_product_quality"
        assert result["reason"] == "chat_product_gap_prefers_quality_iteration"

    def test_memory_gap_routing(self):
        gap = {
            "gap_id": "memory_playbook_depth",
            "domain_id": "self_improvement_memory",
            "suggested_actions": ["advance_meta_improvement_roadmap"],
        }
        memory = {"playbooks": [], "summary": {}}
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] == "advance_meta_improvement_roadmap"
        assert "meta_gap_delegation_loop" in result["selected_playbooks"]
        assert result["reason"] == "memory_gap_expands_meta_playbooks"

    def test_generic_fallback(self):
        gap = {
            "gap_id": "strategy_sample_depth",
            "domain_id": "strategy_learning",
            "suggested_actions": ["select_and_compare_strategies"],
        }
        memory = {"playbooks": [], "summary": {}}
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] == "select_and_compare_strategies"
        assert result["reason"] == "fallback_to_first_suggested_action"

    def test_no_suggested_actions(self):
        gap = {"gap_id": "something", "domain_id": "other", "suggested_actions": []}
        memory = {"playbooks": [], "summary": {}}
        result = _select_gap_method(gap, memory)
        assert result["selected_action"] is None

    def test_utility_comparison_skipped_when_last_was_same(self):
        """compare_before_commit is available but last_successful_method == select_and_compare_strategies so it picks comparison."""
        gap = {
            "gap_id": "utility_sensitivity_and_lift",
            "suggested_actions": ["improve_expectancy_or_reduce_penalties", "select_and_compare_strategies"],
        }
        memory = {
            "playbooks": [
                {"playbook_id": "compare_before_commit"},
                {"playbook_id": "expectancy_tuning_iterative"},
            ],
            "summary": {"last_successful_method": "select_and_compare_strategies"},
        }
        result = _select_gap_method(gap, memory)
        # last_successful_method == "select_and_compare_strategies", so the first condition
        # in utility_sensitivity_and_lift requires last != select_and_compare_strategies.
        # Falls to second branch: expectancy_tuning_iterative
        assert result["selected_action"] == "improve_expectancy_or_reduce_penalties"
        assert result["reason"] == "utility_gap_reuses_expectancy_tuning_playbook"


# ═════════════════════════════════════════════════════════════════════════════
# 12. TestBuildMetaRoadmap
# ═════════════════════════════════════════════════════════════════════════════
class TestBuildMetaRoadmap:
    def test_items_ordered_by_gap_priority(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {
            "open_gaps": [
                _gap("g1", "d1", "T1", "D1", "O1", 0.9, 0.9, "internal_candidate", ["a1"], ["p1"]),
                _gap("g2", "d2", "T2", "D2", "O2", 0.7, 0.7, "internal_candidate", ["a2"], ["p2"]),
            ]
        }
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["items"][0]["gap_id"] == "g1"
        assert roadmap["items"][1]["gap_id"] == "g2"

    def test_first_item_active_rest_queued(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {
            "open_gaps": [
                _gap("g1", "d1", "T1", "D1", "O1", 0.9, 0.9, "internal_candidate", ["a1"], ["p1"]),
                _gap("g2", "d2", "T2", "D2", "O2", 0.7, 0.7, "internal_candidate", ["a2"], ["p2"]),
            ]
        }
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["items"][0]["status"] == "active"
        assert roadmap["items"][1]["status"] == "queued"

    def test_work_status_observe_only_no_gaps(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {"open_gaps": []}
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["work_status"] == "observe_only"

    def test_work_status_blocked_needs_meta_brain(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {
            "open_gaps": [
                _gap("g1", "d1", "T1", "D1", "O1", 0.9, 0.9, "needs_meta_brain", [], ["p1"]),
            ]
        }
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["work_status"] == "blocked_needs_meta_brain"

    def test_work_status_internal_execution_ready(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {
            "open_gaps": [
                _gap("g1", "d1", "T1", "D1", "O1", 0.9, 0.9, "internal_candidate", ["a1"], ["p1"]),
            ]
        }
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["work_status"] == "internal_execution_ready"

    def test_top_item_present(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {
            "open_gaps": [
                _gap("g1", "d1", "T1", "D1", "O1", 0.9, 0.9, "internal_candidate", ["a1"], ["p1"]),
            ]
        }
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["top_item"] is not None
        assert roadmap["top_item"]["gap_id"] == "g1"

    def test_top_item_none_when_no_gaps(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {"open_gaps": []}
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["top_item"] is None

    def test_schema_version(self):
        state = _minimal_state()
        state["memory_snapshot"] = _minimal_memory()
        gap_registry = {"open_gaps": []}
        roadmap = _build_meta_roadmap(state, gap_registry)
        assert roadmap["schema_version"] == "brain_meta_roadmap_v1"


# ═════════════════════════════════════════════════════════════════════════════
# 13. TestBuildHandoff
# ═════════════════════════════════════════════════════════════════════════════
class TestBuildHandoff:
    def test_returns_string(self):
        status = {
            "top_gap": {"gap_id": "g1", "domain_id": "d1", "execution_mode": "internal",
                        "title": "T1", "objective": "O1", "priority_score": 0.9,
                        "benefit_score": 0.8, "readiness_score": 0.7,
                        "suggested_actions": ["a1"], "blockers": [],
                        "evidence_paths": ["p1"]},
            "roadmap": {"roadmap_id": "rid", "work_status": "internal_execution_ready"},
            "memory": {"playbooks": [], "lessons": [], "summary": {"last_successful_method": "m1"}},
        }
        result = _build_handoff(status)
        assert isinstance(result, str)

    def test_includes_key_fields(self):
        status = {
            "top_gap": {"gap_id": "g1", "domain_id": "d1", "execution_mode": "internal",
                        "title": "T1", "objective": "O1", "priority_score": 0.9,
                        "benefit_score": 0.8, "readiness_score": 0.7,
                        "suggested_actions": ["action_x"], "blockers": ["b1"],
                        "evidence_paths": ["evidence/path1"],
                        "recommended_method": "rm1", "method_selection_reason": "reason1"},
            "roadmap": {"roadmap_id": "rid", "work_status": "internal_execution_ready"},
            "memory": {"playbooks": [], "lessons": [], "summary": {"last_successful_method": "m1"}},
        }
        result = _build_handoff(status)
        assert "top_gap=g1" in result
        assert "work_status=internal_execution_ready" in result
        assert "action_x" in result
        assert "evidence/path1" in result

    def test_handles_empty_top_gap(self):
        status = {"top_gap": {}, "roadmap": {}, "memory": {"playbooks": [], "lessons": [], "summary": {}}}
        result = _build_handoff(status)
        assert isinstance(result, str)
        assert "top_gap=None" in result

    def test_includes_playbook_and_lesson(self):
        status = {
            "top_gap": {"gap_id": "g1", "domain_id": "d1", "execution_mode": "i",
                        "title": "T", "objective": "O", "priority_score": 0.5,
                        "benefit_score": 0.5, "readiness_score": 0.5,
                        "suggested_actions": [], "blockers": [], "evidence_paths": []},
            "roadmap": {"roadmap_id": "r", "work_status": "observe_only"},
            "memory": {
                "playbooks": [{"playbook_id": "pb1", "description": "desc1"}],
                "lessons": [{"lesson_id": "ls1", "observation": "obs1"}],
                "summary": {"last_successful_method": None},
            },
        }
        result = _build_handoff(status)
        assert "playbook::pb1" in result
        assert "lesson::ls1" in result


# ═════════════════════════════════════════════════════════════════════════════
# 14. TestRefreshMetaImprovementStatus
# ═════════════════════════════════════════════════════════════════════════════
class TestRefreshMetaImprovementStatus:
    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_returns_status_dict(self, mock_rj, mock_wj):
        mock_rj.side_effect = self._make_read_json_side_effect()
        result = refresh_meta_improvement_status()
        assert isinstance(result, dict)
        assert "schema_version" in result
        assert result["schema_version"] == "meta_improvement_status_v1"

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_writes_five_files(self, mock_rj, mock_wj):
        mock_rj.side_effect = self._make_read_json_side_effect()
        refresh_meta_improvement_status()
        assert mock_wj.call_count == 5

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_status_has_required_keys(self, mock_rj, mock_wj):
        mock_rj.side_effect = self._make_read_json_side_effect()
        result = refresh_meta_improvement_status()
        for key in ("self_model", "gap_registry", "roadmap", "memory",
                     "meta_brain_handoff", "mission"):
            assert key in result, f"Missing key: {key}"

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_reads_files(self, mock_rj, mock_wj):
        mock_rj.side_effect = self._make_read_json_side_effect()
        refresh_meta_improvement_status()
        # read_json called for state + memory snapshot build (internal call)
        assert mock_rj.call_count >= 17  # 17 state reads + 1 memory read

    @staticmethod
    def _make_read_json_side_effect():
        """Returns a side_effect function that provides reasonable defaults."""
        def _side_effect(path, default=None):
            path_str = str(path)
            if "execution_ledger" in path_str:
                return {"entries": []}
            if "action_ledger" in path_str or "autonomy_action_ledger" in path_str:
                return {"entries": []}
            if "self_improvement_ledger" in path_str:
                return {"entries": []}
            if "trading" in path_str:
                return {"global_rules": {"paper_only": True, "live_trading_forbidden": True}}
            if "utility_u_latest" in path_str:
                return {"u_proxy_score": 0.5}
            if "utility_u_promotion" in path_str:
                return {"blockers": []}
            if "utility_governance_status" in path_str:
                return {"accepted_baseline": True}
            if "strategy_ranking" in path_str:
                return {"top_strategy": {"sample_quality": 0.5, "consistency_score": 0.3, "expectancy": 0.1}}
            if "roadmap_development" in path_str:
                return {"work_status": "active"}
            if "roadmap" in path_str and "meta" not in path_str:
                return {"current_stage": "in_progress", "counts": {}}
            if "ibkr_order_check" in path_str or "ibkr_paper_order" in path_str:
                return {"order_api_ready": True}
            if "browser_bridge" in path_str:
                return {"captured_at_utc": _utc_now()}
            if "chat_product_status" in path_str:
                return {"accepted_baseline": True, "acceptance_checks": [], "work_status": "ready_for_chat_improvement"}
            if "brain_self_improvement_memory" in path_str:
                return {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []}
            if "meta_improvement_status" in path_str:
                return {}
            if default is not None:
                return default
            return {}
        return _side_effect


# ═════════════════════════════════════════════════════════════════════════════
# 15. TestReadMetaImprovementStatus
# ═════════════════════════════════════════════════════════════════════════════
class TestReadMetaImprovementStatus:
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_returns_cached_when_present(self, mock_rj):
        mock_rj.return_value = {"schema_version": "cached_status"}
        result = read_meta_improvement_status()
        assert result["schema_version"] == "cached_status"

    @patch("brain_v9.brain.meta_improvement.refresh_meta_improvement_status")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_refreshes_when_empty(self, mock_rj, mock_refresh):
        mock_rj.return_value = {}
        mock_refresh.return_value = {"schema_version": "refreshed"}
        result = read_meta_improvement_status()
        mock_refresh.assert_called_once()
        assert result["schema_version"] == "refreshed"

    @patch("brain_v9.brain.meta_improvement.refresh_meta_improvement_status")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_does_not_refresh_when_data_present(self, mock_rj, mock_refresh):
        mock_rj.return_value = {"data": True}
        read_meta_improvement_status()
        mock_refresh.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# 16. TestAppendMetaExecution
# ═════════════════════════════════════════════════════════════════════════════
class TestAppendMetaExecution:
    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_appends_entry(self, mock_rj, mock_wj):
        mock_rj.return_value = {
            "schema_version": "brain_meta_execution_ledger_v1",
            "entries": [{"existing": True}],
        }
        entry = {"gap_id": "g1", "action": "a1"}
        result = append_meta_execution(entry)
        assert len(result["entries"]) == 2
        assert result["entries"][-1] == entry

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_writes_ledger(self, mock_rj, mock_wj):
        mock_rj.return_value = {
            "schema_version": "brain_meta_execution_ledger_v1",
            "entries": [],
        }
        entry = {"gap_id": "g1"}
        append_meta_execution(entry)
        mock_wj.assert_called_once()

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_updates_timestamp(self, mock_rj, mock_wj):
        mock_rj.return_value = {
            "schema_version": "brain_meta_execution_ledger_v1",
            "entries": [],
        }
        entry = {"gap_id": "g1", "updated_utc": "2025-06-15T00:00:00Z"}
        result = append_meta_execution(entry)
        assert result["updated_utc"] == "2025-06-15T00:00:00Z"

    @patch("brain_v9.brain.meta_improvement.write_json")
    @patch("brain_v9.brain.meta_improvement.read_json")
    def test_uses_utc_now_when_no_timestamp(self, mock_rj, mock_wj):
        mock_rj.return_value = {
            "schema_version": "brain_meta_execution_ledger_v1",
            "entries": [],
        }
        entry = {"gap_id": "g1"}
        result = append_meta_execution(entry)
        assert result["updated_utc"].endswith("Z")
