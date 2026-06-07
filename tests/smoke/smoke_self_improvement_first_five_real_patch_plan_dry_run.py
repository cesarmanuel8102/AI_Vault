"""Smoke tests for self_improvement_first_five_real_patch_plan_dry_run.py."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import brain.external_sources.self_improvement_first_five_real_patch_plan_dry_run as rp

# --- helpers ---

def _mock_candidate(**overrides):
    defaults = {
        "real_patch_planning_candidate_id": "cand_001",
        "generation_review_id": "rev_001",
        "patch_proposal_id": "prop_001",
        "front_id": "front_test",
        "category": "evaluation_gate_gap",
        "patch_type": "test_patch",
        "risk_level": "low",
        "risk_notes": "test risk",
        "target_files_suggested": ["tests/smoke/test_example.py"],
        "required_tests": ["pytest tests/smoke/test_example.py"],
        "acceptance_criteria": ["must pass"],
    }
    defaults.update(overrides)
    return defaults

def _mock_review(**overrides):
    defaults = {
        "generation_review_id": "rev_001",
        "target_files_suggested": ["tests/smoke/test_example.py"],
        "required_tests": ["pytest tests/smoke/test_example.py"],
        "acceptance_criteria": ["must pass"],
        "risk_level": "low",
        "risk_notes": "test risk",
        "category": "evaluation_gate_gap",
        "patch_type": "test_patch",
    }
    defaults.update(overrides)
    return defaults

def _mock_run_first_five_patch_generation_review_dry_run(output_dir=None):
    out = Path(output_dir) if output_dir else Path("tmp_agent/run_output")
    out.mkdir(parents=True, exist_ok=True)

    queue = [
        {
            "real_patch_planning_candidate_id": "cand_001",
            "generation_review_id": "rev_001",
            "patch_proposal_id": "prop_001",
            "front_id": "front_test",
            "category": "evaluation_gate_gap",
            "patch_type": "test_patch",
            "risk_level": "low",
            "risk_notes": "test risk",
            "target_files_suggested": ["tests/smoke/test_example.py"],
            "required_tests": ["pytest tests/smoke/test_example.py"],
            "acceptance_criteria": ["must pass"],
        },
        {
            "real_patch_planning_candidate_id": "cand_002",
            "generation_review_id": "rev_002",
            "patch_proposal_id": "prop_002",
            "front_id": "front_test2",
            "category": "patch_hygiene_gap",
            "patch_type": "policy_patch",
            "risk_level": "medium",
            "risk_notes": "medium risk",
            "target_files_suggested": ["brain/external_sources/foo.py"],
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["must lint"],
        },
    ]
    reviews = [
        {
            "generation_review_id": "rev_001",
            "target_files_suggested": ["tests/smoke/test_example.py"],
            "required_tests": ["pytest tests/smoke/test_example.py"],
            "acceptance_criteria": ["must pass"],
            "risk_level": "low",
            "risk_notes": "test risk",
            "category": "evaluation_gate_gap",
            "patch_type": "test_patch",
        },
        {
            "generation_review_id": "rev_002",
            "target_files_suggested": ["brain/external_sources/foo.py"],
            "required_tests": ["pytest tests/smoke -q"],
            "acceptance_criteria": ["must lint"],
            "risk_level": "medium",
            "risk_notes": "medium risk",
            "category": "patch_hygiene_gap",
            "patch_type": "policy_patch",
        },
    ]
    summary = {"ok": True, "reviews_count": 2, "approved_for_real_patch_planning": 2}

    (out / "first_five_real_patch_planning_queue.json").write_text(json.dumps(queue), encoding="utf-8")
    (out / "first_five_patch_generation_reviews.json").write_text(json.dumps(reviews), encoding="utf-8")
    (out / "first_five_patch_generation_review_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    return {"ok": True, "output_dir": str(out), "reviews_count": 2}


# --- basic existence tests ---

def test_import_module():
    assert rp.now_utc is not None

def test_load_real_patch_planning_queue_artifacts_exists():
    assert callable(rp.load_real_patch_planning_queue_artifacts)

def test_build_real_patch_plan_exists():
    assert callable(rp.build_real_patch_plan)

def test_build_all_real_patch_plans_exists():
    assert callable(rp.build_all_real_patch_plans)

def test_build_real_patch_execution_order_exists():
    assert callable(rp.build_real_patch_execution_order)

def test_build_real_patch_plan_governance_exists():
    assert callable(rp.build_real_patch_plan_governance)

def test_summarize_real_patch_plan_exists():
    assert callable(rp.summarize_real_patch_plan)

def test_run_first_five_real_patch_plan_dry_run_exists():
    assert callable(rp.run_first_five_real_patch_plan_dry_run)

# --- plan field correctness ---

def test_plan_status_is_dry_run_only():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["plan_status"] == "real_patch_plan_dry_run_only"

def test_plan_implementation_allowed_now_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["implementation_allowed_now"] is False

def test_plan_patch_application_allowed_now_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["patch_application_allowed_now"] is False

def test_plan_patch_generated_for_application_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["patch_generated_for_application"] is False

def test_plan_patch_applied_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["patch_applied"] is False

def test_plan_patch_staged_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["patch_staged"] is False

def test_plan_operator_approval_required_true():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["operator_approval_required"] is True

def test_plan_memory_write_allowed_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["memory_write_allowed"] is False

def test_plan_faiss_write_allowed_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["faiss_write_allowed"] is False

def test_plan_real_write_allowed_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["real_write_allowed"] is False

def test_plan_promotion_allowed_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["promotion_allowed"] is False

def test_plan_has_rollback_required_true():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["rollback_plan"]["required"] is True

def test_plan_has_required_tests():
    c = _mock_candidate(required_tests=["pytest -q"])
    p = rp.build_real_patch_plan(c)
    assert "pytest -q" in p["required_tests"]

def test_plan_has_acceptance_criteria():
    c = _mock_candidate(acceptance_criteria=["must lint"])
    p = rp.build_real_patch_plan(c)
    assert "must lint" in p["acceptance_criteria"]

def test_plan_has_forbidden_files():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert "memory/semantic/*" in p["files_forbidden_to_modify"]

def test_plan_filters_forbidden_targets():
    c = _mock_candidate(target_files_suggested=["memory/semantic/foo.jsonl", "tests/smoke/test.py"])
    p = rp.build_real_patch_plan(c)
    assert "memory/semantic/foo.jsonl" not in p["target_files_allowed_for_future_patch"]
    assert "tests/smoke/test.py" in p["target_files_allowed_for_future_patch"]

def test_plan_enriches_missing_fields_from_review():
    c = _mock_candidate(required_tests=[], acceptance_criteria=[], target_files_suggested=[])
    r = _mock_review(required_tests=["pytest"], acceptance_criteria=["must pass"], target_files_suggested=["tests/smoke/a.py"])
    p = rp.build_real_patch_plan(c, r)
    assert p["required_tests"] == ["pytest"]
    assert p["acceptance_criteria"] == ["must pass"]
    assert p["target_files_suggested"] == ["tests/smoke/a.py"]

def test_plan_fallback_defaults_when_review_missing():
    c = _mock_candidate(required_tests=[], acceptance_criteria=[], target_files_suggested=[])
    p = rp.build_real_patch_plan(c, None)
    assert p["required_tests"] == ["python -m pytest tests/smoke -q"]
    assert p["acceptance_criteria"] == ["operator must define acceptance criteria before implementation"]
    assert p["target_files_suggested"] == ["tests/smoke/*"]

# --- execution order ---

def test_execution_order_exists():
    plans = [
        rp.build_real_patch_plan(_mock_candidate(category="patch_hygiene_gap", patch_type="policy_patch", risk_level="medium")),
        rp.build_real_patch_plan(_mock_candidate(category="evaluation_gate_gap", patch_type="test_patch", risk_level="low")),
    ]
    order = rp.build_real_patch_execution_order(plans)
    assert len(order) == 2
    assert order[0]["category"] == "evaluation_gate_gap"
    assert order[1]["category"] == "patch_hygiene_gap"

# --- governance ---

def test_governance_status_correct():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["status"] == "real_patch_plan_only_not_executable"

def test_governance_implementation_allowed_now_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["implementation_allowed_now"] is False

def test_governance_patch_application_allowed_now_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["patch_application_allowed_now"] is False

def test_governance_patches_generated_for_application_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["patches_generated_for_application"] is False

def test_governance_patches_applied_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["patches_applied"] is False

def test_governance_patches_staged_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["patches_staged"] is False

def test_governance_writes_allowed_false():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["writes_allowed"] is False

def test_governance_next_safe_front_correct():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-REVIEW-DRY-RUN-01"

def test_governance_must_preserve_dirty_true():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["must_preserve_dirty_preexisting_files"] is True

def test_governance_must_keep_commits_separate_true():
    p = [rp.build_real_patch_plan(_mock_candidate())]
    g = rp.build_real_patch_plan_governance(p)
    assert g["must_keep_code_and_ledger_commits_separate"] is True

# --- run integration with mock ---

def test_run_writes_first_five_real_patch_plans_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_plans.json").exists()

def test_run_writes_first_five_real_patch_plans_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_plans.jsonl").exists()

def test_run_writes_first_five_real_patch_execution_order_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_execution_order.json").exists()

def test_run_writes_first_five_real_patch_plan_governance_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_governance.json").exists()

def test_run_writes_first_five_real_patch_plan_summary_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_summary.json").exists()

def test_run_writes_first_five_real_patch_plan_report_md(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert (out / "first_five_real_patch_plan_report.md").exists()

def test_report_is_spanish_readable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    md = (out / "first_five_real_patch_plan_report.md").read_text(encoding="utf-8")
    assert "Resumen" in md
    assert "Gobernanza" in md
    assert "Plan Real de Patch" in md

def test_no_token_leak_in_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("token_leak_detected") is False

def test_no_memory_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("memory_write_allowed") is False

def test_no_faiss_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("faiss_write_allowed") is False

def test_no_real_write_performed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("real_write_allowed") is False

def test_no_promotion(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("promotion_allowed") is False

def test_patches_generated_for_application_false(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("patches_generated_for_application") is False

def test_patches_applied_false(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("patches_applied") is False

def test_patches_staged_false(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("patches_staged") is False

def test_plans_count_at_least_one(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("plans_count", 0) >= 1

def test_next_safe_front_is_real_patch_plan_review(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    gov = json.loads((out / "first_five_real_patch_plan_governance.json").read_text(encoding="utf-8"))
    assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-REVIEW-DRY-RUN-01"

def test_no_target_file_is_directly_modified(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    for f in ["tests/smoke/test_example.py", "brain/external_sources/foo.py"]:
        assert not (out / f).exists()

def test_forbidden_files_include_memory_semantic(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    plans = json.loads((out / "first_five_real_patch_plans.json").read_text(encoding="utf-8"))
    for p in plans:
        assert any("memory/semantic" in f for f in p["files_forbidden_to_modify"])

def test_forbidden_files_include_tmp_agent_strategies(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    plans = json.loads((out / "first_five_real_patch_plans.json").read_text(encoding="utf-8"))
    for p in plans:
        assert any("tmp_agent/strategies" in f for f in p["files_forbidden_to_modify"])

def test_forbidden_files_include_trading_b8(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    plans = json.loads((out / "first_five_real_patch_plans.json").read_text(encoding="utf-8"))
    for p in plans:
        assert any("trading" in f for f in p["files_forbidden_to_modify"])
        assert any("B8" in f for f in p["files_forbidden_to_modify"])

def test_forbidden_files_include_mainpy_sessionpy(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    rp.run_first_five_real_patch_plan_dry_run(str(out))
    plans = json.loads((out / "first_five_real_patch_plans.json").read_text(encoding="utf-8"))
    for p in plans:
        assert any("main.py" in f for f in p["files_forbidden_to_modify"])
        assert any("session.py" in f for f in p["files_forbidden_to_modify"])

def test_plan_steps_allowed_now_false():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    for s in p["implementation_steps"]:
        assert s["allowed_now"] is False

def test_summary_ok_when_plans_exist():
    plans = [rp.build_real_patch_plan(_mock_candidate())]
    order = rp.build_real_patch_execution_order(plans)
    s = rp.summarize_real_patch_plan(plans, order)
    assert s["ok"] is True
    assert s["plans_count"] == 1

def test_summary_ok_false_when_no_plans():
    s = rp.summarize_real_patch_plan([], [])
    assert s["ok"] is False

def test_execution_order_sequence_numbers_increase():
    plans = [
        rp.build_real_patch_plan(_mock_candidate(category="security_supply_chain_gap", risk_level="high", patch_type="harness_patch")),
        rp.build_real_patch_plan(_mock_candidate(category="evaluation_gate_gap", risk_level="low", patch_type="test_patch")),
    ]
    order = rp.build_real_patch_execution_order(plans)
    assert order[0]["execution_sequence"] == 1
    assert order[1]["execution_sequence"] == 2

def test_no_runtime_chat_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("promotion_allowed") is False
    assert result.get("real_write_allowed") is False

def test_no_trading_b8(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("memory_write_allowed") is False
    assert result.get("faiss_write_allowed") is False

def test_rollback_preserves_dirty_preexisting():
    c = _mock_candidate()
    p = rp.build_real_patch_plan(c)
    assert p["rollback_plan"]["preserve_dirty_preexisting_files"] is True

def test_plans_count_matches_queue_size(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rp, "run_first_five_patch_generation_review_dry_run", _mock_run_first_five_patch_generation_review_dry_run
    )
    out = tmp_path / "real_patch_plan"
    result = rp.run_first_five_real_patch_plan_dry_run(str(out))
    assert result.get("plans_count") == 2
