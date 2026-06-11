"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-EVALUATION-BENCHMARKING-01
"""

import json
import subprocess
from pathlib import Path

import pytest

from brain.external_curated_learning_evaluation_benchmarking import (
    brain_evaluation_capability_map,
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
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-EVALUATION-BENCHMARKING-01"

    def test_learning_domain_id(self):
        d = learning_domain()
        assert d["id"] == "evaluation_benchmarking"
        assert d["macro_order"] == 2


class TestTaxonomy:
    def test_taxonomy_count(self):
        tax = canonical_taxonomy()
        assert len(tax) >= 15

    def test_taxonomy_includes_retrieval(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "retrieval_quality_evaluation" in ids

    def test_taxonomy_includes_groundedness(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "groundedness_faithfulness" in ids

    def test_taxonomy_includes_hallucination(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "hallucination_detection" in ids

    def test_taxonomy_includes_regression(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "regression_testing" in ids

    def test_taxonomy_includes_before_after(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "before_after_capability" in ids

    def test_taxonomy_includes_promote_reject_rollback(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "promote_reject_rollback" in ids


class TestRubrics:
    def test_source_acceptance_criteria_present(self):
        assert source_acceptance_criteria()

    def test_source_rejection_criteria_present(self):
        assert source_rejection_criteria()

    def test_source_safety_scoring_rubric_present(self):
        r = source_safety_scoring_rubric()
        assert "dimensions" in r
        assert r.get("max_possible") == 75

    def test_source_contrast_scoring_rubric_present(self):
        r = source_contrast_scoring_rubric()
        assert "contrast_types" in r


class TestCapabilityMap:
    def test_brain_evaluation_capability_map_count(self):
        assert len(brain_evaluation_capability_map()) >= 12


class TestSources:
    def test_seed_count(self):
        sources = seed_candidate_sources()
        assert len(sources) >= 18

    def test_source_groups_diverse(self):
        groups = {s["source_group"] for s in seed_candidate_sources()}
        assert "paper" in groups
        assert "repo" in groups
        assert "docs" in groups
        assert "benchmark" in groups

    def test_each_source_has_required_fields(self):
        required = {"source_id", "title", "url", "taxonomy_tags", "safety_score_estimate", "specific_brain_capability_target", "ingestion_status", "metric_gaming_risk"}
        for s in seed_candidate_sources():
            missing = required - set(s.keys())
            assert not missing, f"Missing fields in {s.get('source_id')}: {missing}"

    def test_all_ingestion_status_not_ingested(self):
        for s in seed_candidate_sources():
            assert s["ingestion_status"] == "not_ingested"


class TestContrastMatrix:
    def test_cross_source_contrast_matrix_count(self):
        assert len(cross_source_contrast_matrix()) >= 6


class TestPlan:
    def test_build_plan_status(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["ingestion_status"] == "dry_run_only"

    def test_build_plan_source_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["source_count"] >= 18

    def test_build_plan_taxonomy_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["taxonomy_count"] >= 15

    def test_build_plan_capability_map_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["capability_map_count"] >= 12

    def test_summarize_plan_fields(self):
        summary = summarize_curated_learning_plan()
        assert summary["domain"] == "evaluation_benchmarking"
        assert summary["ingestion_status"] == "dry_run_only"
        assert summary["memory_mutated"] is False
        assert summary["faiss_mutated"] is False


class TestKnowledgeRecordSchema:
    def test_knowledge_record_schema_has_required_fields(self):
        schema = knowledge_record_schema()
        assert "required_fields" in schema
        assert "source_id" in schema["required_fields"]
        assert "metric_gaming_risk" in schema["required_fields"]


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
