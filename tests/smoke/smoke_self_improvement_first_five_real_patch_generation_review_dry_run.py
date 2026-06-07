"""Smoke tests for real patch generation review dry-run module.

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

MODULE_PATH = "brain.external_sources.self_improvement_first_five_real_patch_generation_review_dry_run"


def _make_draft(base: Dict[str, Any], **overrides) -> Dict[str, Any]:
    d = {**base}
    d.update(overrides)
    return d


def _mock_gen_result(output_dir: str | None = None) -> Dict[str, Any]:
    """Mock upstream generation dry-run that writes artifacts."""
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_gen")
    out.mkdir(parents=True, exist_ok=True)

    base_draft = {
        "real_patch_draft_id": "draft_abc123",
        "real_patch_generation_candidate_id": "candidate_def456",
        "real_patch_generation_plan_review_id": "review_ghi789",
        "real_patch_generation_plan_id": "plan_jkl012",
        "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
        "category": "evaluation_gate_gap",
        "patch_type": "test_patch",
        "draft_status": "inert_patch_draft_dry_run_only",
        "dry_run_only": True,
        "applicable": False,
        "not_for_git_apply": True,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "target_files_suggested": ["tests/smoke/test_example.py"],
        "target_files_not_modified": ["tests/smoke/test_example.py"],
        "pseudo_diff_text": (
            "DRY-RUN ONLY — NOT A GIT PATCH\n\n"
            "This is an inert human-review draft.\n"
            "Do not run git apply.\n"
            "Do not paste into patch application tools.\n"
        ),
        "pseudo_diff_is_applicable": False,
        "pseudo_diff_header": "DRY-RUN ONLY — NOT A GIT PATCH",
        "human_review_required": True,
        "operator_approval_packet": {
            "required": True,
            "approval_scope": "inert_patch_draft_only",
            "approval_does_not_allow_patch_application": True,
            "approval_does_not_allow_git_apply": True,
            "must_review_target_files": True,
            "must_review_tests": True,
            "must_review_rollback": True,
        },
        "required_tests": ["python -m pytest tests/smoke -q"],
        "acceptance_criteria": ["operator must define acceptance criteria before patch generation"],
        "rollback_plan": {
            "required": True,
            "strategy": "discard_inert_draft_artifacts_only",
            "preserve_dirty_preexisting_files": True,
        },
        "risk_level": "low",
        "risk_notes": "low risk test patch",
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": "2026-06-07T00:00:00Z",
    }

    drafts = [
        base_draft,
        _make_draft(base_draft,
            real_patch_draft_id="draft_def456",
            real_patch_generation_candidate_id="candidate_ghi789",
            real_patch_generation_plan_review_id="review_jkl012",
            real_patch_generation_plan_id="plan_mno345",
            front_id="SECURITY_SANDBOXING_SUPPLY_CHAIN",
            category="security_supply_chain_gap",
            patch_type="policy_patch",
            target_files_suggested=["brain/external_sources/*"],
            target_files_not_modified=["brain/external_sources/*"],
        ),
        _make_draft(base_draft,
            real_patch_draft_id="draft_ghi789",
            real_patch_generation_candidate_id="candidate_jkl012",
            real_patch_generation_plan_review_id="review_mno345",
            real_patch_generation_plan_id="plan_pqr678",
            front_id="MEMORY_RAG_KNOWLEDGE_STRUCTURE",
            category="retrieval_provenance_gap",
            patch_type="harness_patch",
            target_files_suggested=["tests/smoke/*"],
            target_files_not_modified=["tests/smoke/*"],
        ),
    ]

    governance = {
        "governance_id": "gov_gen",
        "status": "inert_patch_generation_dry_run_only_not_executable",
        "generated_patch_drafts_count": 3,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "requires_operator_approval": True,
    }

    summary = {
        "ok": True,
        "generated_patch_drafts_count": 3,
        "upstream_empty": False,
        "functional_dry_run_passed": True,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_drafts.json").write_text(json.dumps(drafts, indent=2), encoding="utf-8")
    with open(out / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
        for d in drafts:
            fh.write(json.dumps(d) + "\n")
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

    governance = {
        "governance_id": "gov_empty",
        "status": "inert_patch_generation_dry_run_only_not_executable",
        "generated_patch_drafts_count": 0,
    }
    summary = {
        "ok": False,
        "generated_patch_drafts_count": 0,
        "upstream_empty": True,
        "failure_reason": "empty_real_patch_generation_queue",
        "functional_dry_run_passed": False,
        "token_leak_detected": False,
        "timestamp": "2026-06-07T00:00:00Z",
        "output_dir": str(out),
    }

    (out / "first_five_real_patch_drafts.json").write_text("[]", encoding="utf-8")
    with open(out / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
        pass
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
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_dry_run", _mock_gen_result)
    return mod


@pytest.fixture
def empty_module(monkeypatch):
    """Import module with empty upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)
    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_dry_run", _mock_empty_gen)
    return mod


class TestModuleExists:
    def test_import_module(self, module):
        assert module is not None

    def test_now_utc_exists(self, module):
        assert callable(module.now_utc)

    def test_load_real_patch_draft_artifacts_exists(self, module):
        assert callable(module.load_real_patch_draft_artifacts)

    def test_review_inert_patch_draft_exists(self, module):
        assert callable(module.review_inert_patch_draft)

    def test_review_all_inert_patch_drafts_exists(self, module):
        assert callable(module.review_all_inert_patch_drafts)

    def test_build_real_patch_materialization_planning_queue_exists(self, module):
        assert callable(module.build_real_patch_materialization_planning_queue)

    def test_build_real_patch_generation_review_governance_exists(self, module):
        assert callable(module.build_real_patch_generation_review_governance)

    def test_summarize_real_patch_generation_review_exists(self, module):
        assert callable(module.summarize_real_patch_generation_review)

    def test_run_first_five_real_patch_generation_review_dry_run_exists(self, module):
        assert callable(module.run_first_five_real_patch_generation_review_dry_run)


class TestReviewScoresAndDecisions:
    def test_review_has_score(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "review_score" in r
            assert 0.0 <= r["review_score"] <= 1.0

    def test_review_has_decision(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "decision" in r
            assert r["decision"] in ("approve_for_materialization_planning", "reject", "request_more_tests", "request_scope_reduction", "request_inertness_fix", "request_more_evidence")

    def test_review_has_scores(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "scores" in r
            for k in ("draft_completeness", "inertness_safety", "safety_guards", "scope_protection", "human_review_readiness"):
                assert k in r["scores"]

    def test_safe_inert_draft_approved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        approved = [r for r in reviews if r["decision"] == "approve_for_materialization_planning"]
        assert len(approved) >= 1

    def test_score_weights_capped(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert r["review_score"] <= 1.0


class TestRejections:
    def _run_with_override(self, tmp_path, module, monkeypatch, **kwargs):
        out = tmp_path / "review"
        # Create a mock that returns drafts with the override applied
        def mock_gen_with_override(output_dir=None):
            assert output_dir is not None
            result = _mock_gen_result(output_dir)
            drafts = json.loads((Path(output_dir) / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
            drafts[0].update(kwargs)
            (Path(output_dir) / "first_five_real_patch_drafts.json").write_text(json.dumps(drafts, indent=2), encoding="utf-8")
            with open(Path(output_dir) / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
                for d in drafts:
                    fh.write(json.dumps(d) + "\n")
            return result

        monkeypatch.setattr(module, "run_first_five_real_patch_generation_dry_run", mock_gen_with_override)
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        return reviews[0]

    def test_applicable_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, applicable=True)
        assert r["decision"] == "reject"

    def test_dry_run_only_false_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, dry_run_only=False)
        assert r["decision"] == "reject"

    def test_not_for_git_apply_false_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, not_for_git_apply=False)
        assert r["decision"] == "reject"

    def test_pseudo_diff_is_applicable_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, pseudo_diff_is_applicable=True)
        assert r["decision"] == "reject"

    def test_pseudo_diff_starts_diff_git_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, pseudo_diff_text="diff --git a/foo b/foo\n--- a/foo\n+++ b/foo")
        assert r["decision"] == "reject"

    def test_pseudo_diff_contains_a_b_prefixes_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, pseudo_diff_text="--- a/foo\n+++ b/foo")
        assert r["decision"] == "reject"

    def test_patch_generation_allowed_now_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, patch_generation_allowed_now=True)
        assert r["decision"] == "reject"

    def test_diff_generation_allowed_now_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, diff_generation_allowed_now=True)
        assert r["decision"] == "reject"

    def test_patch_application_allowed_now_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, patch_application_allowed_now=True)
        assert r["decision"] == "reject"

    def test_real_patch_application_allowed_now_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, real_patch_application_allowed_now=True)
        assert r["decision"] == "reject"

    def test_patches_generated_for_application_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, patches_generated_for_application=True)
        assert r["decision"] == "reject"

    def test_patches_applied_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, patches_applied=True)
        assert r["decision"] == "reject"

    def test_patches_staged_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, patches_staged=True)
        assert r["decision"] == "reject"

    def test_memory_write_allowed_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, memory_write_allowed=True)
        assert r["decision"] == "reject"

    def test_faiss_write_allowed_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, faiss_write_allowed=True)
        assert r["decision"] == "reject"

    def test_real_write_allowed_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, real_write_allowed=True)
        assert r["decision"] == "reject"

    def test_promotion_allowed_true_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, promotion_allowed=True)
        assert r["decision"] == "reject"

    def test_forbidden_target_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, target_files_suggested=["memory/semantic/foo.json"], target_files_not_modified=["memory/semantic/foo.json"])
        assert r["decision"] == "reject"

    def test_target_files_not_modified_mismatch_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, target_files_not_modified=["different/file.py"])
        assert r["decision"] == "reject"

    def test_approval_allows_git_apply_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, operator_approval_packet={"required": True, "approval_does_not_allow_patch_application": True, "approval_does_not_allow_git_apply": False})
        assert r["decision"] == "reject"

    def test_approval_allows_patch_application_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, operator_approval_packet={"required": True, "approval_does_not_allow_patch_application": False, "approval_does_not_allow_git_apply": True})
        assert r["decision"] == "reject"

    def test_missing_rollback_rejected(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, rollback_plan={})
        assert r["decision"] == "reject"


class TestRequests:
    def _run_with_override(self, tmp_path, module, monkeypatch, **kwargs):
        out = tmp_path / "review"
        def mock_gen_with_override(output_dir=None):
            assert output_dir is not None
            result = _mock_gen_result(output_dir)
            drafts = json.loads((Path(output_dir) / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
            drafts[0].update(kwargs)
            (Path(output_dir) / "first_five_real_patch_drafts.json").write_text(json.dumps(drafts, indent=2), encoding="utf-8")
            with open(Path(output_dir) / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
                for d in drafts:
                    fh.write(json.dumps(d) + "\n")
            return result
        monkeypatch.setattr(module, "run_first_five_real_patch_generation_dry_run", mock_gen_with_override)
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        return reviews[0]

    def test_missing_do_not_run_git_apply_request_inertness_fix(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, pseudo_diff_text="DRY-RUN ONLY\nThis is an inert human-review draft.")
        assert r["decision"] == "request_inertness_fix"

    def test_missing_inert_human_review_draft_request_inertness_fix(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, pseudo_diff_text="DRY-RUN ONLY\nDo not run git apply.")
        assert r["decision"] == "request_inertness_fix"

    def test_missing_required_tests_request_more_tests(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, required_tests=[])
        assert r["decision"] == "request_more_tests"

    def test_missing_acceptance_criteria_request_more_tests(self, tmp_path, module, monkeypatch):
        r = self._run_with_override(tmp_path, module, monkeypatch, acceptance_criteria=[])
        assert r["decision"] == "request_more_tests"


class TestQueue:
    def test_queue_includes_only_approved_reviews(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        queue = json.loads((out / "first_five_real_patch_materialization_planning_queue.json").read_text(encoding="utf-8"))
        approved_ids = {r["real_patch_generation_review_id"] for r in reviews if r["decision"] == "approve_for_materialization_planning"}
        queue_ids = {q["real_patch_generation_review_id"] for q in queue}
        assert queue_ids == approved_ids

    def test_queue_flags_false(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        queue = json.loads((out / "first_five_real_patch_materialization_planning_queue.json").read_text(encoding="utf-8"))
        for q in queue:
            assert q["patch_generation_allowed_now"] is False
            assert q["diff_generation_allowed_now"] is False
            assert q["patch_application_allowed_now"] is False
            assert q["real_patch_application_allowed_now"] is False

    def test_queue_next_safe_front_correct(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        queue = json.loads((out / "first_five_real_patch_materialization_planning_queue.json").read_text(encoding="utf-8"))
        for q in queue:
            assert q["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-DRY-RUN-01"

    def test_queue_count_le_reviews_count(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["materialization_planning_queue_count"] <= result["reviews_count"]

    def test_approved_count_matches_queue_count(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["approved_for_materialization_planning"] == result["materialization_planning_queue_count"]


class TestGovernance:
    def test_governance_status_correct(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["status"] == "inert_patch_generation_review_only_not_executable"

    def test_governance_flags_false(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
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
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-DRY-RUN-01"

    def test_governance_must_not_create_patch_files_true(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_create_patch_files"] is True

    def test_governance_must_not_run_git_apply_true(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_run_git_apply"] is True

    def test_governance_requires_operator_approval(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["requires_operator_approval"] is True

    def test_governance_writes_allowed_false(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_review_governance.json").read_text(encoding="utf-8"))
        assert gov["writes_allowed"] is False


class TestOutputs:
    def test_output_files_written(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert (out / "first_five_real_patch_generation_reviews.json").exists()
        assert (out / "first_five_real_patch_generation_reviews.jsonl").exists()
        assert (out / "first_five_real_patch_materialization_planning_queue.json").exists()
        assert (out / "first_five_real_patch_generation_review_governance.json").exists()
        assert (out / "first_five_real_patch_generation_review_summary.json").exists()
        assert (out / "first_five_real_patch_generation_review_report.md").exists()

    def test_jsonl_written(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        lines = (out / "first_five_real_patch_generation_reviews.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == len(reviews)
        for line in lines:
            json.loads(line)

    def test_report_spanish_readable(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        report = (out / "first_five_real_patch_generation_review_report.md").read_text(encoding="utf-8")
        assert "Resumen" in report
        assert "Gobernanza" in report
        assert "Que NO Se Genero" in report


class TestEmptyUpstream:
    def test_empty_upstream_returns_ok_false(self, tmp_path, empty_module):
        out = tmp_path / "review_empty"
        result = empty_module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["ok"] is False

    def test_empty_upstream_upstream_empty_true(self, tmp_path, empty_module):
        out = tmp_path / "review_empty"
        result = empty_module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["upstream_empty"] is True

    def test_empty_upstream_failure_reason(self, tmp_path, empty_module):
        out = tmp_path / "review_empty"
        result = empty_module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["failure_reason"] == "empty_real_patch_drafts"

    def test_empty_upstream_recommended_next_not_application(self, tmp_path, empty_module):
        out = tmp_path / "review_empty"
        result = empty_module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert "application" not in result["recommended_next_action"].lower()


class TestSummary:
    def test_reviews_count_at_least_one(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["reviews_count"] >= 1

    def test_summary_upstream_empty_false(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("upstream_empty") is False

    def test_summary_functional_dry_run_passed_true(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("functional_dry_run_passed") is True

    def test_summary_recommended_next_correct(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert "materialization_planning" in result["recommended_next_action"]

    def test_no_token_leak(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("token_leak_detected") is False

    def test_output_dir_recorded(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["output_dir"] == str(out)


class TestSafetyFlags:
    def test_no_patches_generated_for_application(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["patches_generated_for_application"] is False

    def test_no_patches_applied(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["patches_applied"] is False

    def test_no_patches_staged(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["patches_staged"] is False

    def test_no_memory_write(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["memory_write_allowed"] is False

    def test_no_faiss_write(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["faiss_write_allowed"] is False

    def test_no_real_write(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["real_write_allowed"] is False

    def test_no_promotion(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result["promotion_allowed"] is False

    def test_no_runtime_chat_integration(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("runtime_chat_integration") is None or result.get("runtime_chat_integration") is False

    def test_no_trading(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("trading_used") is None or result.get("trading_used") is False

    def test_no_b8(self, tmp_path, module):
        out = tmp_path / "review"
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        assert result.get("b8_touched") is None or result.get("b8_touched") is False

    def test_no_target_file_modified(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "target file modified" not in r.get("blocking_issues", [])

    def test_no_applicable_diff_generated(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "pseudo_diff_is_applicable is true" not in r.get("blocking_issues", [])

    def test_no_patch_file_generated(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        patch_files = list(out.rglob("*.patch"))
        assert len(patch_files) == 0

    def test_no_git_stage_implied(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "patches_staged is true" not in r.get("blocking_issues", [])


class TestPreservation:
    def test_required_tests_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "required_tests" in r or r.get("decision") != "approve_for_materialization_planning"

    def test_acceptance_criteria_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "acceptance_criteria" in r or r.get("decision") != "approve_for_materialization_planning"

    def test_risk_level_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "risk_level" in r

    def test_draft_ids_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert r["real_patch_draft_id"].startswith("draft_")

    def test_category_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert r["category"] in ("evaluation_gate_gap", "security_supply_chain_gap", "retrieval_provenance_gap")

    def test_patch_type_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert r["patch_type"] in ("test_patch", "policy_patch", "harness_patch")

    def test_front_id_preserved(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert r["front_id"]

    def test_reviewed_at_present(self, tmp_path, module):
        out = tmp_path / "review"
        module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        for r in reviews:
            assert "reviewed_at" in r and r["reviewed_at"]


class TestDecisionLogic:
    def test_decision_reject_beats_approve(self, tmp_path, module, monkeypatch):
        out = tmp_path / "review"
        def mock_gen_bad_draft(output_dir=None):
            assert output_dir is not None
            result = _mock_gen_result(output_dir)
            drafts = json.loads((Path(output_dir) / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
            drafts[0]["applicable"] = True
            drafts[0]["dry_run_only"] = True
            drafts[0]["pseudo_diff_is_applicable"] = False
            (Path(output_dir) / "first_five_real_patch_drafts.json").write_text(json.dumps(drafts, indent=2), encoding="utf-8")
            with open(Path(output_dir) / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
                for d in drafts:
                    fh.write(json.dumps(d) + "\n")
            return result
        monkeypatch.setattr(module, "run_first_five_real_patch_generation_dry_run", mock_gen_bad_draft)
        result = module.run_first_five_real_patch_generation_review_dry_run(str(out))
        reviews = json.loads((out / "first_five_real_patch_generation_reviews.json").read_text(encoding="utf-8"))
        assert reviews[0]["decision"] == "reject"
