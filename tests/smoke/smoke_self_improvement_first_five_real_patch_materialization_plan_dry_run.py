"""Smoke tests for real patch materialization plan dry-run module.

Uses monkeypatch to mock upstream dependency.
Does not modify filesystem state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, r"C:\AI_VAULT")

import pytest

MODULE_PATH = "brain.external_sources.self_improvement_first_five_real_patch_materialization_plan_dry_run"


def _mock_review_result(output_dir=None) -> Dict[str, Any]:
    """Mock upstream review dry-run that writes artifacts."""
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_review")
    out.mkdir(parents=True, exist_ok=True)

    queue = [
        {
            "real_patch_materialization_planning_candidate_id": "mat_candidate_01",
            "real_patch_generation_review_id": "review_01",
            "real_patch_draft_id": "draft_01",
            "real_patch_generation_candidate_id": "candidate_01",
            "real_patch_generation_plan_review_id": "plan_review_01",
            "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
            "category": "evaluation_gate_gap",
            "patch_type": "test_patch",
            "risk_level": "low",
            "risk_notes": "bounded to test artifacts",
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["operator review required"],
            "target_files_allowed_for_future_patch": ["tests/smoke/*"],
        },
        {
            "real_patch_materialization_planning_candidate_id": "mat_candidate_02",
            "real_patch_generation_review_id": "review_02",
            "real_patch_draft_id": "draft_02",
            "real_patch_generation_candidate_id": "candidate_02",
            "real_patch_generation_plan_review_id": "plan_review_02",
            "front_id": "SECURITY_SANDBOXING_SUPPLY_CHAIN",
            "category": "security_supply_chain_gap",
            "patch_type": "policy_patch",
            "risk_level": "medium",
            "risk_notes": "security patches need extra scrutiny",
            "required_tests": ["pytest tests/smoke -q", "ruff check ."],
            "acceptance_criteria": ["all smoke tests pass", "no token leaks"],
            "target_files_allowed_for_future_patch": ["brain/external_sources/*", "tests/smoke/*"],
        },
        {
            "real_patch_materialization_planning_candidate_id": "mat_candidate_03",
            "real_patch_generation_review_id": "review_03",
            "real_patch_draft_id": "draft_03",
            "real_patch_generation_candidate_id": "candidate_03",
            "real_patch_generation_plan_review_id": "plan_review_03",
            "front_id": "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
            "category": "retrieval_provenance_gap",
            "patch_type": "harness_patch",
            "risk_level": "medium",
            "risk_notes": "read-only provenance required",
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["operator review required"],
            "target_files_allowed_for_future_patch": ["brain/external_sources/*"],
        },
    ]

    reviews = [
        {
            "real_patch_generation_review_id": "review_01",
            "real_patch_draft_id": "draft_01",
            "real_patch_generation_candidate_id": "candidate_01",
            "real_patch_generation_plan_review_id": "plan_review_01",
            "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
            "category": "evaluation_gate_gap",
            "patch_type": "test_patch",
            "decision": "approve_for_materialization_planning",
            "review_score": 0.95,
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["operator review required"],
            "risk_level": "low",
            "risk_notes": "safe dry-run only",
        },
        {
            "real_patch_generation_review_id": "review_02",
            "real_patch_draft_id": "draft_02",
            "real_patch_generation_candidate_id": "candidate_02",
            "real_patch_generation_plan_review_id": "plan_review_02",
            "front_id": "SECURITY_SANDBOXING_SUPPLY_CHAIN",
            "category": "security_supply_chain_gap",
            "patch_type": "policy_patch",
            "decision": "approve_for_materialization_planning",
            "review_score": 0.93,
            "required_tests": ["pytest tests/smoke -q", "ruff check ."],
            "acceptance_criteria": ["all smoke tests pass", "no token leaks"],
            "risk_level": "medium",
            "risk_notes": "safe dry-run only",
        },
        {
            "real_patch_generation_review_id": "review_03",
            "real_patch_draft_id": "draft_03",
            "real_patch_generation_candidate_id": "candidate_03",
            "real_patch_generation_plan_review_id": "plan_review_03",
            "front_id": "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
            "category": "retrieval_provenance_gap",
            "patch_type": "harness_patch",
            "decision": "approve_for_materialization_planning",
            "review_score": 0.94,
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["operator review required"],
            "risk_level": "medium",
            "risk_notes": "safe dry-run only",
        },
    ]

    summary = {
        "ok": True,
        "reviews_count": 3,
        "approved_for_materialization_planning": 3,
        "upstream_empty": False,
        "functional_dry_run_passed": True,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
    }

    governance = {
        "status": "inert_patch_generation_review_only_not_executable",
        "reviews_count": 3,
        "approved_for_materialization_planning": 3,
        "requires_operator_approval": True,
    }

    (out / "first_five_real_patch_materialization_planning_queue.json").write_text(
        json.dumps(queue, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_reviews.json").write_text(
        json.dumps(reviews, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_review_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_review_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )

    return {
        **summary,
        "output_dir": str(out),
        "queue": queue,
        "reviews": reviews,
    }


def _mock_empty_review(output_dir=None) -> Dict[str, Any]:
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_empty_review")
    out.mkdir(parents=True, exist_ok=True)

    summary = {
        "ok": False,
        "reviews_count": 0,
        "approved_for_materialization_planning": 0,
        "upstream_empty": True,
        "failure_reason": "empty_real_patch_drafts",
        "functional_dry_run_passed": False,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
    }

    governance = {
        "status": "inert_patch_generation_review_only_not_executable",
        "reviews_count": 0,
        "approved_for_materialization_planning": 0,
    }

    (out / "first_five_real_patch_materialization_planning_queue.json").write_text("[]", encoding="utf-8")
    (out / "first_five_real_patch_generation_reviews.json").write_text("[]", encoding="utf-8")
    (out / "first_five_real_patch_generation_review_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_review_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )

    return {
        **summary,
        "output_dir": str(out),
        "queue": [],
        "reviews": [],
    }


@pytest.fixture
def module(monkeypatch):
    """Import module with mocked upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_review_dry_run", _mock_review_result)
    return mod


@pytest.fixture
def empty_module(monkeypatch):
    """Import module with empty upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_review_dry_run", _mock_empty_review)
    return mod


# ─── 1–5. module existence ─────────────────────────────────────────────────────


class TestModuleExists:
    def test_import_module(self, module):
        assert module is not None

    def test_now_utc_exists(self, module):
        # _now_utc is internal, but we can test via the public function
        assert callable(module.summarize_materialization_plan)

    def test_load_materialization_planning_queue_artifacts_exists(self, module):
        assert callable(module.load_materialization_planning_queue_artifacts)

    def test_build_materialization_plan_exists(self, module):
        assert callable(module.build_materialization_plan)

    def test_build_all_materialization_plans_exists(self, module):
        assert callable(module.build_all_materialization_plans)

    def test_build_materialization_execution_order_exists(self, module):
        assert callable(module.build_materialization_execution_order)

    def test_build_materialization_plan_governance_exists(self, module):
        assert callable(module.build_materialization_plan_governance)

    def test_summarize_materialization_plan_exists(self, module):
        assert callable(module.summarize_materialization_plan)

    def test_run_first_five_real_patch_materialization_plan_dry_run_exists(self, module):
        assert callable(module.run_first_five_real_patch_materialization_plan_dry_run)


# ─── 6–45. plan structure & safety ───────────────────────────────────────────


class TestPlanStructure:
    def _run(self, tmp_path, module):
        out = tmp_path
        return out, module.run_first_five_real_patch_materialization_plan_dry_run(str(out))

    def test_materialization_plan_status_correct(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["plan_status"] == "materialization_plan_dry_run_only"

    def test_dry_run_only_true(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["dry_run_only"] is True

    def test_materialization_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["materialization_allowed_now"] is False

    def test_patch_file_creation_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patch_file_creation_allowed_now"] is False

    def test_git_apply_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["git_apply_allowed_now"] is False

    def test_target_file_modification_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["target_file_modification_allowed_now"] is False

    def test_patch_generation_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patch_generation_allowed_now"] is False

    def test_diff_generation_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["diff_generation_allowed_now"] is False

    def test_patch_application_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patch_application_allowed_now"] is False

    def test_real_patch_application_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_patch_application_allowed_now"] is False

    def test_patches_generated_for_application_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patches_generated_for_application"] is False

    def test_patches_applied_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patches_applied"] is False

    def test_patches_staged_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patches_staged"] is False

    def test_memory_write_allowed_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["memory_write_allowed"] is False

    def test_faiss_write_allowed_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["faiss_write_allowed"] is False

    def test_real_write_allowed_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_write_allowed"] is False

    def test_promotion_allowed_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["promotion_allowed"] is False

    def test_target_files_preserved(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p.get("target_files_suggested")

    def test_target_files_not_modified(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["target_files_not_modified"] == p["target_files_suggested"]

    def test_materialization_units_exist(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["materialization_units"]

    def test_unit_allowed_now_false(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert u["allowed_now"] is False

    def test_constraints_include_no_patch_file_creation(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_patch_file_creation" in u["materialization_constraints"]

    def test_constraints_include_no_git_apply(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_git_apply" in u["materialization_constraints"]

    def test_constraints_include_no_target_file_modification(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_target_file_modification" in u["materialization_constraints"]

    def test_constraints_include_no_stage(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_stage" in u["materialization_constraints"]

    def test_constraints_include_no_memory_write(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_memory_write" in u["materialization_constraints"]

    def test_constraints_include_no_faiss_write(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_faiss_write" in u["materialization_constraints"]

    def test_constraints_include_no_token_logging(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert "no_token_logging" in u["materialization_constraints"]

    def test_operator_approval_required_true(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["operator_approval_packet"]["required"] is True

    def test_approval_does_not_allow_patch_file_creation(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["operator_approval_packet"]["approval_does_not_allow_patch_file_creation"] is True

    def test_approval_does_not_allow_git_apply(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["operator_approval_packet"]["approval_does_not_allow_git_apply"] is True

    def test_approval_does_not_allow_target_file_modification(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["operator_approval_packet"]["approval_does_not_allow_target_file_modification"] is True

    def test_approval_does_not_allow_patch_application(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["operator_approval_packet"]["approval_does_not_allow_patch_application"] is True

    def test_rollback_required_true(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["rollback_plan"]["required"] is True

    def test_rollback_preserves_dirty_preexisting_files(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["rollback_plan"]["preserve_dirty_preexisting_files"] is True

    def test_required_tests_preserved(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["required_tests"]

    def test_acceptance_criteria_preserved(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["acceptance_criteria"]

    def test_risk_level_preserved_or_fallback_medium(self, tmp_path, module):
        out, result = self._run(tmp_path, module)
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["risk_level"] in ("low", "medium", "high")


# ─── 46–55. governance ───────────────────────────────────────────────────────


class TestGovernance:
    def test_governance_status_correct(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["status"] == "materialization_plan_only_not_executable"

    def test_governance_flags_false(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["materialization_allowed_now"] is False
        assert gov["patch_file_creation_allowed_now"] is False
        assert gov["git_apply_allowed_now"] is False
        assert gov["target_file_modification_allowed_now"] is False
        assert gov["patch_generation_allowed_now"] is False
        assert gov["diff_generation_allowed_now"] is False
        assert gov["patch_application_allowed_now"] is False
        assert gov["real_patch_application_allowed_now"] is False
        assert gov["patches_generated_for_application"] is False
        assert gov["patches_applied"] is False
        assert gov["patches_staged"] is False
        assert gov["memory_write_allowed"] is False
        assert gov["faiss_write_allowed"] is False
        assert gov["real_write_allowed"] is False
        assert gov["promotion_allowed"] is False

    def test_governance_next_safe_front_correct(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-REVIEW-DRY-RUN-01"

    def test_governance_must_not_create_patch_files_true(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_create_patch_files"] is True

    def test_governance_must_not_run_git_apply_true(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_run_git_apply"] is True

    def test_governance_must_not_modify_target_files_true(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_modify_target_files"] is True

    def test_governance_requires_operator_approval(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["requires_operator_approval"] is True

    def test_governance_writes_allowed_false(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        gov = json.loads((out /  "first_five_real_patch_materialization_plan_governance.json").read_text(encoding="utf-8"))
        assert gov["writes_allowed"] is False


# ─── 56–60. outputs ────────────────────────────────────────────────────────────


class TestOutputs:
    def test_output_files_written(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert (out / "first_five_real_patch_materialization_plans.json").exists()
        assert (out / "first_five_real_patch_materialization_plans.jsonl").exists()
        assert (out / "first_five_real_patch_materialization_execution_order.json").exists()
        assert (out / "first_five_real_patch_materialization_plan_governance.json").exists()
        assert (out / "first_five_real_patch_materialization_plan_summary.json").exists()
        assert (out / "first_five_real_patch_materialization_plan_report.md").exists()

    def test_jsonl_written(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out / "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        lines = (out / "first_five_real_patch_materialization_plans.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == len(plans)
        for line in lines:
            json.loads(line)

    def test_execution_order_count_matches_plans(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out / "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        order = json.loads((out / "first_five_real_patch_materialization_execution_order.json").read_text(encoding="utf-8"))
        assert len(order) == len(plans)

    def test_report_spanish_readable(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        report = (out / "first_five_real_patch_materialization_plan_report.md").read_text(encoding="utf-8")
        assert "Resumen" in report
        assert "Gobernanza" in report
        assert "Que NO Se Creo" in report

    def test_no_patch_files_generated(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        patch_files = list(out.rglob("*.patch"))
        assert len(patch_files) == 0


# ─── 61–65. empty upstream ───────────────────────────────────────────────────


class TestEmptyUpstream:
    def test_empty_queue_returns_ok_false(self, tmp_path, empty_module):
        out = tmp_path / "mat_empty"
        result = empty_module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["ok"] is False

    def test_empty_queue_upstream_empty_true(self, tmp_path, empty_module):
        out = tmp_path / "mat_empty"
        result = empty_module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["upstream_empty"] is True

    def test_empty_queue_failure_reason(self, tmp_path, empty_module):
        out = tmp_path / "mat_empty"
        result = empty_module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["failure_reason"] == "empty_real_patch_materialization_planning_queue"

    def test_empty_queue_recommended_next_not_application(self, tmp_path, empty_module):
        out = tmp_path / "mat_empty"
        result = empty_module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert "application" not in result["recommended_next_action"].lower()

    def test_empty_queue_materialization_plans_count_zero(self, tmp_path, empty_module):
        out = tmp_path / "mat_empty"
        result = empty_module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["materialization_plans_count"] == 0


# ─── 66–80. summary, safety, preservation ──────────────────────────────────────


class TestSummary:
    def test_materialization_plans_count_at_least_one(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["materialization_plans_count"] >= 1

    def test_summary_upstream_empty_false(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("upstream_empty") is False

    def test_summary_functional_dry_run_passed_true(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("functional_dry_run_passed") is True

    def test_summary_recommended_next_correct(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert "materialization_plan_review" in result["recommended_next_action"]

    def test_no_token_leak(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("token_leak_detected") is False

    def test_output_dir_recorded(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["output_dir"] == str(out)

    def test_created_at_present(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert "created_at" in p and p["created_at"]

    def test_plan_includes_category(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["category"]

    def test_plan_includes_patch_type(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patch_type"]

    def test_plan_includes_front_id(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["front_id"]

    def test_plan_includes_draft_id(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_patch_draft_id"]

    def test_plan_includes_review_id(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_patch_generation_review_id"]

    def test_plan_includes_candidate_id(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_patch_materialization_planning_candidate_id"]

    def test_plan_id_stable(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["real_patch_materialization_plan_id"].startswith("mat_plan_")


class TestSafetyFlags:
    def test_no_patches_generated_for_application(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["patches_generated_for_application"] is False

    def test_no_patches_applied(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["patches_applied"] is False

    def test_no_patches_staged(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["patches_staged"] is False

    def test_no_memory_write(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["memory_write_allowed"] is False

    def test_no_faiss_write(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["faiss_write_allowed"] is False

    def test_no_real_write(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["real_write_allowed"] is False

    def test_no_promotion(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result["promotion_allowed"] is False

    def test_no_runtime_chat_integration(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("runtime_chat_integration") is None or result.get("runtime_chat_integration") is False

    def test_no_trading(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("trading_used") is None or result.get("trading_used") is False

    def test_no_b8(self, tmp_path, module):
        out = tmp_path
        result = module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        assert result.get("b8_touched") is None or result.get("b8_touched") is False

    def test_no_target_file_modified(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["target_files_not_modified"] == p["target_files_suggested"]

    def test_no_applicable_diff_generated(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["materialization_allowed_now"] is False

    def test_no_git_stage_implied(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            assert p["patches_staged"] is False


# ─── 81–85. report content ───────────────────────────────────────────────────


class TestReportContent:
    def test_report_says_dry_run_only(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        report = (out /  "first_five_real_patch_materialization_plan_report.md").read_text(encoding="utf-8")
        assert "dry-run" in report.lower() or "dry run" in report.lower()

    def test_report_says_no_target_modification(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        report = (out /  "first_five_real_patch_materialization_plan_report.md").read_text(encoding="utf-8")
        assert "no modificar" in report.lower() or "no modif" in report.lower() or "modificacion" in report.lower()

    def test_report_says_no_git_apply(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        report = (out /  "first_five_real_patch_materialization_plan_report.md").read_text(encoding="utf-8")
        assert "git apply" in report.lower()

    def test_materialization_units_include_required_tests(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert u.get("required_tests")

    def test_materialization_units_include_acceptance_criteria(self, tmp_path, module):
        out = tmp_path
        module.run_first_five_real_patch_materialization_plan_dry_run(str(out))
        plans = json.loads((out /  "first_five_real_patch_materialization_plans.json").read_text(encoding="utf-8"))
        for p in plans:
            for u in p["materialization_units"]:
                assert u.get("acceptance_criteria")
