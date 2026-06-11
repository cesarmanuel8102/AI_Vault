"""Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01."""

import json
import subprocess
from pathlib import Path

import pytest

from brain.external_curated_learning_controlled_ingestion_authorization import (
    authorization_domain,
    authorized_batch_limits,
    authorized_first_canary_scope,
    build_controlled_ingestion_authorization_plan,
    domain_authorization_matrix,
    front_id,
    human_approval_requirements,
    memory_record_schema,
    post_ingestion_validation_rules,
    pre_ingestion_validation_rules,
    read_authorized_domain_order,
    retrieval_quality_eval_requirements,
    rollback_requirements,
    source_exclusion_policy,
    source_to_memory_record_policy,
    summarize_controlled_ingestion_authorization_plan,
)


class TestModuleIdentity:
    def test_front_id(self):
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01"

    def test_authorization_domain_id(self):
        assert authorization_domain()["id"] == "controlled_ingestion_authorization"


class TestPlan:
    def test_plan_status(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["authorization_status"] == "authorization_plan_created_no_mutation"

    def test_actual_memory_mutation_false(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["actual_memory_mutation_authorized"] is False

    def test_actual_faiss_mutation_false(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["actual_faiss_mutation_authorized"] is False

    def test_first_canary_domain(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["first_canary_domain"] == "security_governance_sandboxing"

    def test_first_canary_min(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["first_canary_record_min"] == 3

    def test_first_canary_max(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["first_canary_record_max"] == 5

    def test_financial_domain_locked(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["financial_domain_locked"] is True

    def test_coding_domain_locked(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["autonomous_coding_domain_locked"] is True

    def test_requires_future_user_approval(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["requires_future_user_approval_for_mutation"] is True

    def test_memory_mutated_false(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["memory_mutated"] is False

    def test_faiss_mutated_false(self):
        plan = build_controlled_ingestion_authorization_plan()
        assert plan["summary"]["faiss_mutated"] is False


class TestDomainOrder:
    def test_security_governance_first(self):
        order = read_authorized_domain_order()
        assert order[0]["domain"] == "security_governance_sandboxing"
        assert order[0]["authorization_status"] == "authorized_for_future_canary"

    def test_memory_rag_second(self):
        order = read_authorized_domain_order()
        assert order[1]["domain"] == "memory_rag_knowledge_architecture"
        assert order[1]["authorization_status"] == "authorized_for_future_canary"

    def test_evaluation_third(self):
        order = read_authorized_domain_order()
        assert order[2]["domain"] == "evaluation_benchmarking"
        assert order[2]["authorization_status"] == "authorized_for_future_canary"

    def test_agentic_fourth(self):
        order = read_authorized_domain_order()
        assert order[3]["domain"] == "agentic_systems"
        assert order[3]["authorization_status"] == "authorized_for_future_canary"

    def test_coding_locked(self):
        order = read_authorized_domain_order()
        assert order[4]["domain"] == "autonomous_coding_patch_generation"
        assert order[4]["authorization_status"] == "locked_until_later"

    def test_financial_locked(self):
        order = read_authorized_domain_order()
        assert order[5]["domain"] == "financial_motor_trading_intelligence"
        assert order[5]["authorization_status"] == "locked_until_later"


class TestCanaryScope:
    def test_canary_scope_exists(self):
        scope = authorized_first_canary_scope()
        assert scope["recommended_first_domain"] == "security_governance_sandboxing"

    def test_canary_min_records(self):
        scope = authorized_first_canary_scope()
        assert scope["allowed_record_count_min"] == 3

    def test_canary_max_records(self):
        scope = authorized_first_canary_scope()
        assert scope["allowed_record_count_max"] == 5


class TestBatchLimits:
    def test_canary_batch_max(self):
        limits = authorized_batch_limits()
        assert limits["canary_batch"]["max_records"] <= 5

    def test_controlled_batch_01_max(self):
        limits = authorized_batch_limits()
        assert limits["controlled_batch_01"]["max_records"] <= 20

    def test_financial_batch_locked(self):
        limits = authorized_batch_limits()
        assert limits["financial_batch"]["status"] == "locked"


class TestMemoryRecordSchema:
    def test_schema_exists(self):
        schema = memory_record_schema()
        assert "required_fields" in schema

    def test_schema_has_memory_id(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "memory_id" in names

    def test_schema_has_source_id(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "source_id" in names

    def test_schema_has_source_url(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "source_url" in names

    def test_schema_has_content_summary(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "content_summary" in names

    def test_schema_has_retrieval_phrases(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "retrieval_phrases" in names

    def test_schema_has_faiss_eligible(self):
        schema = memory_record_schema()
        names = [f["name"] for f in schema["required_fields"]]
        assert "faiss_eligible" in names

    def test_forbidden_fields_chain_of_thought(self):
        schema = memory_record_schema()
        assert "chain_of_thought" in schema["forbidden_field_names"]

    def test_forbidden_fields_credentials(self):
        schema = memory_record_schema()
        assert "credentials" in schema["forbidden_field_names"]

    def test_forbidden_fields_broker_api(self):
        schema = memory_record_schema()
        assert "broker_api_data" in schema["forbidden_field_names"]

    def test_forbidden_fields_trading_signal(self):
        schema = memory_record_schema()
        assert "trading_signal" in schema["forbidden_field_names"]

    def test_forbidden_fields_executable_code(self):
        schema = memory_record_schema()
        assert "executable_code" in schema["forbidden_field_names"]

    def test_schema_version_strict(self):
        schema = memory_record_schema()
        assert schema["schema_version"] == "controlled_ingestion_memory_record_v1"


class TestSourcePolicies:
    def test_exclusion_policy_excludes_rejected(self):
        policy = source_exclusion_policy()
        assert "rejected sources" in policy["automatic_exclusion_criteria"]

    def test_exclusion_policy_excludes_hold_canary(self):
        policy = source_exclusion_policy()
        assert "hold sources in canary" in policy["automatic_exclusion_criteria"]

    def test_exclusion_policy_excludes_guaranteed_returns(self):
        policy = source_exclusion_policy()
        assert "guaranteed return claims" in policy["automatic_exclusion_criteria"]

    def test_exclusion_policy_excludes_broker_credentials(self):
        policy = source_exclusion_policy()
        assert "broker or API credential requirements" in policy["automatic_exclusion_criteria"]

    def test_exclusion_policy_excludes_executable_strategy(self):
        policy = source_exclusion_policy()
        assert "executable strategy code" in policy["automatic_exclusion_criteria"]

    def test_exclusion_policy_excludes_private_connector(self):
        policy = source_exclusion_policy()
        assert "private connector material" in policy["automatic_exclusion_criteria"]

    def test_source_to_memory_policy_accept_only(self):
        policy = source_to_memory_record_policy()
        assert policy["accept_only_policy"] is True

    def test_source_to_memory_no_chunking(self):
        policy = source_to_memory_record_policy()
        assert policy["no_chunking"] is True


class TestPreIngestionRules:
    def test_pre_ingestion_backup_required(self):
        rules = pre_ingestion_validation_rules()
        assert rules["backup_requirements"]["copy_semantic_memory_jsonl"] is True

    def test_pre_ingestion_schema_validation(self):
        rules = pre_ingestion_validation_rules()
        assert rules["schema_validation"] is True

    def test_pre_ingestion_duplicate_check(self):
        rules = pre_ingestion_validation_rules()
        assert rules["duplicate_memory_id_check"] is True

    def test_pre_ingestion_human_approval(self):
        rules = pre_ingestion_validation_rules()
        assert rules["human_approval_required_before_mutation"] is True

    def test_pre_ingestion_financial_lock_check(self):
        rules = pre_ingestion_validation_rules()
        assert rules["financial_domain_lock_check"] is True

    def test_pre_ingestion_coding_lock_check(self):
        rules = pre_ingestion_validation_rules()
        assert rules["coding_domain_lock_check"] is True


class TestPostIngestionRules:
    def test_exact_memory_line_count_increase(self):
        rules = post_ingestion_validation_rules()
        assert rules["memory_line_count_increase_exact"] is True

    def test_exact_faiss_ids_count_increase(self):
        rules = post_ingestion_validation_rules()
        assert rules["faiss_ids_count_increase_exact"] is True

    def test_no_orphan_memory_records(self):
        rules = post_ingestion_validation_rules()
        assert rules["no_orphan_memory_records"] is True

    def test_retrieval_smoke_tests(self):
        rules = post_ingestion_validation_rules()
        assert rules["retrieval_smoke_tests_pass"] is True


class TestRetrievalEval:
    def test_retrieval_has_top_1(self):
        req = retrieval_quality_eval_requirements()
        assert "top_1_hit" in req["required_metrics"]

    def test_retrieval_has_top_3(self):
        req = retrieval_quality_eval_requirements()
        assert "top_3_hit" in req["required_metrics"]

    def test_retrieval_has_top_5(self):
        req = retrieval_quality_eval_requirements()
        assert "top_5_hit" in req["required_metrics"]

    def test_retrieval_has_top_10(self):
        req = retrieval_quality_eval_requirements()
        assert "top_10_hit" in req["required_metrics"]

    def test_retrieval_has_mrr(self):
        req = retrieval_quality_eval_requirements()
        assert "MRR" in req["required_metrics"]

    def test_retrieval_has_contamination_check(self):
        req = retrieval_quality_eval_requirements()
        assert "contamination_check" in req["required_metrics"]

    def test_pass_criteria_no_financial_for_governance(self):
        req = retrieval_quality_eval_requirements()
        assert any("No financial source retrieved for governance query" in c for c in req["pass_criteria"])


class TestRollback:
    def test_rollback_restores_memory_jsonl(self):
        req = rollback_requirements()
        assert req["restore_semantic_memory_jsonl"] is True

    def test_rollback_restores_faiss_index(self):
        req = rollback_requirements()
        assert req["restore_semantic_memory_faiss_index"] is True

    def test_rollback_restores_faiss_ids(self):
        req = rollback_requirements()
        assert req["restore_semantic_memory_faiss_ids_json"] is True

    def test_rollback_pre_mutation_backup(self):
        req = rollback_requirements()
        assert req["pre_mutation_backup_required"] is True


class TestHumanApproval:
    def test_human_approval_requires_domain(self):
        req = human_approval_requirements()
        assert "domain" in req["approval_must_include"]

    def test_human_approval_requires_batch_id(self):
        req = human_approval_requirements()
        assert "batch_id" in req["approval_must_include"]

    def test_human_approval_requires_source_ids(self):
        req = human_approval_requirements()
        assert "source_ids" in req["approval_must_include"]

    def test_human_approval_requires_record_count(self):
        req = human_approval_requirements()
        assert "record_count" in req["approval_must_include"]

    def test_human_approval_requires_expected_memory_count(self):
        req = human_approval_requirements()
        assert "expected_memory_line_count_after" in req["approval_must_include"]


class TestDomainAuthorizationMatrix:
    def test_security_governance_canary_authorized(self):
        matrix = domain_authorization_matrix()
        sec = next((d for d in matrix if d["domain"] == "security_governance_sandboxing"), None)
        assert sec["canary_authorized"] is True

    def test_financial_canary_locked(self):
        matrix = domain_authorization_matrix()
        fin = next((d for d in matrix if d["domain"] == "financial_motor_trading_intelligence"), None)
        assert fin["canary_authorized"] is False

    def test_coding_canary_locked(self):
        matrix = domain_authorization_matrix()
        code = next((d for d in matrix if d["domain"] == "autonomous_coding_patch_generation"), None)
        assert code["canary_authorized"] is False


class TestGitSafety:
    def test_no_semantic_memory_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("memory/semantic" in p for p in staged)

    def test_no_faiss_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("faiss" in p.lower() for p in staged)

    def test_no_trading_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("trading/") for p in staged)

    def test_no_b8_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("B8/") for p in staged)

    def test_no_strategies_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("tmp_agent/strategies" in p for p in staged)

    def test_no_previous_curated_modules_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        forbidden = [
            "brain/external_curated_learning_agentic_systems.py",
            "brain/external_curated_learning_evaluation_benchmarking.py",
            "brain/external_curated_learning_memory_rag_knowledge_architecture.py",
            "brain/external_curated_learning_security_governance_sandboxing.py",
            "brain/external_curated_learning_autonomous_coding_patch_generation.py",
            "brain/external_curated_learning_financial_motor_trading_intelligence.py",
        ]
        for f in forbidden:
            assert f not in staged, f"Previous curated module {f} should not be staged"

    def test_roadmap_valid_json(self):
        roadmap = Path(__file__).resolve().parents[2] / "ROADMAP_STATUS.json"
        assert roadmap.exists()
        data = json.loads(roadmap.read_text(encoding="utf-8"))
        assert "current_head" in data
        assert "completed_fronts" in data

    def test_ledger_exists(self):
        ledger = Path(__file__).resolve().parents[2] / "docs" / "MIGRATION_CONTROL_LEDGER.md"
        assert ledger.exists()
        text = ledger.read_text(encoding="utf-8")
        assert len(text) > 0
