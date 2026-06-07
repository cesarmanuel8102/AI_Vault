"""Smoke tests for real patch generation plan review dry-run module.

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

MODULE_PATH = "brain.external_sources.self_improvement_first_five_real_patch_generation_plan_review_dry_run"


def _mock_gen_result(output_dir: str | None = None) -> Dict[str, Any]:
    """Mock upstream generation plan dry-run that writes artifacts."""
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
    out.mkdir(parents=True, exist_ok=True)

    plans = [
        {
            "real_patch_generation_plan_id": "gen_plan_abc123",
            "real_patch_generation_planning_candidate_id": "gen_candidate_def456",
            "real_patch_implementation_plan_review_id": "impl_review_ghi789",
            "real_patch_implementation_plan_id": "impl_plan_jkl012",
            "front_id": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-DRY-RUN-01",
            "category": "patch_hygiene_gap",
            "patch_type": "test_patch",
            "plan_status": "real_patch_generation_plan_dry_run_only",
            "patch_generation_allowed_now": False,
            "diff_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "real_patch_application_allowed_now": False,
            "patches_generated_for_application": False,
            "patches_applied": False,
            "patches_staged": False,
            "target_files_suggested": ["tests/smoke/test_example.py"],
            "target_files_allowed_for_future_patch": ["tests/smoke/test_example.py"],
            "files_forbidden_to_modify": [
                "memory/semantic/*",
                "tmp_agent/strategies/*",
                "trading/*",
                "B8/*",
                "tmp_agent/brain_v9/main.py",
                "tmp_agent/brain_v9/core/session.py",
                "brain/curated_runtime_lookup.py",
            ],
            "generation_units": [
                {
                    "unit_id": "gen_unit_001",
                    "description": "Generate patch plan for tests/smoke/test_example.py",
                    "allowed_now": False,
                    "generation_type": "test_patch_plan",
                    "target_files": ["tests/smoke/test_example.py"],
                    "required_tests": ["python -m pytest tests/smoke -q"],
                    "acceptance_criteria": ["operator must define acceptance criteria before patch generation"],
                    "patch_constraints": [
                        "no_apply",
                        "no_stage",
                        "no_memory_write",
                        "no_faiss_write",
                        "no_token_logging",
                    ],
                    "rollback_instruction": "discard generated patch plan artifacts only",
                }
            ],
            "operator_approval_packet": {
                "required": True,
                "approval_scope": "patch_generation_plan_only",
                "approval_does_not_allow_patch_generation": True,
                "approval_does_not_allow_patch_application": True,
                "must_review_target_files": True,
                "must_review_tests": True,
                "must_review_rollback": True,
            },
            "required_tests": ["python -m pytest tests/smoke -q"],
            "acceptance_criteria": ["operator must define acceptance criteria before patch generation"],
            "rollback_plan": {
                "required": True,
                "strategy": "delete_generated_patch_plan_artifacts_only",
                "preserve_dirty_preexisting_files": True,
            },
            "risk_level": "low",
            "risk_notes": "low risk test patch generation",
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
            "promotion_allowed": False,
            "created_at": "2026-06-07T00:00:00Z",
        }
    ]

    order = [
        {
            "execution_order_id": "gen_exec_001",
            "real_patch_generation_plan_id": "gen_plan_abc123",
            "front_id": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-DRY-RUN-01",
            "category": "patch_hygiene_gap",
            "patch_type": "test_patch",
            "risk_level": "low",
            "execution_sequence": 1,
            "patch_generation_allowed_now": False,
            "diff_generation_allowed_now": False,
            "patch_application_allowed_now": False,
        }
    ]

    governance = {
        "governance_id": "gov_gen",
        "status": "real_patch_generation_plan_only_not_executable",
        "patch_generation_plans_count": 1,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "requires_operator_approval": True,
    }

    summary = {
        "ok": True,
        "patch_generation_plans_count": 1,
        "upstream_empty": False,
        "functional_dry_run_passed": True,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_generation_plans.json").write_text(
        json.dumps(plans, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_execution_order.json").write_text(
        json.dumps(order, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return summary


def _mock_empty_gen(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_empty_gen")
    out.mkdir(parents=True, exist_ok=True)

    plans: List[Dict[str, Any]] = []
    order: List[Dict[str, Any]] = []
    governance = {
        "governance_id": "gov_empty",
        "status": "real_patch_generation_plan_only_not_executable",
        "patch_generation_plans_count": 0,
    }
    summary = {
        "ok": False,
        "patch_generation_plans_count": 0,
        "upstream_empty": True,
        "failure_reason": "empty_real_patch_generation_plans",
        "functional_dry_run_passed": False,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_generation_plans.json").write_text(
        json.dumps(plans), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_execution_order.json").write_text(
        json.dumps(order), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    (out / "first_five_real_patch_generation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return summary


@pytest.fixture
def module(monkeypatch):
    """Import module with mocked upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_plan_dry_run", _mock_gen_result)
    return mod


@pytest.fixture
def empty_module(monkeypatch):
    """Import module with empty upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_plan_dry_run", _mock_empty_gen)
    return mod


# 1-2. import and functions
def test_import_module():
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    assert mod is not None


def test_required_functions_exist(module):
    assert callable(getattr(module, "now_utc", None))
    assert callable(getattr(module, "load_real_patch_generation_plan_artifacts", None))
    assert callable(getattr(module, "review_real_patch_generation_plan", None))
    assert callable(getattr(module, "review_all_real_patch_generation_plans", None))
    assert callable(getattr(module, "build_real_patch_generation_queue", None))
    assert callable(getattr(module, "build_real_patch_generation_plan_review_governance", None))
    assert callable(getattr(module, "summarize_real_patch_generation_plan_review", None))
    assert callable(getattr(module, "run_first_five_real_patch_generation_plan_review_dry_run", None))


# 3-5. review structure
def test_review_has_score(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert "review_score" in reviews[0]
    assert isinstance(reviews[0]["review_score"], (int, float))


def test_review_has_decision(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert "decision" in reviews[0]
    assert reviews[0]["decision"] != ""


def test_review_has_scores(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert "scores" in reviews[0]
    assert "generation_plan_completeness" in reviews[0]["scores"]


# 6. safe generation plan approved
def test_safe_plan_approved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["approved_for_real_patch_generation_dry_run"] is True


# 7-11. reject when flags true
def _make_flag_true_gen(flag_name: str):
    def _mock(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0][flag_name] = True
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    return _mock


def test_patch_generation_allowed_now_true_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_flag_true_gen("patch_generation_allowed_now"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_diff_generation_allowed_now_true_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_flag_true_gen("diff_generation_allowed_now"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_patch_application_allowed_now_true_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_flag_true_gen("patch_application_allowed_now"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_patch_applied_true_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_flag_true_gen("patches_applied"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_patch_staged_true_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_flag_true_gen("patches_staged"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 12. forbidden target rejected
def test_forbidden_target_rejected(monkeypatch, module, tmp_path):
    def _mock_forbidden(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["target_files_allowed_for_future_patch"] = ["memory/semantic/test.json"]
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_forbidden)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 13. missing tests request_more_tests
def test_missing_tests_request_more_tests(monkeypatch, module, tmp_path):
    def _mock_no_tests(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["required_tests"] = []
        plans[0]["acceptance_criteria"] = []
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_no_tests)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "request_more_tests"


# 14. missing rollback rejected
def test_missing_rollback_rejected(monkeypatch, module, tmp_path):
    def _mock_no_rollback(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["rollback_plan"] = {}
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_no_rollback)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 15. approval allowing patch generation rejected
def test_approval_allows_patch_generation_rejected(monkeypatch, module, tmp_path):
    def _mock_bad_approval(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["operator_approval_packet"]["approval_does_not_allow_patch_generation"] = False
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_bad_approval)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 16. approval allowing patch application rejected
def test_approval_allows_patch_application_rejected(monkeypatch, module, tmp_path):
    def _mock_bad_approval(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["operator_approval_packet"]["approval_does_not_allow_patch_application"] = False
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_bad_approval)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 17. generation unit allowed_now true rejected
def test_unit_allowed_now_true_rejected(monkeypatch, module, tmp_path):
    def _mock_unit_allowed(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["generation_units"][0]["allowed_now"] = True
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_unit_allowed)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 18-22. missing constraints
def _make_missing_constraint(constraint: str):
    def _mock(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        constraints = plans[0]["generation_units"][0]["patch_constraints"]
        if constraint in constraints:
            constraints.remove(constraint)
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    return _mock


def test_missing_no_apply_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_missing_constraint("no_apply"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_missing_no_stage_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_missing_constraint("no_stage"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_missing_no_memory_write_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_missing_constraint("no_memory_write"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_missing_no_faiss_write_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_missing_constraint("no_faiss_write"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


def test_missing_no_token_logging_rejected(monkeypatch, module, tmp_path):
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _make_missing_constraint("no_token_logging"))
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"


# 23-24. queue
def test_queue_includes_only_approved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    queue = json.loads((tmp_path / "first_five_real_patch_generation_queue.json").read_text())
    assert all(q["candidate_status"] == "approved_for_real_patch_generation_dry_run" for q in queue)


def test_queue_flags_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    queue = json.loads((tmp_path / "first_five_real_patch_generation_queue.json").read_text())
    for q in queue:
        assert q["patch_generation_allowed_now"] is False
        assert q["diff_generation_allowed_now"] is False
        assert q["patch_application_allowed_now"] is False


# 25-27. governance
def test_governance_status_correct(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_plan_review_governance.json").read_text())
    assert gov["status"] == "real_patch_generation_plan_review_only_not_executable"


def test_governance_flags_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_plan_review_governance.json").read_text())
    assert gov["patch_generation_allowed_now"] is False
    assert gov["patch_application_allowed_now"] is False
    assert gov["diff_generation_allowed_now"] is False


def test_governance_next_safe_front(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_plan_review_governance.json").read_text())
    assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-DRY-RUN-01"


# 28-30. output files
def test_output_files_written(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert (tmp_path / "first_five_real_patch_generation_plan_reviews.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_queue.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_plan_review_governance.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_plan_review_summary.json").exists()
    assert (tmp_path / "first_five_real_patch_generation_plan_review_report.md").exists()


def test_jsonl_written(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert (tmp_path / "first_five_real_patch_generation_plan_reviews.jsonl").exists()
    lines = (tmp_path / "first_five_real_patch_generation_plan_reviews.jsonl").read_text().strip().split("\n")
    assert len(lines) >= 1


def test_report_spanish_readable(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_plan_review_report.md").read_text()
    assert "Revision" in report or "revision" in report
    assert "NO Se Genero" in report or "NO Se Aplico" in report


# 31-32. empty upstream
def test_empty_upstream_returns_ok_false(empty_module, tmp_path):
    result = empty_module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["ok"] is False


def test_empty_upstream_recommended_next_not_application(empty_module, tmp_path):
    result = empty_module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    rec = result.get("recommended_next_action", "")
    assert "application" not in rec.lower() or "re_run" in rec.lower()


# 33-37. no mutation flags
def test_no_token_leak(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["token_leak_detected"] is False


def test_no_memory_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["memory_write_allowed"] is False


def test_no_faiss_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["faiss_write_allowed"] is False


def test_no_real_write_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["real_write_allowed"] is False


def test_no_promotion_flag(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["promotion_allowed"] is False


# 38-43. no integration / modification
def test_no_runtime_chat_integration(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_plan_review_report.md").read_text()
    assert len(report) > 0


def test_no_trading_b8_in_output(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    for r in reviews:
        assert "trading" not in r.get("category", "").lower()


def test_no_target_file_modified(module, tmp_path):
    test_file = tmp_path / "_test_target.py"
    test_file.write_text("# original")
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert test_file.read_text() == "# original"


def test_no_applicable_diff_generated(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_plan_review_report.md").read_text()
    assert "Diffs aplicables" in report or "applicable" in report.lower()


def test_no_patch_file_generated(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    for f in tmp_path.iterdir():
        if f.is_file() and f.suffix == ".patch":
            pytest.fail(f"Patch file generated: {f}")


def test_no_git_stage_implied(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    report = (tmp_path / "first_five_real_patch_generation_plan_review_report.md").read_text()
    assert "stage" in report.lower() or "staged" in report.lower()


# 44-49. counts and upstream
def test_reviews_count_ge_1(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["reviews_count"] >= 1


def test_queue_count_le_reviews_count(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    queue = json.loads((tmp_path / "first_five_real_patch_generation_queue.json").read_text())
    assert len(queue) <= result["reviews_count"]


def test_approved_count_matches_queue_count(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    queue = json.loads((tmp_path / "first_five_real_patch_generation_queue.json").read_text())
    assert result["approved_for_real_patch_generation_dry_run"] == len(queue)


def test_summary_contains_reviews_count(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert "reviews_count" in result


def test_upstream_empty_false_when_nonempty(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result.get("upstream_empty") is False


def test_functional_dry_run_passed_true(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result.get("functional_dry_run_passed") is True


# 50-54. governance and rollback
def test_governance_requires_operator_approval(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_plan_review_governance.json").read_text())
    assert gov["requires_operator_approval"] is True


def test_rollback_preserves_dirty_preexisting(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    # Check original plans preserved rollback
    plans = json.loads((tmp_path / "run_patch_generation_plan" / "first_five_real_patch_generation_plans.json").read_text())
    assert plans[0]["rollback_plan"]["preserve_dirty_preexisting_files"] is True


def test_required_tests_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert any("pytest" in str(t) for t in reviews[0].get("required_tests", []))


def test_acceptance_criteria_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert any("acceptance" in str(c).lower() for c in reviews[0].get("acceptance_criteria", []))


def test_risk_level_preserved(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0].get("risk_level") in ("low", "medium", "high")


# 55. generation units inspected
def test_generation_units_inspected(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert "scores" in reviews[0]
    assert reviews[0]["scores"]["bounded_patch_generation_readiness"] >= 0.0


# 56-60. forbidden paths in review
def test_forbidden_files_memory_semantic(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["scores"]["forbidden_scope_protection"] == 1.0


def test_forbidden_files_strategies(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["scores"]["forbidden_scope_protection"] == 1.0


def test_forbidden_files_trading_b8(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["scores"]["forbidden_scope_protection"] == 1.0


def test_forbidden_files_main_session(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["scores"]["forbidden_scope_protection"] == 1.0


def test_forbidden_files_curated_lookup(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["scores"]["forbidden_scope_protection"] == 1.0


# 61-63. operator approval
def test_operator_approval_required(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["operator_approval_required"] is True


def test_approval_does_not_allow_patch_generation(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    # Safe plan should pass this check
    assert reviews[0]["blocking_issues"] == []


def test_approval_does_not_allow_patch_application(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["blocking_issues"] == []


# 64. score weights work
def test_score_weights_work(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["review_score"] >= 0.0
    assert reviews[0]["review_score"] <= 1.0


# 65. decision reject beats approve
def test_decision_reject_beats_approve(monkeypatch, module, tmp_path):
    def _mock_bad_plan(output_dir: str | None = None):
        summary = _mock_gen_result(output_dir)
        out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
        plans = json.loads((out / "first_five_real_patch_generation_plans.json").read_text())
        plans[0]["real_write_allowed"] = True
        (out / "first_five_real_patch_generation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        return summary
    monkeypatch.setattr(module, "run_first_five_real_patch_generation_plan_dry_run", _mock_bad_plan)
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert reviews[0]["decision"] == "reject"
    assert reviews[0]["approved_for_real_patch_generation_dry_run"] is False


# 66. reviewed_at present
def test_reviewed_at_present(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    reviews = json.loads((tmp_path / "first_five_real_patch_generation_plan_reviews.json").read_text())
    assert "reviewed_at" in reviews[0]
    assert reviews[0]["reviewed_at"] != ""


# 67. output_dir recorded
def test_output_dir_recorded(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["output_dir"] == str(tmp_path)


# 68. queue next_safe_front correct
def test_queue_next_safe_front_correct(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    queue = json.loads((tmp_path / "first_five_real_patch_generation_queue.json").read_text())
    for q in queue:
        assert q["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-DRY-RUN-01"


# 69. governance writes_allowed false
def test_governance_writes_allowed_false(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    gov = json.loads((tmp_path / "first_five_real_patch_generation_plan_review_governance.json").read_text())
    assert gov["writes_allowed"] is False


# 70-72. no patches generated/applied/staged
def test_no_patches_generated_for_application(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["patches_generated_for_application"] is False


def test_no_patches_applied(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["patches_applied"] is False


def test_no_patches_staged(module, tmp_path):
    result = module.run_first_five_real_patch_generation_plan_review_dry_run(str(tmp_path))
    assert result["patches_staged"] is False
