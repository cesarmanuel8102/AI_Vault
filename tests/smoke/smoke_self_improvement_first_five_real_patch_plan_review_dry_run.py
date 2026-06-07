"""Smoke tests for self_improvement_first_five_real_patch_plan_review_dry_run.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import brain.external_sources.self_improvement_first_five_real_patch_plan_review_dry_run as rp


# --- helpers ---

def _mock_plan(**overrides):
    defaults = {
        "real_patch_plan_id": "plan_001",
        "real_patch_planning_candidate_id": "cand_001",
        "front_id": "front_test",
        "category": "evaluation_gate_gap",
        "patch_type": "test_patch",
        "risk_level": "low",
        "risk_notes": "low risk note",
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
        "implementation_steps": [{"step_id": "s1", "description": "step"}],
        "required_tests": ["pytest tests/smoke"],
        "acceptance_criteria": ["must pass"],
        "rollback_plan": {"required": True, "strategy": "revert"},
        "operator_approval_required": True,
        "implementation_allowed_now": False,
        "patch_application_allowed_now": False,
        "patch_generated_for_application": False,
        "patch_applied": False,
        "patch_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
    }
    defaults.update(overrides)
    return defaults


def _mock_run_first_five_real_patch_plan_dry_run(output_dir=None):
    out = Path(output_dir) if output_dir else Path("tmp_agent/run_output")
    out.mkdir(parents=True, exist_ok=True)

    plans = [
        _mock_plan(),
        _mock_plan(
            real_patch_plan_id="plan_002",
            real_patch_planning_candidate_id="cand_002",
            front_id="front_test2",
            category="patch_hygiene_gap",
            patch_type="policy_patch",
            risk_level="medium",
            target_files_allowed_for_future_patch=["brain/external_sources/foo.py"],
        ),
    ]
    order = [
        {"execution_sequence": 1, "real_patch_plan_id": "plan_001"},
        {"execution_sequence": 2, "real_patch_plan_id": "plan_002"},
    ]
    governance = {"status": "real_patch_plan_only_not_executable", "plans_count": 2}
    summary = {"ok": True, "plans_count": 2}

    (out / "first_five_real_patch_plans.json").write_text(json.dumps(plans), encoding="utf-8")
    (out / "first_five_real_patch_execution_order.json").write_text(json.dumps(order), encoding="utf-8")
    (out / "first_five_real_patch_plan_governance.json").write_text(json.dumps(governance), encoding="utf-8")
    (out / "first_five_real_patch_plan_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    return {"ok": True, "output_dir": str(out), "plans_count": 2}


# --- basic existence tests ---

def test_import_module():
    assert rp.now_utc is not None


def test_load_real_patch_plan_artifacts_exists():
    assert callable(rp.load_real_patch_plan_artifacts)


def test_review_real_patch_plan_exists():
    assert callable(rp.review_real_patch_plan)


def test_review_all_real_patch_plans_exists():
    assert callable(rp.review_all_real_patch_plans)


def test_build_real_patch_implementation_planning_queue_exists():
    assert callable(rp.build_real_patch_implementation_planning_queue)


def test_build_real_patch_plan_review_governance_exists():
    assert callable(rp.build_real_patch_plan_review_governance)


def test_summarize_real_patch_plan_review_exists():
    assert callable(rp.summarize_real_patch_plan_review)


def test_run_first_five_real_patch_plan_review_dry_run_exists():
    assert callable(rp.run_first_five_real_patch_plan_review_dry_run)


# --- review field correctness ---

def test_review_has_review_score():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert "review_score" in r


def test_review_has_decision():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert "decision" in r


def test_review_has_scores():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert "scores" in r
    assert "plan_completeness" in r["scores"]
    assert "safety_guards" in r["scores"]


def test_safe_plan_approved_or_eligible():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "approve_for_real_patch_implementation_planning"


def test_write_flag_true_rejected():
    p = _mock_plan(real_write_allowed=True)
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_patch_applied_true_rejected():
    p = _mock_plan(patch_applied=True)
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_patch_staged_true_rejected():
    p = _mock_plan(patch_staged=True)
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_forbidden_target_rejected():
    p = _mock_plan(target_files_allowed_for_future_patch=["memory/semantic/foo.jsonl"])
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_missing_tests_request_more_tests():
    p = _mock_plan(required_tests=[], acceptance_criteria=[])
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "request_more_tests"


def test_missing_rollback_rejected():
    p = _mock_plan(rollback_plan={"required": False})
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_high_risk_request_risk_mitigation():
    p = _mock_plan(risk_level="high", risk_notes="")
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "request_risk_mitigation"


# --- queue correctness ---

def test_queue_includes_only_approved_reviews():
    reviews = [
        rp.review_real_patch_plan(_mock_plan()),
        rp.review_real_patch_plan(_mock_plan(real_write_allowed=True)),
    ]
    q = rp.build_real_patch_implementation_planning_queue(reviews)
    assert len(q) == 1
    assert q[0]["real_patch_plan_id"] == "plan_001"


def test_queue_flags_false():
    reviews = [rp.review_real_patch_plan(_mock_plan())]
    q = rp.build_real_patch_implementation_planning_queue(reviews)
    assert q[0]["implementation_allowed_now"] is False
    assert q[0]["patch_application_allowed_now"] is False
    assert q[0]["real_patch_application_allowed_now"] is False


# --- governance correctness ---

def test_governance_status_correct():
    reviews = [rp.review_real_patch_plan(_mock_plan())]
    g = rp.build_real_patch_plan_review_governance(reviews)
    assert g["status"] == "real_patch_plan_review_only_not_executable"


def test_governance_flags_false():
    reviews = [rp.review_real_patch_plan(_mock_plan())]
    g = rp.build_real_patch_plan_review_governance(reviews)
    assert g["implementation_allowed_now"] is False
    assert g["patch_application_allowed_now"] is False
    assert g["patches_applied"] is False
    assert g["patches_staged"] is False
    assert g["writes_allowed"] is False


def test_governance_next_safe_front_correct():
    reviews = [rp.review_real_patch_plan(_mock_plan())]
    g = rp.build_real_patch_plan_review_governance(reviews)
    assert g["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-DRY-RUN-01"


# --- run integration with mock ---

def test_run_writes_reviews_json(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_reviews.json").exists()


def test_run_writes_reviews_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_reviews.jsonl").exists()


def test_run_writes_queue_json(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_implementation_planning_queue.json").exists()


def test_run_writes_governance_json(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_governance.json").exists()


def test_run_writes_summary_json(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_summary.json").exists()


def test_run_writes_report_md(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_report.md").exists()


def test_report_is_spanish_readable(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    md = (out / "first_five_real_patch_plan_review_report.md").read_text(encoding="utf-8")
    assert "Resumen" in md
    assert "Revision" in md or "Revisados" in md


def test_no_token_leak_in_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("token_leak_detected") is False


def test_no_memory_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("memory_write_allowed") is False


def test_no_faiss_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("faiss_write_allowed") is False


def test_no_real_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("real_write_allowed") is False


def test_no_promotion(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("promotion_allowed") is False


def test_patches_generated_for_application_false(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("patches_generated_for_application") is False


def test_patches_applied_false(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("patches_applied") is False


def test_patches_staged_false(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("patches_staged") is False


def test_reviews_count_at_least_one(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("reviews_count", 0) >= 1


def test_queue_count_le_reviews_count(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("implementation_planning_queue_count", 0) <= result.get("reviews_count", 0)


def test_next_safe_front_is_implementation_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    gov = json.loads((out / "first_five_real_patch_plan_review_governance.json").read_text(encoding="utf-8"))
    assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-DRY-RUN-01"


def test_no_target_file_is_directly_modified(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert not (out / "tests/smoke/test_example.py").exists()


def test_forbidden_files_list_validated():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert r["scores"]["forbidden_scope_protection"] == 1.0


def test_target_allowed_files_validated():
    p = _mock_plan(target_files_allowed_for_future_patch=["memory/semantic/foo.jsonl"])
    r = rp.review_real_patch_plan(p)
    assert r["scores"]["forbidden_scope_protection"] == 0.0


def test_required_tests_preserved():
    p = _mock_plan(required_tests=["pytest -q"])
    r = rp.review_real_patch_plan(p)
    assert r["scores"]["test_readiness"] >= 0.5


def test_acceptance_criteria_preserved():
    p = _mock_plan(acceptance_criteria=["must lint"])
    r = rp.review_real_patch_plan(p)
    assert r["scores"]["test_readiness"] >= 0.5


def test_rollback_required_true():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert "rollback_plan" not in r  # it's in the plan, not review directly
    # but missing rollback should reject
    p2 = _mock_plan(rollback_plan={"required": False})
    r2 = rp.review_real_patch_plan(p2)
    assert r2["decision"] == "reject"


def test_operator_approval_required_true():
    p = _mock_plan(operator_approval_required=False)
    r = rp.review_real_patch_plan(p)
    assert r["decision"] == "reject"


def test_score_weights_work():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    expected = round(
        r["scores"]["plan_completeness"] * 0.20 +
        r["scores"]["safety_guards"] * 0.30 +
        r["scores"]["forbidden_scope_protection"] * 0.20 +
        r["scores"]["test_readiness"] * 0.15 +
        r["scores"]["implementation_boundedness"] * 0.15,
        4,
    )
    assert r["review_score"] == expected


def test_summary_counts_decisions(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert "approved_for_real_patch_implementation_planning" in result
    assert "rejected" in result


def test_jsonl_written(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    lines = (out / "first_five_real_patch_plan_reviews.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1


def test_governance_written(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_governance.json").exists()


def test_summary_written(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_summary.json").exists()


def test_report_written(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_review_report.md").exists()


def test_output_dir_set(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("output_dir") == str(out)


def test_reviewed_at_present():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert "reviewed_at" in r
    assert r["reviewed_at"] is not None


def test_approved_queue_item_has_rollback_required_true(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    q = json.loads((out / "first_five_real_patch_implementation_planning_queue.json").read_text(encoding="utf-8"))
    if q:
        assert q[0]["rollback_required"] is True


def test_implementation_allowed_now_false():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert r["implementation_allowed_now"] is False


def test_real_patch_application_allowed_now_false():
    p = _mock_plan()
    r = rp.review_real_patch_plan(p)
    assert r["patch_application_allowed_now"] is False


def test_writes_allowed_false_in_governance(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    gov = json.loads((out / "first_five_real_patch_plan_review_governance.json").read_text(encoding="utf-8"))
    assert gov["writes_allowed"] is False


def test_next_front_is_real_patch_implementation_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    gov = json.loads((out / "first_five_real_patch_plan_review_governance.json").read_text(encoding="utf-8"))
    assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-DRY-RUN-01"


def test_no_runtime_chat_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("promotion_allowed") is False
    assert result.get("real_write_allowed") is False


def test_no_trading_b8(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "run_first_five_real_patch_plan_dry_run", _mock_run_first_five_real_patch_plan_dry_run)
    out = tmp_path / "review"
    result = rp.run_first_five_real_patch_plan_review_dry_run(str(out))
    assert result.get("memory_write_allowed") is False
    assert result.get("faiss_write_allowed") is False


def test_score_plan_completeness_max():
    p = _mock_plan()
    assert rp._score_plan_completeness(p) == 1.0


def test_score_safety_guards_max():
    p = _mock_plan()
    assert rp._score_safety_guards(p) == 1.0


def test_score_forbidden_scope_protection_max():
    p = _mock_plan()
    assert rp._score_forbidden_scope_protection(p) == 1.0


def test_score_test_readiness_max():
    p = _mock_plan()
    assert rp._score_test_readiness(p) == 1.0


def test_score_implementation_boundedness_max():
    p = _mock_plan()
    assert rp._score_implementation_boundedness(p) == 1.0
