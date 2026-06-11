"""Brain external curated learning: Controlled Ingestion Authorization.

This module is AUTHORIZATION-ONLY / NO MUTATION.
- No ingestion into semantic memory in this front
- No FAISS writes in this front
- Only defines policies, schemas, limits, and approval requirements
- Future actual ingestion requires explicit user approval per this plan
"""

import json
import hashlib
from pathlib import Path
from typing import Any


###############################################################################
# Front identity
###############################################################################

def front_id() -> str:
    return "FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01"


def authorization_domain() -> dict[str, Any]:
    return {
        "id": "controlled_ingestion_authorization",
        "name": "Controlled Ingestion Authorization",
        "description": (
            "Authorizes a future safe, controlled, human-approved canary/batch ingestion "
            "of curated external sources into semantic memory and FAISS. "
            "This module does not perform actual ingestion."
        ),
        "scope": "authorization_plan_only_no_mutation",
        "actual_memory_mutation_authorized": False,
        "actual_faiss_mutation_authorized": False,
        "requires_future_user_approval_for_mutation": True,
    }


###############################################################################
# Authorized domain order (G4)
###############################################################################

def read_authorized_domain_order() -> list[dict[str, Any]]:
    return [
        {
            "domain": "security_governance_sandboxing",
            "order": 1,
            "authorization_status": "authorized_for_future_canary",
            "reason": (
                "Security/Governance sources teach constraints and protective controls, "
                "not autonomous actions. Lowest risk of contamination."
            ),
            "max_canary_records": 5,
            "max_batch_records_after_canary": 20,
            "financial_or_execution_risk": "low",
            "requires_human_approval": True,
        },
        {
            "domain": "memory_rag_knowledge_architecture",
            "order": 2,
            "authorization_status": "authorized_for_future_canary",
            "reason": (
                "Memory/RAG sources improve the brain's own knowledge architecture. "
                "No external action risk. Purely infrastructural."
            ),
            "max_canary_records": 5,
            "max_batch_records_after_canary": 20,
            "financial_or_execution_risk": "low",
            "requires_human_approval": True,
        },
        {
            "domain": "evaluation_benchmarking",
            "order": 3,
            "authorization_status": "authorized_for_future_canary",
            "reason": (
                "Evaluation sources teach measurement and validation. "
                "Useful for assessing all subsequent domains."
            ),
            "max_canary_records": 5,
            "max_batch_records_after_canary": 20,
            "financial_or_execution_risk": "low",
            "requires_human_approval": True,
        },
        {
            "domain": "agentic_systems",
            "order": 4,
            "authorization_status": "authorized_for_future_canary",
            "reason": (
                "Agentic sources expand reasoning and planning capabilities. "
                "Moderate risk because they teach autonomous action patterns."
            ),
            "max_canary_records": 5,
            "max_batch_records_after_canary": 20,
            "financial_or_execution_risk": "medium",
            "requires_human_approval": True,
        },
        {
            "domain": "autonomous_coding_patch_generation",
            "order": 5,
            "authorization_status": "locked_until_later",
            "reason": (
                "Coding sources teach code modification. High risk because they could influence "
                "self-modification behavior. Locked until security and governance are proven in memory."
            ),
            "max_canary_records": 0,
            "max_batch_records_after_canary": 0,
            "financial_or_execution_risk": "high",
            "requires_human_approval": True,
        },
        {
            "domain": "financial_motor_trading_intelligence",
            "order": 6,
            "authorization_status": "locked_until_later",
            "reason": (
                "Financial sources have risk of advice contamination, signal contamination, "
                "and trading-action suggestion. Locked until all other domains are proven safe in memory "
                "and explicit financial-action governance is in place."
            ),
            "max_canary_records": 0,
            "max_batch_records_after_canary": 0,
            "financial_or_execution_risk": "high",
            "requires_human_approval": True,
        },
    ]


###############################################################################
# First canary scope (G5)
###############################################################################

def authorized_first_canary_scope() -> dict[str, Any]:
    return {
        "recommended_first_domain": "security_governance_sandboxing",
        "allowed_record_count_min": 3,
        "allowed_record_count_max": 5,
        "allowed_source_status": ["accept"],
        "forbidden_source_status": ["hold", "reject", "candidate"],
        "forbidden_domains_first_canary": [
            "financial_motor_trading_intelligence",
            "autonomous_coding_patch_generation",
        ],
        "allowed_content_type": {
            "metadata_summary_only": True,
            "non_executable_governance_knowledge": True,
            "no_full_paper_text": True,
            "no_full_readme": True,
            "no_external_copyrighted_long_content": True,
        },
        "required_fields": [
            "memory_id",
            "source_id",
            "source_title",
            "source_group",
            "source_url",
            "source_license_or_status",
            "domain",
            "taxonomy_tags",
            "capability_target",
            "source_provenance",
            "safety_score_estimate",
            "acceptance_status",
            "ingestion_batch_id",
            "created_at_utc",
            "content_summary",
            "retrieval_phrases",
            "exclusion_notes",
            "risk_flags",
        ],
        "forbidden_fields": [
            "raw_full_text",
            "copyrighted_full_content",
            "credentials",
            "broker_api_data",
            "trading_signal",
            "executable_code",
            "chain_of_thought",
            "private_user_data",
        ],
    }


###############################################################################
# Batch limits (G6)
###############################################################################

def authorized_batch_limits() -> dict[str, Any]:
    return {
        "canary_batch": {
            "min_records": 3,
            "max_records": 5,
            "one_domain_only": True,
            "allowed_domain": "security_governance_sandboxing",
            "requires_prior_approval": True,
            "requires_backup": True,
            "allows_faiss": False,
        },
        "controlled_batch_01": {
            "min_records": 10,
            "max_records": 20,
            "allowed_domains": [
                "security_governance_sandboxing",
                "memory_rag_knowledge_architecture",
            ],
            "requires_canary_pass": True,
            "requires_prior_approval": True,
            "requires_backup": True,
            "allows_faiss": True,
        },
        "controlled_batch_02": {
            "min_records": 20,
            "max_records": 40,
            "allowed_domains": [
                "security_governance_sandboxing",
                "memory_rag_knowledge_architecture",
                "evaluation_benchmarking",
            ],
            "requires_batch_01_pass": True,
            "requires_prior_approval": True,
            "requires_backup": True,
            "allows_faiss": True,
        },
        "agentic_batch": {
            "status": "locked",
            "reason": "agentic systems knowledge requires proven governance ingestion first",
            "requires_separate_authorization": True,
            "min_records": 0,
            "max_records": 0,
        },
        "coding_batch": {
            "status": "locked",
            "reason": "coding sources may influence self-modification; locked until proven safe",
            "requires_separate_authorization": True,
            "min_records": 0,
            "max_records": 0,
        },
        "financial_batch": {
            "status": "locked",
            "reason": "financial knowledge requires additional no-advice and no-signal controls",
            "requires_separate_authorization": True,
            "min_records": 0,
            "max_records": 0,
        },
    }


###############################################################################
# Memory record schema v1 (G7)
###############################################################################

def memory_record_schema() -> dict[str, Any]:
    return {
        "schema_version": "controlled_ingestion_memory_record_v1",
        "required_fields": [
            {"name": "memory_id", "type": "string", "description": "Deterministic ID: extlearn::{domain}::{source_id}::{schema_version}"},
            {"name": "schema_version", "type": "string", "description": "Must be controlled_ingestion_memory_record_v1"},
            {"name": "source_id", "type": "string", "description": "Source identifier from curation module"},
            {"name": "source_title", "type": "string", "description": "Human-readable title"},
            {"name": "source_group", "type": "string", "description": "paper, repo, docs, regulatory, etc."},
            {"name": "source_url", "type": "string", "description": "Public URL or docs URL"},
            {"name": "source_license_or_status", "type": "string", "description": "License or legal status"},
            {"name": "domain", "type": "string", "description": "Curated learning domain"},
            {"name": "taxonomy_tags", "type": "list[str]", "description": "At least 1 tag from canonical taxonomy"},
            {"name": "capability_target", "type": "string", "description": "Brain capability this source targets"},
            {"name": "source_provenance", "type": "string", "description": "Authors, org, year, maintenance status"},
            {"name": "safety_score_estimate", "type": "integer", "description": "0-125 safety score"},
            {"name": "acceptance_status", "type": "string", "description": "Must be accept"},
            {"name": "ingestion_status", "type": "string", "description": "Begins as proposed"},
            {"name": "ingestion_batch_id", "type": "string", "description": "Batch identifier for tracking"},
            {"name": "created_at_utc", "type": "string", "description": "ISO timestamp"},
            {"name": "content_summary", "type": "string", "description": "Max 1200 chars"},
            {"name": "retrieval_phrases", "type": "list[str]", "description": "3-8 strings for retrieval"},
            {"name": "evidence_type", "type": "string", "description": "paper_summary, repo_metadata, docs_reference, etc."},
            {"name": "risk_flags", "type": "list[str]", "description": "Must exist even if empty"},
            {"name": "exclusion_notes", "type": "string", "description": "Why any content was excluded"},
            {"name": "faiss_eligible", "type": "boolean", "description": "Whether this record may be embedded"},
            {"name": "faiss_embedding_text", "type": "string", "description": "Max 1600 chars for embedding"},
        ],
        "validation_rules": [
            {"rule": "schema_version == 'controlled_ingestion_memory_record_v1'", "severity": "fatal"},
            {"rule": "acceptance_status == 'accept'", "severity": "fatal"},
            {"rule": "ingestion_status in ['proposed', 'approved', 'ingested']", "severity": "fatal"},
            {"rule": "source_url is not empty", "severity": "fatal"},
            {"rule": "len(content_summary) <= 1200", "severity": "error"},
            {"rule": "len(faiss_embedding_text) <= 1600", "severity": "error"},
            {"rule": "len(retrieval_phrases) between 3 and 8", "severity": "error"},
            {"rule": "len(taxonomy_tags) >= 1", "severity": "error"},
            {"rule": "risk_flags is not None", "severity": "error"},
            {"rule": "faiss_eligible is boolean", "severity": "error"},
            {"rule": "no chain-of-thought in any field", "severity": "fatal"},
            {"rule": "no credentials in any field", "severity": "fatal"},
            {"rule": "no broker/API credentials in any field", "severity": "fatal"},
            {"rule": "no trading signal in any field", "severity": "fatal"},
            {"rule": "no executable code in any field", "severity": "fatal"},
        ],
        "forbidden_field_names": [
            "raw_full_text",
            "copyrighted_full_content",
            "credentials",
            "broker_api_data",
            "trading_signal",
            "executable_code",
            "chain_of_thought",
            "private_user_data",
        ],
    }


###############################################################################
# Source to memory record policy (G8)
###############################################################################

def source_to_memory_record_policy() -> dict[str, Any]:
    return {
        "accept_only_policy": True,
        "excluded_statuses": ["hold", "reject", "candidate"],
        "content_scope": "metadata_summary_only",
        "one_record_per_source_per_domain_in_canary": True,
        "no_chunking": True,
        "no_recursive_web_crawling": True,
        "no_full_readme_ingestion": True,
        "no_full_paper_ingestion": True,
        "no_book_content_ingestion": True,
        "no_broker_api_docs_in_first_canary": True,
        "no_financial_source_in_first_canary": True,
        "no_coding_source_in_first_canary": True,
        "memory_id_convention": "extlearn::{domain}::{source_id}::{schema_version}",
        "source_provenance_required": True,
        "risk_flags_preserved": True,
        "required_source_fields_for_memory_record": [
            "source_id",
            "title",
            "source_group",
            "url",
            "license",
            "domain",
            "taxonomy_tags",
            "specific_brain_capability_target",
            "authors_or_org",
            "year_or_first_release",
            "maintenance_status",
            "safety_score_estimate",
            "acceptance_status",
        ],
    }


###############################################################################
# Source exclusion policy (G9)
###############################################################################

def source_exclusion_policy() -> dict[str, Any]:
    return {
        "automatic_exclusion_criteria": [
            "rejected sources",
            "hold sources in canary",
            "candidate sources",
            "unknown attribution",
            "no URL",
            "no license or legal status",
            "guaranteed return claims",
            "signal-selling claims",
            "broker or API credential requirements",
            "executable strategy code",
            "untrusted external code execution",
            "offensive security content not governance-framed",
            "copyrighted full books or papers",
            "private connector material",
            "user-private material",
            "chain-of-thought content",
            "trading/* or B8/* content",
        ],
        "exclusion_rationale": (
            "Only safe, attributable, governance-oriented metadata may enter memory. "
            "All executable, personalized, credential-bearing, or copyrighted content is excluded."
        ),
    }


###############################################################################
# Pre-ingestion validation rules (G10)
###############################################################################

def pre_ingestion_validation_rules() -> dict[str, Any]:
    return {
        "repo_clean_check": True,
        "memory_faiss_baseline_snapshot": True,
        "backup_requirements": {
            "copy_semantic_memory_jsonl": True,
            "copy_semantic_memory_faiss_index": True,
            "copy_semantic_memory_faiss_ids_json": True,
            "verify_backup_integrity": True,
        },
        "schema_validation": True,
        "source_acceptance_validation": True,
        "duplicate_memory_id_check": True,
        "duplicate_source_id_within_batch_check": True,
        "content_length_check": True,
        "forbidden_content_check": True,
        "domain_authorization_check": True,
        "financial_domain_lock_check": True,
        "coding_domain_lock_check": True,
        "faiss_id_uniqueness_check": True,
        "dry_run_preview_required": True,
        "human_approval_required_before_mutation": True,
    }


###############################################################################
# Post-ingestion validation rules (G11)
###############################################################################

def post_ingestion_validation_rules() -> dict[str, Any]:
    return {
        "memory_line_count_increase_exact": True,
        "faiss_ids_count_increase_exact": True,
        "every_new_memory_id_in_semantic_memory_jsonl": True,
        "every_faiss_id_maps_to_valid_memory_record": True,
        "no_orphan_memory_records": True,
        "no_orphan_faiss_ids": True,
        "no_duplicate_memory_id": True,
        "no_duplicate_faiss_id": True,
        "retrieval_smoke_tests_pass": True,
        "top_k_eval_before_after": True,
        "rollback_script_available": True,
        "final_git_diff_inspected_before_commit": True,
    }


###############################################################################
# Retrieval quality eval requirements (G12)
###############################################################################

def retrieval_quality_eval_requirements() -> dict[str, Any]:
    return {
        "pre_ingestion_baseline_queries": [
            "What are the security governance controls?",
            "How does the brain evaluate sources?",
            "What is the memory architecture?",
        ],
        "post_ingestion_same_queries": True,
        "canary_domain_target_queries": [
            "What are the NIST AI RMF controls?",
            "What is the OWASP LLM top 10?",
            "How does gVisor sandboxing work?",
        ],
        "required_metrics": {
            "top_1_hit": "boolean",
            "top_3_hit": "boolean",
            "top_5_hit": "boolean",
            "top_10_hit": "boolean",
            "MRR": "float",
            "domain_precision": "float",
            "contamination_check": "boolean",
            "duplicate_retrieval_check": "boolean",
        },
        "pass_criteria": [
            "No regression on existing baseline queries",
            "Canary records retrievable in top_5",
            "No financial source retrieved for governance query",
            "No coding source retrieved for governance query",
            "No rejected source retrievable",
            "No hold source retrievable",
        ],
    }


###############################################################################
# Rollback requirements (G13)
###############################################################################

def rollback_requirements() -> dict[str, Any]:
    return {
        "pre_mutation_backup_required": True,
        "restore_semantic_memory_jsonl": True,
        "restore_semantic_memory_faiss_index": True,
        "restore_semantic_memory_faiss_ids_json": True,
        "verify_sha_returns_to_baseline": True,
        "verify_line_counts_return_to_baseline": True,
        "verify_faiss_ids_count_returns_to_baseline": True,
        "auto_rollback_triggers": [
            "schema validation fails",
            "line count mismatch",
            "FAISS id mismatch",
            "retrieval regression",
            "duplicate ids",
            "forbidden content detected",
            "wrong domain ingested",
            "financial source ingested accidentally",
            "coding source ingested accidentally",
            "runtime smoke fails",
        ],
    }


###############################################################################
# Human approval requirements (G14)
###############################################################################

def human_approval_requirements() -> dict[str, Any]:
    return {
        "this_front_does_not_grant_actual_mutation_permission": True,
        "future_canary_ingestion_requires_explicit_user_approval": True,
        "approval_must_include": [
            "domain",
            "batch_id",
            "source_ids",
            "record_count",
            "faiss_eligible_count",
            "backup_path",
            "rollback_path",
            "expected_memory_line_count_after",
            "expected_faiss_ids_count_after",
        ],
        "without_approval": {
            "no_memory_mutation": True,
            "no_faiss_mutation": True,
        },
    }


###############################################################################
# Domain authorization matrix
###############################################################################

def domain_authorization_matrix() -> list[dict[str, Any]]:
    return [
        {
            "domain": "security_governance_sandboxing",
            "canary_authorized": True,
            "batch_01_authorized": True,
            "batch_02_authorized": True,
            "faiss_authorized": True,
            "financial_risk": "low",
            "execution_risk": "low",
            "advice_risk": "low",
            "signal_risk": "low",
        },
        {
            "domain": "memory_rag_knowledge_architecture",
            "canary_authorized": True,
            "batch_01_authorized": True,
            "batch_02_authorized": True,
            "faiss_authorized": True,
            "financial_risk": "low",
            "execution_risk": "low",
            "advice_risk": "low",
            "signal_risk": "low",
        },
        {
            "domain": "evaluation_benchmarking",
            "canary_authorized": False,
            "batch_01_authorized": False,
            "batch_02_authorized": True,
            "faiss_authorized": True,
            "financial_risk": "low",
            "execution_risk": "low",
            "advice_risk": "low",
            "signal_risk": "low",
        },
        {
            "domain": "agentic_systems",
            "canary_authorized": False,
            "batch_01_authorized": False,
            "batch_02_authorized": False,
            "faiss_authorized": True,
            "financial_risk": "low",
            "execution_risk": "medium",
            "advice_risk": "low",
            "signal_risk": "low",
        },
        {
            "domain": "autonomous_coding_patch_generation",
            "canary_authorized": False,
            "batch_01_authorized": False,
            "batch_02_authorized": False,
            "faiss_authorized": False,
            "financial_risk": "low",
            "execution_risk": "high",
            "advice_risk": "low",
            "signal_risk": "low",
        },
        {
            "domain": "financial_motor_trading_intelligence",
            "canary_authorized": False,
            "batch_01_authorized": False,
            "batch_02_authorized": False,
            "faiss_authorized": False,
            "financial_risk": "high",
            "execution_risk": "high",
            "advice_risk": "high",
            "signal_risk": "medium",
        },
    ]


###############################################################################
# Build / summarize authorization plan
###############################################################################

def build_controlled_ingestion_authorization_plan() -> dict[str, Any]:
    return {
        "front_id": front_id(),
        "domain": authorization_domain(),
        "authorized_domain_order": read_authorized_domain_order(),
        "first_canary_scope": authorized_first_canary_scope(),
        "batch_limits": authorized_batch_limits(),
        "memory_record_schema": memory_record_schema(),
        "source_to_memory_policy": source_to_memory_record_policy(),
        "source_exclusion_policy": source_exclusion_policy(),
        "domain_authorization_matrix": domain_authorization_matrix(),
        "pre_ingestion_validation": pre_ingestion_validation_rules(),
        "post_ingestion_validation": post_ingestion_validation_rules(),
        "retrieval_quality_eval": retrieval_quality_eval_requirements(),
        "rollback": rollback_requirements(),
        "human_approval": human_approval_requirements(),
        "summary": {
            "authorization_status": "authorization_plan_created_no_mutation",
            "first_canary_domain": "security_governance_sandboxing",
            "first_canary_record_min": 3,
            "first_canary_record_max": 5,
            "actual_memory_mutation_authorized": False,
            "actual_faiss_mutation_authorized": False,
            "financial_domain_locked": True,
            "autonomous_coding_domain_locked": True,
            "requires_future_user_approval_for_mutation": True,
            "memory_mutated": False,
            "faiss_mutated": False,
        },
    }


def summarize_controlled_ingestion_authorization_plan() -> dict[str, Any]:
    plan = build_controlled_ingestion_authorization_plan()
    summary = plan["summary"]
    return {
        "front_id": plan["front_id"],
        "domain_id": plan["domain"]["id"],
        "authorization_status": summary["authorization_status"],
        "first_canary_domain": summary["first_canary_domain"],
        "first_canary_record_min": summary["first_canary_record_min"],
        "first_canary_record_max": summary["first_canary_record_max"],
        "actual_memory_mutation_authorized": summary["actual_memory_mutation_authorized"],
        "actual_faiss_mutation_authorized": summary["actual_faiss_mutation_authorized"],
        "financial_domain_locked": summary["financial_domain_locked"],
        "autonomous_coding_domain_locked": summary["autonomous_coding_domain_locked"],
        "requires_future_user_approval_for_mutation": summary["requires_future_user_approval_for_mutation"],
        "memory_mutated": summary["memory_mutated"],
        "faiss_mutated": summary["faiss_mutated"],
    }


###############################################################################
# Immutability assertion
###############################################################################

def assert_no_memory_or_faiss_mutation(before: dict, after: dict) -> dict:
    errors = []
    for key in ["semantic_memory_jsonl_sha", "semantic_memory_faiss_index_sha", "semantic_memory_faiss_ids_json_sha"]:
        if before.get(key) != after.get(key):
            errors.append(f"{key} changed")
    for key in ["semantic_memory_jsonl_lines", "semantic_memory_faiss_ids_count"]:
        if before.get(key) != after.get(key):
            errors.append(f"{key} count changed")
    return {
        "before": before,
        "after": after,
        "mutated": len(errors) > 0,
        "errors": errors,
    }
