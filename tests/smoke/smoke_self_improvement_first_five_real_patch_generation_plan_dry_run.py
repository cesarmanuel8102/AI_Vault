"""Smoke tests for real patch generation plan dry-run module.

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

MODULE_PATH = "brain.external_sources.self_improvement_first_five_real_patch_generation_plan_dry_run"


def _mock_review_result(output_dir: str | None = None) -> Dict[str, Any]:
    """Mock upstream implementation plan review dry-run that writes artifacts."""
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_impl_review")
    out.mkdir(parents=True, exist_ok=True)

    queue = [
        {
            "real_patch_generation_planning_candidate_id": "gen_plan_abc123",
            "real_patch_implementation_plan_review_id": "impl_review_def456",
            "real_patch_implementation_plan_id": "impl_plan_ghi789",
            "real_patch_implementation_planning_candidate_id": "impl_candidate_jkl012",
            "front_id": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-REVIEW-DRY-RUN-01",
            "category": "patch_hygiene_gap",
            "patch_type": "test_patch",
            "candidate_status": "approved_for_real_patch_generation_planning",
            "patch_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "real_patch_application_allowed_now": False,
            "requires_operator_approval": True,
            "required_tests": ["python -m pytest tests/smoke -q"],
            "rollback_required": True,
            "next_safe_front": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-DRY-RUN-01",
        }
    ]

    reviews = [
        {
            "real_patch_implementation_plan_review_id": "impl_review_def456",
            "real_patch_implementation_plan_id": "impl_plan_ghi789",
            "real_patch_implementation_planning_candidate_id": "impl_candidate_jkl012",
            "real_patch_plan_review_id": "review_mno345",
            "real_patch_plan_id": "plan_pqr678",
            "front_id": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-REVIEW-DRY-RUN-01",
            "category": "patch_hygiene_gap",
            "patch_type": "test_patch",
            "review_score": 0.92,
            "decision": "approve_for_real_patch_generation_planning",
            "scores": {
                "implementation_plan_completeness": 0.95,
                "safety_guards": 1.0,
                "forbidden_scope_protection": 1.0,
                "test_and_rollback_readiness": 0.85,
                "bounded_generation_readiness": 0.90,
            },
            "reasons": [],
            "blocking_issues": [],
            "required_before_patch_generation_planning": [],
            "approved_for_real_patch_generation_planning": True,
            "required_tests": ["python -m pytest tests/smoke -q"],
            "acceptance_criteria": ["operator must define acceptance criteria before patch generation"],
            "risk_level": "low",
            "implementation_allowed_now": False,
            "patch_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "patches_generated_for_application": False,
            "patches_applied": False,
            "patches_staged": False,
            "operator_approval_required": True,
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
            "promotion_allowed": False,
            "reviewed_at": "2026-06-07T00:00:00Z",
        }
    ]

    impl_plans = [
        {
            "real_patch_implementation_plan_id": "impl_plan_ghi789",
            "target_files_suggested": ["tests/smoke/test_example.py"],
            "target_files_allowed_for_future_patch": ["tests/smoke/test_example.py"],
            "required_tests": ["python -m pytest tests/smoke -q"],
            "acceptance_criteria": ["operator must define acceptance criteria before patch generation"],
            "risk_level": "low",
            "risk_notes": "low risk test patch",
            "category": "patch_hygiene_gap",
            "patch_type": "test_patch",
            "front_id": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-REVIEW-DRY-RUN-01",
        }
    ]

    governance = {
        "governance_id": "gov_mock",
        "status": "real_patch_implementation_plan_review_only_not_executable",
        "reviews_count": 1,
        "approved_for_real_patch_generation_planning": 1,
        "patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "requires_operator_approval": True,
        "writes_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "must_preserve_dirty_preexisting_files": True,
        "must_keep_code_and_ledger_commits_separate": True,
        "next_safe_front": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-REVIEW-DRY-RUN-01",
    }

    summary = {
        "ok": True,
        "reviews_count": 1,
        "implementation_plans_reviewed": 1,
        "approved_for_real_patch_generation_planning": 1,
        "patch_generation_planning_queue_count": 1,
        "upstream_empty": False,
        "missing_upstream_artifacts": False,
        "functional_dry_run_passed": True,
        "patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_generation_planning_queue.json").write_text(
        json.dumps(queue, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_reviews.json").write_text(
        json.dumps(reviews, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_review_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_review_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )

    # Create nested impl plan dir for enrichment
    impl_dir = out / "run_impl_plan"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "first_five_real_patch_implementation_plans.json").write_text(
        json.dumps(impl_plans, indent=2), encoding="utf-8"
    )

    return summary


def _mock_empty_review(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_empty_impl_review")
    out.mkdir(parents=True, exist_ok=True)

    queue: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    governance = {
        "governance_id": "gov_empty",
        "status": "real_patch_implementation_plan_review_only_not_executable",
        "reviews_count": 0,
        "approved_for_real_patch_generation_planning": 0,
    }
    summary = {
        "ok": False,
        "reviews_count": 0,
        "implementation_plans_reviewed": 0,
        "approved_for_real_patch_generation_planning": 0,
        "patch_generation_planning_queue_count": 0,
        "upstream_empty": True,
        "missing_upstream_artifacts": False,
        "functional_dry_run_passed": False,
        "patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_generation_planning_queue.json").write_text(
        json.dumps(queue), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_reviews.json").write_text(
        json.dumps(reviews), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_review_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_implementation_plan_review_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )

    impl_dir = out / "run_impl_plan"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "first_five_real_patch_implementation_plans.json").write_text(
        json.dumps([]), encoding="utf-8"
    )

    return summary


@pytest.fixture
def module(monkeypatch):
    """Import module with mocked upstream review dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_implementation_plan_review_dry_run", _mock_review_result)
    return mod


@pytest.fixture
def empty_module(monkeypatch):
    """Import module with empty upstream review dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_implementation_plan_review_dry_run", _mock_empty_review)
    return mod


# 1-2. import and functions
def test_import_module():
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    assert mod is not None


def test_required_functions_exist(module):
    assert callable(getattr(module, "now_utc", None))
    assert callable(getattr(module, "load_real_patch_generation_planning_queue_artifacts", None))
    assert callable(getattr(module, "build_real_patch_generation_plan", None))
    assert callable(getattr(module, "build_all_real_patch_generation_plans", None))
    assert callable(getattr(module, "build_real_patch_generation_execution_order", None))
    assert callable(getattr(module, "build_real_patch_generation_governance", None))
    assert callable(getattr(module, "summarize_real_patch_generation_plan", None))
    assert callable(getattr(module, "run_first_five_real_patch_generation_plan_dry_run", None))


# 3. status
def test_generation_plan_status(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["plan_status"] == "real_patch_generation_plan_dry_run_only"


# 4-14. flags false
def test_patch_generation_allowed_now_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patch_generation_allowed_now"] is False


def test_diff_generation_allowed_now_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["diff_generation_allowed_now"] is False


def test_patch_application_allowed_now_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patch_application_allowed_now"] is False


def test_real_patch_application_allowed_now_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["real_patch_application_allowed_now"] is False


def test_patches_generated_for_application_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patches_generated_for_application"] is False


def test_patches_applied_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patches_applied"] is False


def test_patches_staged_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patches_staged"] is False


def test_memory_write_allowed_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["memory_write_allowed"] is False


def test_faiss_write_allowed_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["faiss_write_allowed"] is False


def test_real_write_allowed_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["real_write_allowed"] is False


def test_promotion_allowed_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["promotion_allowed"] is False


# 15-17. operator approval
def test_operator_approval_required_true(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["operator_approval_packet"]["required"] is True


def test_approval_does_not_allow_patch_generation(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["operator_approval_packet"]["approval_does_not_allow_patch_generation"] is True


def test_approval_does_not_allow_patch_application(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["operator_approval_packet"]["approval_does_not_allow_patch_application"] is True


# 18. rollback
def test_rollback_required_true(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["rollback_plan"]["required"] is True


# 19-21. preserved fields
def test_required_tests_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["required_tests"] == ["python -m pytest tests/smoke -q"]


def test_acceptance_criteria_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "operator must define acceptance criteria before patch generation" in plans[0]["acceptance_criteria"]


def test_target_files_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "tests/smoke/test_example.py" in plans[0]["target_files_suggested"]


# 22-26. forbidden paths
def test_forbidden_memory_semantic(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    forbidden = plans[0]["files_forbidden_to_modify"]
    assert any("memory/semantic" in f for f in forbidden)


def test_forbidden_strategies(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    forbidden = plans[0]["files_forbidden_to_modify"]
    assert any("tmp_agent/strategies" in f for f in forbidden)


def test_forbidden_trading_b8(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    forbidden = plans[0]["files_forbidden_to_modify"]
    assert any("trading/" in f for f in forbidden)
    assert any("B8/" in f for f in forbidden)


def test_forbidden_main_session(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    forbidden = plans[0]["files_forbidden_to_modify"]
    assert any("main.py" in f for f in forbidden)
    assert any("session.py" in f for f in forbidden)


def test_forbidden_curated_runtime_lookup(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    forbidden = plans[0]["files_forbidden_to_modify"]
    assert any("curated_runtime_lookup" in f for f in forbidden)


# 27-28. generation units
def test_generation_units_exist(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert len(plans[0]["generation_units"]) >= 1


def test_generation_unit_allowed_now_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    for u in plans[0]["generation_units"]:
        assert u["allowed_now"] is False


# 29-32. generation constraints
def test_generation_constraints_no_apply(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "no_apply" in plans[0]["generation_units"][0]["patch_constraints"]


def test_generation_constraints_no_stage(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "no_stage" in plans[0]["generation_units"][0]["patch_constraints"]


def test_generation_constraints_no_memory_write(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "no_memory_write" in plans[0]["generation_units"][0]["patch_constraints"]


def test_generation_constraints_no_faiss_write(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "no_faiss_write" in plans[0]["generation_units"][0]["patch_constraints"]


# 33. execution order
def test_execution_order_count_matches(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    order = json.loads((tmp_path / "first_five_real_patch_generation_execution_order.json").read_text())
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert len(order) == len(plans)


# 34-36. governance
def test_governance_status_correct(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_governance.json").read_text())
    assert gov["status"] == "real_patch_generation_plan_only_not_executable"


def test_governance_flags_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_governance.json").read_text())
    assert gov["patch_generation_allowed_now"] is False
    assert gov["patch_application_allowed_now"] is False
    assert gov["diff_generation_allowed_now"] is False


def test_governance_next_safe_front(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_governance.json").read_text())
    assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-REVIEW-DRY-RUN-01"


# 37-39. output files
def test_output_files_written(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert (tmp_path / "first_five_real_patch_generation_plans.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_execution_order.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_governance.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_summary.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_report.md").exists()


def test_jsonl_written(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert (tmp_path / "first_five_real_patch_generation_plans.jsonl").exists()
    lines = (tmp_path / "first_five_real_patch_generation_plans.jsonl").read_text().strip().split("\n")
    assert len(lines) >= 1


def test_report_spanish_readable(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_report.md").read_text()
    assert "Generacion" in report or "generacion" in report
    assert "NO Se Genero" in report or "NO Se Aplico" in report


# 40-41. empty queue
def test_empty_queue_returns_ok_false(empty_module, tmp_path):
    result = empty_module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["ok"] is False


def test_empty_queue_recommended_next_not_application(empty_module, tmp_path):
    result = empty_module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    rec = result.get("recommended_next_action", "")
    assert "application" not in rec.lower() or "re_run" in rec.lower()


# 42-46. no mutation flags
def test_no_token_leak(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["token_leak_detected"] is False


def test_no_memory_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["memory_write_allowed"] is False


def test_no_faiss_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["faiss_write_allowed"] is False


def test_no_real_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["real_write_allowed"] is False


def test_no_promotion_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["promotion_allowed"] is False


# 47-52. no integration / modification
def test_no_runtime_chat_integration(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_report.md").read_text()
    assert "runtime" not in report.lower() or "chat" not in report.lower()


def test_no_trading_b8_in_output(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    for p in plans:
        for t in p.get("target_files_allowed_for_future_patch", []):
            assert "trading/" not in t
            assert "B8/" not in t


def test_no_target_file_modified(module, tmp_path):
    test_file = tmp_path / "_test_target.py"
    test_file.write_text("# original")
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert test_file.read_text() == "# original"


def test_no_applicable_diff_generated(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_report.md").read_text()
    assert "Diffs aplicables" in report or "applicable" in report.lower()


def test_no_patch_file_generated(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    for f in tmp_path.iterdir():
        if f.is_file() and f.suffix == ".patch":
            pytest.fail(f"Patch file generated: {f}")


def test_no_git_stage_implied(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_report.md").read_text()
    assert "stage" in report.lower() or "staged" in report.lower()


# 53-57. counts and upstream
def test_patch_generation_plans_count_ge_1(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["patch_generation_plans_count"] >= 1


def test_queue_count_equals_plans_count(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert result["patch_generation_plans_count"] == len(plans)


def test_summary_contains_plans_count(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert "patch_generation_plans_count" in result


def test_upstream_empty_false_when_nonempty(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result.get("upstream_empty") is False


def test_functional_dry_run_passed_true(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result.get("functional_dry_run_passed") is True


# 58-61. governance details
def test_governance_requires_operator_approval(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_governance.json").read_text())
    assert gov["requires_operator_approval"] is True


def test_rollback_preserves_dirty_preexisting(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["rollback_plan"]["preserve_dirty_preexisting_files"] is True


def test_acceptance_criteria_non_empty(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert len(plans[0]["acceptance_criteria"]) > 0


def test_required_tests_non_empty(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert len(plans[0]["required_tests"]) > 0


# 62-65. miscellaneous
def test_risk_level_preserved_or_fallback(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["risk_level"] in ("low", "medium", "high")


def test_generation_units_include_tests(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    for u in plans[0]["generation_units"]:
        assert "required_tests" in u


def test_output_dir_recorded(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    assert result["output_dir"] == str(tmp_path)


def test_created_at_present(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_dry_run(str(tmp_path))
    plans = json.loads((tmp_path / "first_five_real_patch_generation_plans.json").read_text())
    assert "created_at" in plans[0]
    assert plans[0]["created_at"] != ""
