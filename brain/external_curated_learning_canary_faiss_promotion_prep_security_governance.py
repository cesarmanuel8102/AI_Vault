"""
External Curated Learning -- Canary FAISS Promotion Prep (Security / Governance / Sandboxing)
FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01

This module is a PREP DRY-RUN ONLY.
It does NOT ingest into semantic memory or FAISS.
It does NOT create embeddings.
It does NOT modify protected runtime files.

Purpose: Prepare the first canary FAISS promotion package for
security_governance_sandboxing domain, pending future user approval.
"""

import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FRONT_ID = "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01"
BATCH_ID = "SEC_GOV_CANARY_001"
EXPECTED_MEMORY_IDS = [
    "SEC_GOV_CANARY_001_nist_csf_001",
    "SEC_GOV_CANARY_001_nist_ai_rmf_002",
    "SEC_GOV_CANARY_001_opa_docs_003",
    "SEC_GOV_CANARY_001_mitre_atlas_004",
    "SEC_GOV_CANARY_001_gvisor_docs_005",
]
EXPECTED_SOURCE_IDS = ["nist_csf", "nist_ai_rmf", "opa_docs", "mitre_atlas", "gvisor_docs"]
EXPECTED_MEMORY_LINE_COUNT = 1715
EXPECTED_FAISS_IDS_COUNT = 1611
EXPECTED_FAISS_IDS_COUNT_AFTER = 1616


def front_id() -> str:
    return FRONT_ID


def get_batch_id() -> str:
    return BATCH_ID


def get_expected_memory_ids() -> list[str]:
    return EXPECTED_MEMORY_IDS.copy()


def load_canary_records_from_memory(memory_path: str = "memory/semantic/semantic_memory.jsonl") -> list[dict]:
    """Load the 5 canary records from semantic memory. Read-only."""
    records = []
    with open(memory_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                if record.get("ingestion_batch_id") == BATCH_ID:
                    records.append(record)
    return records


def validate_faiss_promotion_candidate(record: dict) -> list[str]:
    """Validate a record as a candidate for FAISS promotion. Returns error strings (empty if valid)."""
    errors = []
    
    if record.get("ingestion_batch_id") != BATCH_ID:
        errors.append("wrong_batch_id")
    
    if record.get("domain") != "security_governance_sandboxing":
        errors.append("wrong_domain")
    
    if record.get("ingestion_status") != "ingested_memory_only":
        errors.append("ingestion_status_not_ingested")
    
    if record.get("acceptance_status") != "accept":
        errors.append("acceptance_status_not_accept")
    
    if record.get("faiss_eligible") is not False:
        errors.append("faiss_eligible_not_false")
    
    if record.get("faiss_embedding_text") != "":
        errors.append("faiss_embedding_text_not_empty")
    
    if record.get("memory_id") not in EXPECTED_MEMORY_IDS:
        errors.append("memory_id_not_in_expected_list")
    
    if record.get("source_id") not in EXPECTED_SOURCE_IDS:
        errors.append("source_id_not_in_expected_list")
    
    forbidden_fields = ["chain_of_thought", "executable_code", "trading_signal", "broker_api"]
    for field in forbidden_fields:
        if field in record:
            errors.append(f"forbidden_field:{field}")
    
    # Check required fields for FAISS promotion
    required_fields = [
        "memory_id", "source_id", "source_title", "domain",
        "taxonomy_tags", "capability_target", "content_summary", "retrieval_phrases"
    ]
    for field in required_fields:
        if not record.get(field):
            errors.append(f"missing_required_field_for_faiss:{field}")
    
    return errors


def build_faiss_embedding_text(record: dict) -> str:
    """Build deterministic embedding text from existing record fields.
    NO model call. NO new data."""
    parts = [
        f"Source: {record.get('source_title', '')}",
        f"ID: {record.get('source_id', '')}",
        f"Domain: {record.get('domain', '')}",
        f"Taxonomy: {', '.join(record.get('taxonomy_tags', []))}",
        f"Capability: {record.get('capability_target', '')}",
        f"Summary: {record.get('content_summary', '')}",
        f"Retrieval phrases: {'; '.join(record.get('retrieval_phrases', []))}",
    ]
    return "\n".join(parts)


def build_faiss_promotion_plan() -> dict:
    """Build the FAISS promotion plan. Read-only."""
    records = load_canary_records_from_memory()
    candidates = []
    
    for rec in records:
        errors = validate_faiss_promotion_candidate(rec)
        embedding_text = build_faiss_embedding_text(rec)
        embedding_sha = hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
        
        candidates.append({
            "memory_id": rec["memory_id"],
            "source_id": rec["source_id"],
            "domain": rec["domain"],
            "source_title": rec.get("source_title", ""),
            "embedding_text_preview": embedding_text[:200] + "..." if len(embedding_text) > 200 else embedding_text,
            "embedding_text_sha256": embedding_sha,
            "validation_errors": errors,
            "valid": len(errors) == 0,
        })
    
    return {
        "front_id": front_id(),
        "batch_id": get_batch_id(),
        "promotion_status": "proposed_only",
        "records_count": len(candidates),
        "current_memory_line_count_expected": EXPECTED_MEMORY_LINE_COUNT,
        "current_faiss_ids_count_expected": EXPECTED_FAISS_IDS_COUNT,
        "expected_faiss_ids_count_after_if_approved": EXPECTED_FAISS_IDS_COUNT_AFTER,
        "faiss_index_mutation_authorized_now": False,
        "faiss_ids_mutation_authorized_now": False,
        "embeddings_creation_authorized_now": False,
        "requires_user_approval_before_mutation": True,
        "candidates": candidates,
        "all_valid": all(c["valid"] for c in candidates),
    }


def build_human_approval_package() -> dict:
    """Build the human approval package for FAISS promotion."""
    plan = build_faiss_promotion_plan()
    
    return {
        "batch_id": get_batch_id(),
        "domain": "security_governance_sandboxing",
        "memory_ids": EXPECTED_MEMORY_IDS,
        "source_ids": EXPECTED_SOURCE_IDS,
        "candidate_count": len(EXPECTED_MEMORY_IDS),
        "expected_faiss_ids_before": EXPECTED_FAISS_IDS_COUNT,
        "expected_faiss_ids_after_if_approved": EXPECTED_FAISS_IDS_COUNT_AFTER,
        "memory_line_count_expected": EXPECTED_MEMORY_LINE_COUNT,
        "backup_required": True,
        "rollback_required": True,
        "faiss_index_mutation_authorized_now": False,
        "faiss_ids_mutation_authorized_now": False,
        "embeddings_creation_authorized_now": False,
        "requires_user_approval_before_mutation": True,
        "approval_phrase_required": f"APPROVE_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_{BATCH_ID}",
        "denial_phrase": f"DENY_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_{BATCH_ID}",
        "promotion_plan_summary": {
            "records_to_promote": plan["records_count"],
            "all_candidates_valid": plan["all_valid"],
        },
    }


def assert_no_faiss_mutation(before: dict, after: dict) -> dict:
    """Compare before/after inventory dicts. Returns pass/fail details."""
    checks = {
        "semantic_memory_jsonl_sha": before.get("semantic_memory_jsonl_sha") == after.get("semantic_memory_jsonl_sha"),
        "semantic_memory_jsonl_lines": before.get("semantic_memory_jsonl_lines") == after.get("semantic_memory_jsonl_lines"),
        "faiss_index_sha": before.get("semantic_memory_faiss_index_sha") == after.get("semantic_memory_faiss_index_sha"),
        "faiss_ids_sha": before.get("semantic_memory_faiss_ids_json_sha") == after.get("semantic_memory_faiss_ids_json_sha"),
        "faiss_ids_count": before.get("semantic_memory_faiss_ids_count") == after.get("semantic_memory_faiss_ids_count"),
    }
    all_pass = all(checks.values())
    return {
        "pass": all_pass,
        "checks": checks,
        "message": "No FAISS mutation detected." if all_pass else "FAISS MUTATION DETECTED — STOP.",
    }
