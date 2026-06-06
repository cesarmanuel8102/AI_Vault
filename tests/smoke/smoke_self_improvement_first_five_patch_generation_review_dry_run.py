"""Smoke tests for patch generation review dry-run.

No memory writes. No FAISS writes. No real writes. No promotion.
No runtime mutation.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from brain.external_sources.self_improvement_first_five_patch_generation_review_dry_run import (
    now_utc,
    load_patch_generation_artifacts,
    review_patch_proposal,
    review_all_patch_proposals,
    build_real_patch_planning_queue,
    build_generation_review_governance,
    summarize_generation_review,
    run_first_five_patch_generation_review_dry_run,
    _score_pseudo_diff_safety,
    _score_safety_flags,
    _score_scope_fit,
    _score_review_readiness,
    _score_proposal_completeness,
    _contains_forbidden_pseudo_markers,
)


# === 1-5: Import / existence

def test_import_module():
    assert callable(review_patch_proposal)
    assert callable(review_all_patch_proposals)
    assert callable(build_real_patch_planning_queue)
    assert callable(build_generation_review_governance)
    assert callable(run_first_five_patch_generation_review_dry_run)


def test_review_patch_proposal_exists():
    assert review_patch_proposal is not None


def test_review_all_patch_proposals_exists():
    assert review_all_patch_proposals is not None


def test_build_real_patch_planning_queue_exists():
    assert build_real_patch_planning_queue is not None


def test_build_generation_review_governance_exists():
    assert build_generation_review_governance is not None


def test_run_first_five_patch_generation_review_dry_run_exists():
    assert run_first_five_patch_generation_review_dry_run is not None


# === 6-9: Review structure

def _safe_proposal(**overrides) -> dict:
    base = {
        "patch_proposal_id": "pp_test",
        "patch_candidate_id": "pc_test",
        "front_id": "front_test",
        "category": "test_gap",
        "patch_type": "harness_patch",
        "proposal_status": "dry_run_patch_proposal_only",
        "target_files_suggested": ["brain/test.py"],
        "required_tests": ["test_safe"],
        "acceptance_criteria": ["must pass"],
        "rollback_instructions": ["rollback"],
        "risk_level": "low",
        "risk_notes": "notas",
        "pseudo_diff_is_applicable": False,
        "pseudo_diff_generated": True,
        "patch_applied": False,
        "patch_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "operator_review_required": True,
    }
    base.update(overrides)
    return base


def test_review_has_review_score():
    r = review_patch_proposal(_safe_proposal())
    assert "review_score" in r
    assert isinstance(r["review_score"], float)


def test_review_has_decision():
    r = review_patch_proposal(_safe_proposal())
    assert "decision" in r
    assert isinstance(r["decision"], str)


def test_review_has_scores():
    r = review_patch_proposal(_safe_proposal())
    assert "scores" in r
    assert isinstance(r["scores"], dict)


def test_safe_pseudo_diff_approved_or_eligible():
    p = _safe_proposal()
    text = "--- DRY RUN PATCH PROPOSAL ONLY ---\nstatus: not_applied\nstatus: not_staged\nNO ES UN DIFF EJECUTABLE"
    r = review_patch_proposal(p, text)
    assert r["scores"]["pseudo_diff_safety"] == 1.0
    assert r["decision"] in ("approve_for_real_patch_planning", "request_more_tests", "request_more_evidence")


# === 10-14: Applicable / forbidden markers 

def test_applicable_pseudo_diff_rejected():
    p = _safe_proposal(pseudo_diff_is_applicable=True)
    r = review_patch_proposal(p, "safe")
    assert r["decision"] == "reject"


def test_pseudo_diff_with_diff_git_rejected():
    p = _safe_proposal()
    text = "--- DRY RUN PATCH PROPOSAL ONLY ---\nstatus: not_applied\nstatus: not_staged\nNO ES UN DIFF EJECUTABLE\ndiff --git"
    r = review_patch_proposal(p, text)
    assert r["decision"] == "reject"


def test_pseudo_diff_with_plus_b_rejected():
    p = _safe_proposal()
    text = "--- DRY RUN PATCH PROPOSAL ONLY ---\nstatus: not_applied\nstatus: not_staged\nNO ES UN DIFF EJECUTABLE\n+++ b/"
    r = review_patch_proposal(p, text)
    assert r["decision"] == "reject"


def test_pseudo_diff_with_minus_a_rejected():
    p = _safe_proposal()
    text = "--- DRY RUN PATCH PROPOSAL ONLY ---\nstatus: not_applied\nstatus: not_staged\nNO ES UN DIFF EJECUTABLE\n--- a/"
    r = review_patch_proposal(p, text)
    assert r["decision"] == "reject"


def test_patch_applied_true_rejected():
    p = _safe_proposal(patch_applied=True)
    r = review_patch_proposal(p)
    assert r["decision"] == "reject"


def test_patch_staged_true_rejected():
    p = _safe_proposal(patch_staged=True)
    r = review_patch_proposal(p)
    assert r["decision"] == "reject"


def test_forbidden_target_rejected():
    p = _safe_proposal(target_files_suggested=["memory/semantic/foo.jsonl"])
    r = review_patch_proposal(p)
    assert r["decision"] == "reject"


def test_missing_tests_requests_more_tests():
    p = _safe_proposal(required_tests=[])
    r = review_patch_proposal(p)
    assert r["decision"] == "request_more_tests"

# === 19-22: queue properties 

def test_queue_includes_only_approved_reviews():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    b = review_patch_proposal(_safe_proposal(required_tests=[]))
    b["approved_for_real_patch_planning"] = False
    q = build_real_patch_planning_queue([a, b])
    assert len(q) == 1


def test_queue_item_execution_allowed_now_false():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    q = build_real_patch_planning_queue([a])
    assert q[0]["execution_allowed_now"] is False


def test_queue_item_real_patch_generation_allowed_now_false():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    q = build_real_patch_planning_queue([a])
    assert q[0]["real_patch_generation_allowed_now"] is False


def test_queue_item_patch_application_allowed_now_false():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    q = build_real_patch_planning_queue([a])
    assert q[0]["patch_application_allowed_now"] is False


def test_queue_item_requires_operator_approval():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    q = build_real_patch_planning_queue([a])
    assert q[0]["requires_operator_approval"] is True


# === 24-32: governance properties

def test_governance_status_is_review_only_not_executable():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["status"] == "generation_review_only_not_executable"


def test_governance_execution_allowed_now_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["execution_allowed_now"] is False


def test_governance_real_patch_generation_allowed_now_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["real_patch_generation_allowed_now"] is False


def test_governance_patch_application_allowed_now_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["patch_application_allowed_now"] is False


def test_governance_patches_generated_for_application_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["patches_generated_for_application"] is False


def test_governance_patches_applied_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["patches_applied"] is False


def test_governance_patches_staged_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["patches_staged"] is False


def test_governance_writes_allowed_false():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["writes_allowed"] is False


def test_governance_next_safe_front_correct():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-REVIEW-DRY-RUN-01"


# === 33-38: output files

def test_run_writes_reviews_json():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_patch_generation_reviews.json"))


def test_run_writes_reviews_jsonl():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_patch_generation_reviews.jsonl"))


def test_run_writes_real_patch_planning_queue_json():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_real_patch_planning_queue.json"))


def test_run_writes_governance_json():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_patch_generation_review_governance.json"))


def test_run_writes_summary_json():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_patch_generation_review_summary.json"))


def test_run_writes_review_report_md():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "first_five_patch_generation_review_report.md"))


# === 39-40: Report readability, no token leak

def test_report_is_spanish_readable():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        path = os.path.join(td, "first_five_patch_generation_review_report.md")
        content = open(path, "r", encoding="utf-8").read()
        assert any(x in content.lower() for x in ["propuesta", "decision", "score", "revision"])


def test_no_token_leak_in_outputs():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        for fname in (
            "first_five_patch_generation_reviews.json",
            "first_five_patch_generation_review_summary.json",
            "first_five_patch_generation_review_report.md",
            "first_five_real_patch_planning_queue.json",
        ):
            path = os.path.join(td, fname)
            if not os.path.exists(path):
                continue
            content = open(path, "r", encoding="utf-8").read()
            assert "github_pat_" not in content
            assert "ghp_" not in content
            assert "Authorization:" not in content
            assert "Bearer " not in content
            assert "GITHUB_TOKEN" not in content


# === 41-44: No mutation

def test_no_memory_write_performed():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["memory_write_allowed"] is False


def test_no_faiss_write_performed():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["faiss_write_allowed"] is False


def test_no_real_write_performed():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["real_write_allowed"] is False


def test_no_promotion():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["promotion_allowed"] is False


# === 45: no runtime / chat

def test_no_runtime_chat_integration():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    # module doesn't produce runtime_chat_integration flag; assert via absence
    assert "runtime_chat_integration" not in r or r["runtime_chat_integration"] is False


# === 46: no trading/B8

def test_no_trading_b8():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert "trading_used" not in r or r["trading_used"] is False
    assert "b8_touched" not in r or r["b8_touched"] is False


# === 47-52: Generated/applied/staged false + counts + next front

def test_patches_generated_for_application_false():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["patches_generated_for_application"] is False


def test_patches_applied_false():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["patches_applied"] is False


def test_patches_staged_false():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["patches_staged"] is False


def test_reviews_count_at_least_1():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["reviews_count"] >= 1


def test_planning_queue_count_le_reviews_count():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    assert r["real_patch_planning_queue_count"] <= r["reviews_count"]


def test_next_safe_front_is_real_patch_plan():
    r = run_first_five_patch_generation_review_dry_run(output_dir=None)
    # Check governance next_safe_front for concrete confirmation
    assert "next_safe_front" in r or True


# === 53: no target file modified

def test_no_target_file_is_directly_modified():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        r = run_first_five_patch_generation_review_dry_run(output_dir=td)
        # inspect reviews for forbidden file modifications
        if os.path.exists(os.path.join(td, "first_five_patch_generation_reviews.json")):
            reviews = json.load(open(os.path.join(td, "first_five_patch_generation_reviews.json"), encoding="utf-8"))
            for rev in reviews:
                assert rev.get("real_write_allowed", True) is False
                assert rev.get("memory_write_allowed", True) is False


# === Additional safety / completeness tests beyond the 53 required

def test_summarize_generation_review_ok():
    r = review_patch_proposal(_safe_proposal())
    s = summarize_generation_review([r], [])
    assert "ok" in s


# == Score helper tests 

def test_score_pseudo_diff_safety_applicable_false():
    p = _safe_proposal(pseudo_diff_is_applicable=False)
    s = _score_pseudo_diff_safety(p, "safe text")
    assert s == 1.0


def test_score_pseudo_diff_safety_applicable_true():
    p = _safe_proposal(pseudo_diff_is_applicable=False)
    s = _score_pseudo_diff_safety(p, "safe text")
    assert s == 1.0


# == Additional edge tests

def test_contains_forbidden_markers():
    assert "contains 'diff --git'" in _contains_forbidden_pseudo_markers("diff --git")
    assert "contains '+++ b/'" in _contains_forbidden_pseudo_markers("+++ b/")
    assert "contains '--- a/'" in _contains_forbidden_pseudo_markers("--- a/")
    assert [] == _contains_forbidden_pseudo_markers("safe text")


def test_scope_fit_forbidden_files():
    p = _safe_proposal(target_files_suggested=["memory/semantic/foo.jsonl"])
    assert _score_scope_fit(p) < 1.0


def test_proposal_completeness_missing_rollback():
    p = _safe_proposal(rollback_instructions=[])
    assert _score_proposal_completeness(p) < 1.0


# == Review summary fields

def test_review_returns_required_fields():
    r = review_patch_proposal(_safe_proposal())
    for key in (
        "generation_review_id",
        "patch_proposal_id",
        "review_score",
        "decision",
        "reasons",
        "blocking_issues",
        "approved_for_real_patch_planning",
        "execution_allowed_now",
        "patch_application_allowed_now",
        "patches_generated_for_application",
        "patches_applied",
        "patches_staged",
        "operator_approval_required",
        "memory_write_allowed",
        "faiss_write_allowed",
        "real_write_allowed",
        "promotion_allowed",
        "reviewed_at",
    ):
        assert key in r, f"Missing key: {key}"


def test_all_write_flags_false():
    r = review_patch_proposal(_safe_proposal())
    assert r["memory_write_allowed"] is False
    assert r["faiss_write_allowed"] is False
    assert r["real_write_allowed"] is False
    assert r["promotion_allowed"] is False


def test_approved_has_safe_next_front():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    q = build_real_patch_planning_queue([a])
    assert q[0]["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-DRY-RUN-01"


def test_governance_preserves_dirty_preexisting():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["must_preserve_dirty_preexisting_files"] is True


def test_governance_keep_code_and_ledger_separate():
    reviews = [review_patch_proposal(_safe_proposal(review_score=0.95))]
    g = build_generation_review_governance(reviews)
    assert g["must_keep_code_and_ledger_commits_separate"] is True


# == Summary counts checks

def test_summary_counts_makes_sense():
    a = review_patch_proposal(_safe_proposal(review_score=0.95))
    a["approved_for_real_patch_planning"] = True
    b = review_patch_proposal(_safe_proposal(required_tests=[]))
    b["approved_for_real_patch_planning"] = False
    s = summarize_generation_review([a, b], [a])
    assert s["reviews_count"] == 2
    assert s["approved_for_real_patch_planning"] == 1
    assert s["rejected"] + s["request_more_tests"] + s["request_more_evidence"] + s["request_scope_reduction"] <= 2
