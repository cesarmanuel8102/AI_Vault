"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-SECURITY-GOVERNANCE-SANDBOXING-01
"""

import json
import subprocess
from pathlib import Path

import pytest

from brain.external_curated_learning_security_governance_sandboxing import (
    brain_governance_capability_map,
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
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-SECURITY-GOVERNANCE-SANDBOXING-01"

    def test_learning_domain_id(self):
        d = learning_domain()
        assert d["id"] == "security_governance_sandboxing"
        assert d["macro_order"] == 4


class TestTaxonomy:
    def test_taxonomy_count(self):
        tax = canonical_taxonomy()
        assert len(tax) >= 22

    def test_taxonomy_includes_least_privilege(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "least_privilege" in ids

    def test_taxonomy_includes_rbac(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "role_based_access_control" in ids

    def test_taxonomy_includes_policy_as_code(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "policy_as_code" in ids

    def test_taxonomy_includes_execution_gates(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "execution_gates" in ids

    def test_taxonomy_includes_sandboxed_execution(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "sandboxed_code_execution" in ids

    def test_taxonomy_includes_filesystem_boundaries(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "filesystem_boundaries" in ids

    def test_taxonomy_includes_network_egress(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "network_egress_control" in ids

    def test_taxonomy_includes_secrets_management(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "secrets_management" in ids

    def test_taxonomy_includes_audit_logging(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "audit_logging" in ids

    def test_taxonomy_includes_supply_chain(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "supply_chain_security" in ids

    def test_taxonomy_includes_prompt_injection(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "prompt_injection_defense" in ids

    def test_taxonomy_includes_tool_governance(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "tool_use_governance" in ids

    def test_taxonomy_includes_human_approval(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "human_approval_gates" in ids

    def test_taxonomy_includes_rollback(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "rollback_recovery" in ids

    def test_taxonomy_includes_cot_non_disclosure(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "chain_of_thought_non_disclosure" in ids

    def test_taxonomy_includes_financial_governance(self):
        ids = {t["id"] for t in canonical_taxonomy()}
        assert "financial_action_governance" in ids


class TestRubrics:
    def test_source_acceptance_criteria_present(self):
        assert source_acceptance_criteria()

    def test_source_rejection_criteria_present(self):
        assert source_rejection_criteria()

    def test_source_safety_scoring_rubric_present(self):
        r = source_safety_scoring_rubric()
        assert "dimensions" in r
        assert r.get("max_possible") == 90

    def test_source_contrast_scoring_rubric_present(self):
        r = source_contrast_scoring_rubric()
        assert "contrast_types" in r


class TestCapabilityMap:
    def test_brain_governance_capability_map_count(self):
        assert len(brain_governance_capability_map()) >= 18


class TestSources:
    def test_seed_count(self):
        sources = seed_candidate_sources()
        assert len(sources) >= 22

    def test_source_groups_diverse(self):
        groups = {s["source_group"] for s in seed_candidate_sources()}
        assert "paper" in groups
        assert "standard" in groups
        assert "repo" in groups
        assert "docs" in groups
        assert "framework" in groups

    def test_each_source_has_required_fields(self):
        required = {"source_id", "title", "url", "taxonomy_tags", "safety_score_estimate", "specific_brain_capability_target", "ingestion_status", "privacy_risk", "security_misuse_risk", "vendor_lock_in_risk"}
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
        assert plan["summary"]["source_count"] >= 22

    def test_build_plan_taxonomy_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["taxonomy_count"] >= 22

    def test_build_plan_capability_map_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["capability_map_count"] >= 18

    def test_summarize_plan_fields(self):
        summary = summarize_curated_learning_plan()
        assert summary["domain"] == "security_governance_sandboxing"
        assert summary["ingestion_status"] == "dry_run_only"
        assert summary["memory_mutated"] is False
        assert summary["faiss_mutated"] is False


class TestKnowledgeRecordSchema:
    def test_knowledge_record_schema_has_required_fields(self):
        schema = knowledge_record_schema()
        assert "required_fields" in schema
        assert "source_id" in schema["required_fields"]
        assert "privacy_risk" in schema["required_fields"]
        assert "security_misuse_risk" in schema["required_fields"]
        assert "vendor_lock_in_risk" in schema["required_fields"]
        assert "exploit_code" in schema["forbidden_fields"]
        assert "malware_samples" in schema["forbidden_fields"]


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
