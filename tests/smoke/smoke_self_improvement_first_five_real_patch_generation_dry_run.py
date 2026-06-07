"""Smoke tests for first five real patch generation dry-run.

Mocks the upstream review module to avoid deep chain recursion.
Follows the pattern from sibling smoke test files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, r"C:\AI_VAULT")

import pytest

MODULE_PATH = "brain.external_sources.self_improvement_first_five_real_patch_generation_dry_run"


def _mock_review_result(output_dir: str | None = None, queue: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Mock upstream review dry-run that writes artifacts."""
    out = Path(output_dir) if output_dir else Path("tmp_agent/mock_review")
    out.mkdir(parents=True, exist_ok=True)
    queue = queue or []

    reviews = []
    for q in queue:
        reviews.append({
            "real_patch_generation_plan_review_id": q.get("real_patch_generation_plan_review_id", ""),
            "real_patch_generation_plan_id": q.get("real_patch_generation_plan_id", ""),
            "real_patch_generation_candidate_id": q.get("real_patch_generation_candidate_id", ""),
            "front_id": q.get("front_id", ""),
            "category": q.get("category", ""),
            "patch_type": q.get("patch_type", ""),
            "decision": "approve_for_real_patch_generation_dry_run",
            "review_score": 0.95,
            "required_tests": q.get("required_tests", ["python -m pytest tests/smoke -q"]),
            "acceptance_criteria": q.get("acceptance_criteria", ["operator review required"]),
            "risk_level": q.get("risk_level", "medium"),
            "risk_notes": "safe dry-run only",
        })

    (out / "first_five_real_patch_generation_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
    (out / "first_five_real_patch_generation_plan_reviews.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    (out / "first_five_real_patch_generation_plan_review_summary.json").write_text(
        json.dumps({"reviews_count": len(queue), "approved_for_real_patch_generation_dry_run": len(queue)}, indent=2),
        encoding="utf-8",
    )
    (out / "first_five_real_patch_generation_plan_review_governance.json").write_text(
        json.dumps({
            "status": "review_only_not_executable",
            "reviews_count": len(queue),
            "approved_for_real_patch_generation_dry_run": len(queue),
            "patch_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "next_safe_front": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-DRY-RUN-01",
        }, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": len(queue) > 0,
        "reviews_count": len(queue),
        "approved_for_real_patch_generation_dry_run": len(queue),
        "output_dir": str(out),
    }


@pytest.fixture
def sample_queue() -> List[Dict[str, Any]]:
    return [
        {
            "real_patch_generation_candidate_id": "candidate_01",
            "real_patch_generation_plan_review_id": "review_01",
            "real_patch_generation_plan_id": "plan_01",
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
            "real_patch_generation_candidate_id": "candidate_02",
            "real_patch_generation_plan_review_id": "review_02",
            "real_patch_generation_plan_id": "plan_02",
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
            "real_patch_generation_candidate_id": "candidate_03",
            "real_patch_generation_plan_review_id": "review_03",
            "real_patch_generation_plan_id": "plan_03",
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


@pytest.fixture
def module(monkeypatch, sample_queue):
    """Import module with mocked upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)

    def mock_run(output_dir=None):
        return _mock_review_result(output_dir, sample_queue)

    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_plan_review_dry_run", mock_run)
    return mod


@pytest.fixture
def empty_module(monkeypatch):
    """Import module with empty upstream dependency."""
    import importlib
    mod = importlib.import_module(MODULE_PATH)

    def mock_empty(output_dir=None):
        return _mock_review_result(output_dir, [])

    monkeypatch.setattr(mod, "run_first_five_real_patch_generation_plan_review_dry_run", mock_empty)
    return mod


class TestModuleExists:
    def test_import_module(self, module):
        assert module is not None

    def test_now_utc_exists(self, module):
        assert callable(module.now_utc)

    def test_load_real_patch_generation_queue_artifacts_exists(self, module):
        assert callable(module.load_real_patch_generation_queue_artifacts)

    def test_generate_inert_patch_draft_exists(self, module):
        assert callable(module.generate_inert_patch_draft)

    def test_generate_all_inert_patch_drafts_exists(self, module):
        assert callable(module.generate_all_inert_patch_drafts)

    def test_build_real_patch_generation_governance_exists(self, module):
        assert callable(module.build_real_patch_generation_governance)

    def test_summarize_real_patch_generation_exists(self, module):
        assert callable(module.summarize_real_patch_generation)

    def test_run_first_five_real_patch_generation_dry_run_exists(self, module):
        assert callable(module.run_first_five_real_patch_generation_dry_run)


class TestDraftStructure:
    def test_draft_status_correct(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["draft_status"] == "inert_patch_draft_dry_run_only"

    def test_dry_run_only_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["dry_run_only"] is True

    def test_applicable_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["applicable"] is False

    def test_not_for_git_apply_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["not_for_git_apply"] is True

    def test_pseudo_diff_is_applicable_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["pseudo_diff_is_applicable"] is False

    def test_pseudo_diff_header_correct(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["pseudo_diff_header"] == "DRY-RUN ONLY — NOT A GIT PATCH"

    def test_pseudo_diff_does_not_start_diff_git(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert not d["pseudo_diff_text"].startswith("diff --git")

    def test_pseudo_diff_does_not_contain_a_b_prefixes(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert "--- a/" not in d["pseudo_diff_text"]
            assert "+++ b/" not in d["pseudo_diff_text"]

    def test_patch_generation_allowed_now_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patch_generation_allowed_now"] is False

    def test_diff_generation_allowed_now_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["diff_generation_allowed_now"] is False

    def test_patch_application_allowed_now_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patch_application_allowed_now"] is False

    def test_real_patch_application_allowed_now_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["real_patch_application_allowed_now"] is False

    def test_patches_generated_for_application_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patches_generated_for_application"] is False

    def test_patches_applied_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patches_applied"] is False

    def test_patches_staged_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patches_staged"] is False

    def test_memory_write_allowed_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["memory_write_allowed"] is False

    def test_faiss_write_allowed_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["faiss_write_allowed"] is False

    def test_real_write_allowed_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["real_write_allowed"] is False

    def test_promotion_allowed_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["promotion_allowed"] is False

    def test_operator_approval_required_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["operator_approval_packet"]["required"] is True

    def test_approval_does_not_allow_patch_application(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["operator_approval_packet"]["approval_does_not_allow_patch_application"] is True

    def test_approval_does_not_allow_git_apply(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["operator_approval_packet"]["approval_does_not_allow_git_apply"] is True

    def test_rollback_required_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["rollback_plan"]["required"] is True

    def test_required_tests_preserved(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["required_tests"] == sample_queue[i]["required_tests"]

    def test_acceptance_criteria_preserved(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["acceptance_criteria"] == sample_queue[i]["acceptance_criteria"]

    def test_target_files_preserved(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["target_files_suggested"] == sample_queue[i]["target_files_allowed_for_future_patch"]

    def test_target_files_not_modified(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["target_files_not_modified"] == d["target_files_suggested"]

    def test_human_review_required_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["human_review_required"] is True

    def test_pseudo_diff_contains_do_not_run_git_apply(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert "Do not run git apply" in d["pseudo_diff_text"]

    def test_pseudo_diff_contains_inert_human_review_draft(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert "inert human-review draft" in d["pseudo_diff_text"]

    def test_pseudo_diff_contains_target_file_names(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            for tf in sample_queue[i]["target_files_allowed_for_future_patch"]:
                assert tf in d["pseudo_diff_text"]

    def test_draft_includes_category(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["category"] == sample_queue[i]["category"]

    def test_draft_includes_patch_type(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["patch_type"] == sample_queue[i]["patch_type"]

    def test_draft_includes_front_id(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["front_id"] == sample_queue[i]["front_id"]

    def test_draft_includes_real_patch_generation_plan_review_id(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["real_patch_generation_plan_review_id"] == sample_queue[i]["real_patch_generation_plan_review_id"]

    def test_created_at_present(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert "created_at" in d and d["created_at"]

    def test_risk_level_preserved_or_fallback_medium(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for i, d in enumerate(drafts):
            assert d["risk_level"] == sample_queue[i].get("risk_level", "medium")

    def test_draft_ids_stable(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["real_patch_draft_id"].startswith("draft_")
            assert len(d["real_patch_draft_id"]) > 8


class TestGovernance:
    def test_governance_status_correct(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
        assert gov["status"] == "inert_patch_generation_dry_run_only_not_executable"

    def test_governance_flags_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
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

    def test_governance_next_safe_front_correct(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
        assert gov["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-REVIEW-DRY-RUN-01"

    def test_governance_must_not_create_patch_files_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_create_patch_files"] is True

    def test_governance_must_not_run_git_apply_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
        assert gov["must_not_run_git_apply"] is True

    def test_governance_requires_operator_approval(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        gov = json.loads((out / "first_five_real_patch_generation_governance.json").read_text(encoding="utf-8"))
        assert gov["requires_operator_approval"] is True

    def test_rollback_preserves_dirty_preexisting_files(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["rollback_plan"]["preserve_dirty_preexisting_files"] is True


class TestOutputs:
    def test_output_files_written(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        assert (out / "first_five_real_patch_drafts.json").exists()
        assert (out / "first_five_real_patch_drafts.jsonl").exists()
        assert (out / "first_five_real_patch_generation_governance.json").exists()
        assert (out / "first_five_real_patch_generation_summary.json").exists()
        assert (out / "first_five_real_patch_generation_report.md").exists()

    def test_jsonl_written(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        lines = (out / "first_five_real_patch_drafts.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == len(sample_queue)
        for line in lines:
            json.loads(line)

    def test_report_spanish_readable(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        report = (out / "first_five_real_patch_generation_report.md").read_text(encoding="utf-8")
        assert "Resumen" in report
        assert "Gobernanza" in report
        assert "Que NO Se Genero" in report

    def test_no_patch_files_generated(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        patch_files = list(out.rglob("*.patch"))
        assert len(patch_files) == 0

    def test_only_writes_to_output_dir(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        before = set(p.name for p in tmp_path.iterdir())
        module.run_first_five_real_patch_generation_dry_run(str(out))
        after = set(p.name for p in tmp_path.iterdir())
        assert after == before or (after - before) == {"gen"}


class TestEmptyQueue:
    def test_empty_queue_returns_ok_false(self, tmp_path, empty_module):
        out = tmp_path / "gen_empty"
        result = empty_module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["ok"] is False

    def test_empty_queue_upstream_empty_true(self, tmp_path, empty_module):
        out = tmp_path / "gen_empty"
        result = empty_module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["upstream_empty"] is True

    def test_empty_queue_failure_reason(self, tmp_path, empty_module):
        out = tmp_path / "gen_empty"
        result = empty_module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["failure_reason"] == "empty_real_patch_generation_queue"

    def test_empty_queue_recommended_next_not_application(self, tmp_path, empty_module):
        out = tmp_path / "gen_empty"
        result = empty_module.run_first_five_real_patch_generation_dry_run(str(out))
        assert "application" not in result["recommended_next_action"].lower()


class TestSummary:
    def test_generated_patch_drafts_count(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["generated_patch_drafts_count"] == len(sample_queue)

    def test_summary_upstream_empty_false(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("upstream_empty") is False

    def test_summary_functional_dry_run_passed_true(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("functional_dry_run_passed") is True

    def test_summary_recommended_next_correct(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert "patch_generation_review_dry_run" in result["recommended_next_action"]

    def test_queue_count_equals_draft_count(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["generated_patch_drafts_count"] == len(sample_queue)

    def test_generated_count_at_least_one(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["generated_patch_drafts_count"] >= 1

    def test_output_dir_recorded(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["output_dir"] == str(out)

    def test_no_token_leak(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("token_leak_detected") is False


class TestSafetyFlags:
    def test_no_patches_generated_for_application(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["patches_generated_for_application"] is False

    def test_no_patches_applied(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["patches_applied"] is False

    def test_no_patches_staged(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["patches_staged"] is False

    def test_no_memory_write(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["memory_write_allowed"] is False

    def test_no_faiss_write(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["faiss_write_allowed"] is False

    def test_no_real_write(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["real_write_allowed"] is False

    def test_no_promotion(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result["promotion_allowed"] is False

    def test_no_runtime_chat_integration(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("runtime_chat_integration") is None or result.get("runtime_chat_integration") is False

    def test_no_trading(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("trading_used") is None or result.get("trading_used") is False

    def test_no_b8(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        result = module.run_first_five_real_patch_generation_dry_run(str(out))
        assert result.get("b8_touched") is None or result.get("b8_touched") is False

    def test_no_target_file_modified(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["target_files_not_modified"] == d["target_files_suggested"]

    def test_no_applicable_diff_generated(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["pseudo_diff_is_applicable"] is False
            assert d["applicable"] is False

    def test_no_git_stage_implied(self, tmp_path, module, sample_queue):
        out = tmp_path / "gen"
        module.run_first_five_real_patch_generation_dry_run(str(out))
        drafts = json.loads((out / "first_five_real_patch_drafts.json").read_text(encoding="utf-8"))
        for d in drafts:
            assert d["patches_staged"] is False
