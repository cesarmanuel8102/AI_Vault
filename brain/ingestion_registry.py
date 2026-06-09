"""
brain/ingestion_registry.py
FRONT-INGESTION-REGISTRY-01

Read-only ingestion source registry for Brain Lab.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module ONLY defines, validates, and documents the registry of sources
allowed for controlled ingestion. It does NOT execute ingestion,
dry-runs, or write to any storage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─── Allowed values ────────────────────────────────────────────────────────

_ALLOWED_SOURCE_TYPES: frozenset = frozenset({
    "local_file",
    "local_directory",
    "uploaded_document",
    "manual_text",
    "connector_reference",
    "api_reference",
    "web_reference",
})

_ALLOWED_RISK_LEVELS: frozenset = frozenset({
    "low",
    "medium",
    "high",
    "blocked",
})

_ALLOWED_MODES: frozenset = frozenset({
    "registry_only",
    "dry_run_only",
    "operator_review_required",
    "blocked",
})

_ALLOWED_CONTENT_POLICIES: frozenset = frozenset({
    "public",
    "user_private",
    "credential_sensitive",
    "unknown",
})


# ─── Normalizers ───────────────────────────────────────────────────────────

def normalize_source_id(value: str) -> str:
    s = str(value).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    return s


def normalize_source_type(value: str) -> str:
    s = str(value).strip().lower()
    if s in _ALLOWED_SOURCE_TYPES:
        return s
    return "unknown"


def normalize_risk_level(value: str) -> str:
    s = str(value).strip().lower()
    if s in _ALLOWED_RISK_LEVELS:
        return s
    return "blocked"


def normalize_allowed_mode(value: str) -> str:
    s = str(value).strip().lower()
    if s in _ALLOWED_MODES:
        return s
    return "blocked"


def normalize_content_policy(value: str) -> str:
    s = str(value).strip().lower()
    if s in _ALLOWED_CONTENT_POLICIES:
        return s
    return "unknown"


# ─── Record builder ────────────────────────────────────────────────────────

def build_source_record(
    source_id: str,
    source_type: str,
    uri: str,
    *,
    display_name: str = "",
    description: str = "",
    risk_level: str = "medium",
    allowed_mode: str = "registry_only",
    content_policy: str = "unknown",
    requires_operator_approval: bool = False,
    can_auto_ingest: bool = False,
    can_write_semantic_memory: bool = False,
    can_promote_faiss: bool = False,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "source_id": normalize_source_id(source_id),
        "source_type": normalize_source_type(source_type),
        "uri": str(uri).strip(),
        "display_name": str(display_name).strip(),
        "description": str(description).strip(),
        "risk_level": normalize_risk_level(risk_level),
        "allowed_mode": normalize_allowed_mode(allowed_mode),
        "content_policy": normalize_content_policy(content_policy),
        "requires_operator_approval": bool(requires_operator_approval),
        "can_auto_ingest": bool(can_auto_ingest),
        "can_write_semantic_memory": bool(can_write_semantic_memory),
        "can_promote_faiss": bool(can_promote_faiss),
        "notes": list(notes or []),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_source_record(record: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    source_id = record.get("source_id")
    if not source_id or not str(source_id).strip():
        errors.append("Missing required field: source_id")

    source_type = str(record.get("source_type", "")).strip().lower()
    if not source_type:
        errors.append("Missing required field: source_type")
    elif source_type not in _ALLOWED_SOURCE_TYPES:
        errors.append(f"Invalid source_type: {source_type}")

    uri = record.get("uri")
    if not uri or not str(uri).strip():
        errors.append("Missing required field: uri")

    risk_level = str(record.get("risk_level", "")).strip().lower()
    if risk_level not in _ALLOWED_RISK_LEVELS:
        errors.append(f"Invalid risk_level: {risk_level}")

    allowed_mode = str(record.get("allowed_mode", "")).strip().lower()
    if allowed_mode not in _ALLOWED_MODES:
        errors.append(f"Invalid allowed_mode: {allowed_mode}")

    content_policy = str(record.get("content_policy", "")).strip().lower()
    if content_policy not in _ALLOWED_CONTENT_POLICIES:
        errors.append(f"Invalid content_policy: {content_policy}")

    # Business rule: can_write_semantic_memory must be false in this front
    if record.get("can_write_semantic_memory") is True:
        errors.append("can_write_semantic_memory must be False (front constraint)")

    # Business rule: can_promote_faiss must be false in this front
    if record.get("can_promote_faiss") is True:
        errors.append("can_promote_faiss must be False (front constraint)")

    # Business rule: high risk cannot auto_ingest
    if risk_level == "high" and record.get("can_auto_ingest") is True:
        errors.append("High risk source cannot have can_auto_ingest=True")

    # Business rule: blocked cannot dry_run
    if risk_level == "blocked" and allowed_mode in ("dry_run_only",):
        errors.append("Blocked source cannot have allowed_mode=dry_run_only")

    # Business rule: credential_sensitive cannot auto_ingest
    if content_policy == "credential_sensitive" and record.get("can_auto_ingest") is True:
        errors.append("Credential-sensitive source cannot have can_auto_ingest=True")

    # Business rule: unknown requires operator review
    if content_policy == "unknown" and not record.get("requires_operator_approval"):
        errors.append("Unknown content_policy must have requires_operator_approval=True")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "record": record,
    }


# ─── Classifier ────────────────────────────────────────────────────────────

def classify_source_record(record: Dict[str, Any]) -> Dict[str, Any]:
    risk_level = str(record.get("risk_level", "medium")).strip().lower()
    allowed_mode = str(record.get("allowed_mode", "registry_only")).strip().lower()
    content_policy = str(record.get("content_policy", "unknown")).strip().lower()
    can_auto_ingest = bool(record.get("can_auto_ingest", False))

    # Residual risk: highest of risk_level + content_policy
    residual_risk = risk_level
    if content_policy in ("credential_sensitive", "unknown") and risk_level in ("low", "medium"):
        residual_risk = "high"
    if risk_level == "blocked" or allowed_mode == "blocked":
        residual_risk = "blocked"

    # Auto-ingest eligibility
    auto_ingest_eligible = (
        can_auto_ingest
        and risk_level == "low"
        and content_policy == "public"
        and allowed_mode in ("registry_only", "dry_run_only")
    )

    # Dry-run eligibility
    dry_run_eligible = (
        allowed_mode in ("registry_only", "dry_run_only", "operator_review_required")
        and risk_level != "blocked"
    )

    return {
        "source_id": record.get("source_id"),
        "risk_level": risk_level,
        "allowed_mode": allowed_mode,
        "content_policy": content_policy,
        "residual_risk": residual_risk,
        "auto_ingest_eligible": auto_ingest_eligible,
        "dry_run_eligible": dry_run_eligible,
        "requires_operator_review": bool(record.get("requires_operator_approval", False)),
    }


# ─── Policy helpers ────────────────────────────────────────────────────────

def is_source_allowed_for_dry_run(record: Dict[str, Any]) -> bool:
    c = classify_source_record(record)
    return c["dry_run_eligible"]


def is_source_allowed_for_auto_ingest(record: Dict[str, Any]) -> bool:
    c = classify_source_record(record)
    return c["auto_ingest_eligible"]


# ─── Default registry ──────────────────────────────────────────────────────

def build_default_registry() -> List[Dict[str, Any]]:
    return [
        build_source_record(
            source_id="manual_text_low_risk",
            source_type="manual_text",
            uri="inline://manual_input",
            display_name="Manual Text Input",
            description="User-provided text content entered manually.",
            risk_level="low",
            allowed_mode="registry_only",
            content_policy="public",
            requires_operator_approval=False,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Safe for manual entry; no secrets expected."],
        ),
        build_source_record(
            source_id="uploaded_document_operator_review",
            source_type="uploaded_document",
            uri="upload://user_documents",
            display_name="Uploaded Document",
            description="Files uploaded by operator for review.",
            risk_level="medium",
            allowed_mode="operator_review_required",
            content_policy="user_private",
            requires_operator_approval=True,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Requires operator review before any processing."],
        ),
        build_source_record(
            source_id="local_file_dry_run_only",
            source_type="local_file",
            uri="file://tmp_agent/data/safe_sample.jsonl",
            display_name="Local Safe Sample File",
            description="Local fixture file for dry-run ingestion testing.",
            risk_level="low",
            allowed_mode="dry_run_only",
            content_policy="public",
            requires_operator_approval=False,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Dry-run only; no real ingestion allowed."],
        ),
        build_source_record(
            source_id="connector_reference_operator_review",
            source_type="connector_reference",
            uri="ref://external_connector/github",
            display_name="External Connector Reference",
            description="Reference to external source connector; requires review.",
            risk_level="medium",
            allowed_mode="operator_review_required",
            content_policy="public",
            requires_operator_approval=True,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Connector may fetch external data; operator must approve."],
        ),
        build_source_record(
            source_id="api_reference_blocked_until_credentials_policy",
            source_type="api_reference",
            uri="ref://api/external_api",
            display_name="External API Reference",
            description="API endpoint reference blocked until credential policy defined.",
            risk_level="blocked",
            allowed_mode="blocked",
            content_policy="credential_sensitive",
            requires_operator_approval=True,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Blocked: credential policy and operator approval required."],
        ),
        build_source_record(
            source_id="web_reference_operator_review",
            source_type="web_reference",
            uri="ref://web/public_docs",
            display_name="Web Page Reference",
            description="Reference to web content; requires operator review.",
            risk_level="medium",
            allowed_mode="operator_review_required",
            content_policy="public",
            requires_operator_approval=True,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=["Web content may change; operator review required."],
        ),
    ]


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_registry(registry: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts_by_risk: Dict[str, int] = {}
    counts_by_mode: Dict[str, int] = {}
    counts_by_type: Dict[str, int] = {}
    total = 0

    for record in registry:
        total += 1
        counts_by_risk[record.get("risk_level", "unknown")] = counts_by_risk.get(record.get("risk_level", "unknown"), 0) + 1
        counts_by_mode[record.get("allowed_mode", "unknown")] = counts_by_mode.get(record.get("allowed_mode", "unknown"), 0) + 1
        counts_by_type[record.get("source_type", "unknown")] = counts_by_type.get(record.get("source_type", "unknown"), 0) + 1

    return {
        "total_records": total,
        "by_risk_level": counts_by_risk,
        "by_allowed_mode": counts_by_mode,
        "by_source_type": counts_by_type,
        "auto_ingest_eligible": sum(1 for r in registry if is_source_allowed_for_auto_ingest(r)),
        "dry_run_eligible": sum(1 for r in registry if is_source_allowed_for_dry_run(r)),
        "requires_operator_review": sum(1 for r in registry if r.get("requires_operator_approval")),
    }
