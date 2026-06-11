"""
External Curated Learning -- Canary Ingestion Prep (Security / Governance / Sandboxing)
FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01

This module is a PREP DRY-RUN ONLY.
It does NOT ingest into semantic memory or FAISS.
It does NOT create embeddings.
It does NOT modify protected runtime files.

Purpose: Prepare the first canary ingestion package for
security_governance_sandboxing domain, pending future user approval.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain.external_curated_learning_security_governance_sandboxing import (
    seed_candidate_sources,
    front_id as domain_front_id,
)
from brain.external_curated_learning_controlled_ingestion_authorization import (
    authorized_first_canary_scope,
    authorized_batch_limits,
)


FRONT_ID = "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01"
BATCH_ID = "SEC_GOV_CANARY_001"


def front_id() -> str:
    return FRONT_ID


def get_canary_batch_id() -> str:
    return BATCH_ID


def select_security_governance_canary_sources() -> list[dict]:
    """Select 3–5 accepted sources for the first canary ingestion."""
    all_sources = seed_candidate_sources()
    accepted = [
        s for s in all_sources
        if s.get("acceptance_status") == "accept"
    ]
    # Sort by safety score descending
    accepted_sorted = sorted(
        accepted,
        key=lambda s: s.get("safety_score_estimate", 0),
        reverse=True,
    )
    # Take top 5
    selected = accepted_sorted[:5]
    return [
        {
            "source_id": s["source_id"],
            "source_group": s["source_group"],
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "authors_or_org": s.get("authors_or_org", ""),
            "license": s.get("license", ""),
            "acceptance_status": s["acceptance_status"],
            "safety_score_estimate": s.get("safety_score_estimate", 0),
            "taxonomy_tags": s.get("taxonomy_tags", []),
            "specific_brain_capability_target": s.get("specific_brain_capability_target", ""),
            "cross_check_targets": s.get("cross_check_targets", []),
            "notes": s.get("notes", ""),
        }
        for s in selected
    ]


def build_proposed_memory_records() -> list[dict]:
    """Build proposed memory records conforming to controlled_ingestion_memory_record_v1.
    Does NOT write to memory/FAISS."""
    selected = select_security_governance_canary_sources()
    records = []
    now_utc = datetime.now(timezone.utc).isoformat()

    for idx, src in enumerate(selected, 1):
        memory_id = f"{BATCH_ID}_{src['source_id']}_{idx:03d}"
        record = {
            "memory_id": memory_id,
            "schema_version": "controlled_ingestion_memory_record_v1",
            "source_id": src["source_id"],
            "source_title": src["title"],
            "source_group": src["source_group"],
            "source_url": src["url"],
            "source_license_or_status": src["license"],
            "domain": "security_governance_sandboxing",
            "taxonomy_tags": src["taxonomy_tags"],
            "capability_target": src["specific_brain_capability_target"],
            "source_provenance": {
                "authors_or_org": src["authors_or_org"],
                "cross_check_targets": src["cross_check_targets"],
                "notes": src["notes"],
            },
            "safety_score_estimate": src["safety_score_estimate"],
            "acceptance_status": "accept",
            "ingestion_status": "proposed_only",
            "ingestion_batch_id": BATCH_ID,
            "created_at_utc": now_utc,
            "content_summary": _build_content_summary(src),
            "retrieval_phrases": _build_retrieval_phrases(src),
            "evidence_type": "metadata_summary_only",
            "risk_flags": [],
            "exclusion_notes": "",
            "faiss_eligible": False,
            "faiss_embedding_text": "",
        }
        records.append(record)
    return records


def _build_content_summary(src: dict) -> str:
    """Construct a concise content summary (<= 1200 chars) from source metadata."""
    title = src.get("title", "")
    group = src.get("source_group", "")
    tags = ", ".join(src.get("taxonomy_tags", []))
    target = src.get("specific_brain_capability_target", "")
    notes = src.get("notes", "")
    summary = (
        f"[{group}] {title}. "
        f"Relevant taxonomy: {tags}. "
        f"Brain capability target: {target}. "
        f"Notes: {notes}"
    )
    return summary[:1200]


def _build_retrieval_phrases(src: dict) -> list[str]:
    """Build 3–8 retrieval phrases for the proposed memory record."""
    title = src.get("title", "")
    tags = src.get("taxonomy_tags", [])
    target = src.get("specific_brain_capability_target", "")
    phrases = [
        f"{src['source_id']} security governance",
        f"{target} governance controls",
    ]
    for tag in tags[:3]:
        phrases.append(f"{tag.replace('_', ' ')} governance")
    phrases.append(f"security governance sandboxing {src['source_group']}")
    phrases.append(f"{src['source_id']} source reference")
    # Ensure 3–8
    while len(phrases) < 3:
        phrases.append(f"security governance {src['source_id']}")
    return phrases[:8]


def validate_proposed_memory_record(record: dict) -> list[str]:
    """Validate a single proposed memory record. Returns list of error strings (empty if valid)."""
    errors = []
    required = [
        "memory_id", "schema_version", "source_id", "source_title",
        "source_group", "source_url", "source_license_or_status",
        "domain", "taxonomy_tags", "capability_target",
        "source_provenance", "safety_score_estimate", "acceptance_status",
        "ingestion_status", "ingestion_batch_id", "created_at_utc",
        "content_summary", "retrieval_phrases", "evidence_type",
        "risk_flags", "exclusion_notes", "faiss_eligible", "faiss_embedding_text",
    ]
    for field in required:
        if field not in record:
            errors.append(f"missing_required_field:{field}")

    if record.get("schema_version") != "controlled_ingestion_memory_record_v1":
        errors.append("invalid_schema_version")

    if record.get("domain") != "security_governance_sandboxing":
        errors.append("invalid_domain")

    if record.get("acceptance_status") != "accept":
        errors.append("acceptance_status_not_accept")

    if record.get("ingestion_status") != "proposed_only":
        errors.append("ingestion_status_not_proposed_only")

    summary = record.get("content_summary", "")
    if len(summary) > 1200:
        errors.append("content_summary_too_long")

    phrases = record.get("retrieval_phrases", [])
    if not (3 <= len(phrases) <= 8):
        errors.append("retrieval_phrases_count_out_of_range")

    if record.get("faiss_eligible") is not False:
        errors.append("faiss_eligible_must_be_false")

    if record.get("faiss_embedding_text") != "":
        errors.append("faiss_embedding_text_must_be_empty")

    forbidden = ["chain_of_thought", "executable_code", "trading_signal", "broker_api"]
    for f in forbidden:
        if f in record:
            errors.append(f"forbidden_field_present:{f}")

    return errors


def validate_canary_prep_package() -> dict:
    """Validate the entire canary prep package."""
    records = build_proposed_memory_records()
    selected = select_security_governance_canary_sources()
    batch = authorized_batch_limits().get("canary_batch", {})

    all_errors = []
    for rec in records:
        errs = validate_proposed_memory_record(rec)
        all_errors.extend(errs)

    valid = (
        len(records) >= batch.get("min_records", 3)
        and len(records) <= batch.get("max_records", 5)
        and len(selected) == len(records)
        and all(s["acceptance_status"] == "accept" for s in selected)
        and len(all_errors) == 0
    )

    return {
        "package_valid": valid,
        "record_count": len(records),
        "selected_count": len(selected),
        "validation_errors": all_errors,
        "batch_limits": batch,
        "memory_mutation_authorized": False,
        "faiss_mutation_authorized": False,
    }


def build_human_approval_package() -> dict:
    """Build the human approval package for the canary ingestion."""
    records = build_proposed_memory_records()
    selected = select_security_governance_canary_sources()
    batch = authorized_batch_limits().get("canary_batch", {})
    first_canary = authorized_first_canary_scope()

    record_count = len(records)
    expected_memory_after = 1710 + record_count  # baseline + new records
    expected_faiss_after = 1611  # no FAISS promotion in canary

    return {
        "domain": "security_governance_sandboxing",
        "batch_id": BATCH_ID,
        "source_ids": [s["source_id"] for s in selected],
        "record_count": record_count,
        "faiss_eligible_count": 0,
        "backup_required": True,
        "backup_path_planned": (
            f"tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/"
            f"backups/{BATCH_ID}/"
        ),
        "rollback_path_planned": (
            f"tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/"
            f"backups/{BATCH_ID}/rollback_manifest.json"
        ),
        "expected_memory_line_count_before": 1710,
        "expected_memory_line_count_after_if_approved": expected_memory_after,
        "expected_faiss_ids_count_before": 1611,
        "expected_faiss_ids_count_after_if_approved": expected_faiss_after,
        "memory_mutation_authorized_now": False,
        "faiss_mutation_authorized_now": False,
        "requires_user_approval_before_mutation": True,
        "approval_phrase_required": f"APPROVE_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_{BATCH_ID}",
        "denial_phrase": f"DENY_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_{BATCH_ID}",
        "first_canary_scope": first_canary,
        "batch_limits": batch,
        "proposed_records_preview": [
            {
                "memory_id": r["memory_id"],
                "source_id": r["source_id"],
                "source_title": r["source_title"],
                "domain": r["domain"],
                "ingestion_status": r["ingestion_status"],
                "faiss_eligible": r["faiss_eligible"],
            }
            for r in records
        ],
    }


def assert_no_memory_or_faiss_mutation(before: dict, after: dict) -> dict:
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
        "message": "No mutation detected." if all_pass else "MUTATION DETECTED — STOP.",
    }
