"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-AUTONOMOUS-CODING-PATCH-GENERATION-01
"""

import json
import subprocess
from pathlib import Path

import pytest

from brain.external_curated_learning_autonomous_coding_patch_generation import (
    brain_coding_capability_map,
    build_curated_learning_plan,
    canonical_taxonomy,
    cross_source_contrast_matrix,
    front_id,
    knowledge_record_schema,
    learning_domain,
    seed_candidate_sources,
    source_acceptance_criteria,
    source_contrast_scoring_rubric,
    source_rejection_criteria,
    source_safety_scoring_rubric,
    summarize_curated_learning_plan,
)


class TestModuleIntegrity:
    def test_front_id_exact(self):
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-AUTONOMOUS-CODING-PATCH-GENERATION-01"

    def test_learning_domain_id(self):
        d = learning_domain()
        assert d["id"] == "autonomous_coding_patch_generation"
        assert d["macro_order"] == 5


class TestTaxonomy:
    def test_taxonomy_count(self):
        tax = canonical_taxonomy()
        assert len(tax) >= 25

    def test_taxonomy_includes_codebase_navigation(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "codebase_navigation" in ids

    def test_taxonomy_includes_issue_understanding(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "issue_understanding" in ids

    def test_taxonomy_includes_bug_localization(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "bug_localization" in ids

    def test_taxonomy_includes_patch_planning(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "patch_planning" in ids

    def test_taxonomy_includes_diff_generation(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "diff_generation" in ids

    def test_taxonomy_includes_test_driven_repair(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "test_driven_repair" in ids

    def test_taxonomy_includes_regression_testing(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "regression_testing" in ids

    def test_taxonomy_includes_static_analysis(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "static_analysis" in ids

    def test_taxonomy_includes_ci_validation(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "ci_validation" in ids

    def test_taxonomy_includes_patch_review(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "patch_review" in ids

    def test_taxonomy_includes_small_commit_discipline(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "small_commit_discipline" in ids

    def test_taxonomy_includes_rollback_revert(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "rollback_revert_strategy" in ids

    def test_taxonomy_includes_swe_bench_eval(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "swe_bench_style_evaluation" in ids

    def test_taxonomy_includes_code_execution_sandboxing(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "code_execution_sandboxing" in ids

    def test_taxonomy_includes_tool_use_governance(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "tool_use_governance_for_coding" in ids

    def test_taxonomy_includes_protected_file_boundaries(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "protected_file_boundaries" in ids

    def test_taxonomy_includes_financial_code_safety(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "financial_code_safety_readiness" in ids


class TestRubrics:
    def test_source_acceptance_criteria_present(self):
        assert source_acceptance_criteria()

    def test_source_rejection_criteria_present(self):
        assert source_rejection_criteria()

    def test_source_safety_scoring_rubric_present(self):
        r = source_safety_scoring_rubric()
        assert "dimensions" in r
        assert r.get("max_possible") == 95

    def test_source_contrast_scoring_rubric_present(self):
        r = source_contrast_scoring_rubric()
        assert "contrast_types" in r


class TestCapabilityMap:
    def test_brain_coding_capability_map_count(self):
        assert len(brain_coding_capability_map()) >= 20


class TestSources:
    def test_seed_count(self):
        sources = seed_candidate_sources()
        assert len(sources) >= 24

    def test_source_groups_diverse(self):
        groups = {s["source_group"] for s in seed_candidate_sources()}
        assert "paper" in groups
        assert "benchmark" in groups
        assert "repo" in groups
        assert "docs" in groups
        assert "framework" in groups

    def test_each_source_has_required_fields(self):
        required = {"source_id", "title", "url", "taxonomy_tags", "safety_score_estimate", "specific_brain_capability_target", "ingestion_status", "unsafe_code_execution_risk", "repo_state_corruption_risk", "vendor_lock_in_risk"}
        for s in seed_candidate_sources():
            missing = required - set(s.keys())
            assert not missing, f"Missing fields in {s.get('source_id')}: {missing}"

    def test_all_ingestion_status_not_ingested(self):
        for s in seed_candidate_sources():
            assert s["ingestion_status"] == "not_ingested"


class TestContrastMatrix:
    def test_cross_source_contrast_matrix_count(self):
        assert len(cross_source_contrast_matrix()) >= 8


class TestPlan:
    def test_build_plan_status(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["ingestion_status"] == "dry_run_only"

    def test_build_plan_source_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["source_count"] >= 24

    def test_build_plan_taxonomy_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["taxonomy_count"] >= 25

    def test_build_plan_capability_map_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["capability_map_count"] >= 20

    def test_summarize_plan_fields(self):
        summary = summarize_curated_learning_plan()
        assert summary["domain"] == "autonomous_coding_patch_generation"
        assert summary["ingestion_status"] == "dry_run_only"
        assert summary["memory_mutated"] is False
        assert summary["faiss_mutated"] is False


class TestKnowledgeRecordSchema:
    def test_knowledge_record_schema_has_required_fields(self):
        schema = knowledge_record_schema()
        assert "required_fields" in schema
        assert "source_id" in schema["required_fields"]
        assert "unsafe_code_execution_risk" in schema["required_fields"]
        assert "repo_state_corruption_risk" in schema["required_fields"]
        assert "vendor_lock_in_risk" in schema["required_fields"]
        assert "untrusted_executable" in schema["forbidden_fields"]


class TestNoMemoryOrFAISSMutation:
    def test_no_semantic_memory_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
        )
        staged = result.stdout
        for line in staged.splitlines():
            assert "semantic_memory" not in line, f"Memory file staged: {line}"

    def test_no_faiss_index_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
        )
        staged = result.stdout
        for line in staged.splitlines():
            assert "faiss.index" not in line, f"FAISS index staged: {line}"

    def test_no_faiss_ids_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
        )
        staged = result.stdout
        for line in staged.splitlines():
            assert "faiss_ids" not in line, f"FAISS ids staged: {line}"

    def test_no_protected_runtime_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
        )
        staged = result.stdout
        protected = [
            "tmp_agent/brain_v9/core/session.py",
            "tmp_agent/brain_v9/main.py",
            "tmp_agent/brain_v9/core/llm.py",
            "execution_gate.py",
            "brain/curated_runtime_lookup.py",
            "brain/external_curated_learning_agentic_systems.py",
            "brain/external_curated_learning_evaluation_benchmarking.py",
            "brain/external_curated_learning_memory_rag_knowledge_architecture.py",
            "brain/external_curated_learning_security_governance_sandboxing.py",
        ]
        for line in staged.splitlines():
            for p in protected:
                assert p not in line, f"Protected file staged: {line}"


class TestRoadmapAndLedger:
    def test_roadmap_json_valid(self):
        repo = Path(__file__).resolve().parents[2]
        roadmap = repo / "ROADMAP_STATUS.json"
        data = json.loads(roadmap.read_text(encoding="utf-8"))
        assert "completed_fronts" in data or "fronts" in data or "current_head" in data

    def test_ledger_exists(self):
        repo = Path(__file__).resolve().parents[2]
        ledger = repo / "docs" / "MIGRATION_CONTROL_LEDGER.md"
        assert ledger.exists()
        assert "FRONT" in ledger.read_text(encoding="utf-8")
