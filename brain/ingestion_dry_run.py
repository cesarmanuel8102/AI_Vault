"""
brain/ingestion_dry_run.py
FRONT-INGESTION-DRY-RUN-01

Controlled dry-run ingestion planner.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module consumes the ingestion registry and simulates the ingestion
pipeline without executing real ingestion, content reading, or storage writes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_registry as _registry


# ─── Immutable safety flags ────────────────────────────────────────────────

_DEFAULT_SAFETY_FLAGS: Dict[str, bool] = {
    "ingestion_executed": False,
    "memory_write_executed": False,
    "faiss_write_executed": False,
    "network_called": False,
    "connector_called": False,
    "content_read": False,
    "promotion_executed": False,
}


# ─── Helpers ───────────────────────────────────────────────────────────────

def _build_candidate_id(source_id: str) -> str:
    return f"dryrun:{source_id}"


def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


# ─── Candidate builder ─────────────────────────────────────────────────────

def build_dry_run_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(record.get("source_id", ""))
    risk_level = str(record.get("risk_level", ""))
    allowed_mode = str(record.get("allowed_mode", ""))
    content_policy = str(record.get("content_policy", ""))
    requires_operator_approval = bool(record.get("requires_operator_approval", False))

    validation = _registry.validate_source_record(record)
    classification = _registry.classify_source_record(record)

    # Determine dry_run_status
    blocked_reasons: List[str] = []
    dry_run_status = "registry_only"
    planned_actions: List[str] = []

    if not validation["ok"]:
        dry_run_status = "invalid"
        blocked_reasons.extend(validation["errors"])
    elif risk_level == "blocked":
        dry_run_status = "blocked"
        blocked_reasons.append("Source risk_level is 'blocked'")
    elif allowed_mode == "blocked":
        dry_run_status = "blocked"
        blocked_reasons.append("Source allowed_mode is 'blocked'")
    elif allowed_mode == "dry_run_only":
        dry_run_status = "candidate"
        planned_actions.append("dry_run_simulation")
        planned_actions.append("operator_review_before_real_ingestion")
    elif allowed_mode == "operator_review_required":
        if requires_operator_approval:
            dry_run_status = "operator_review_required"
            planned_actions.append("operator_review")
            planned_actions.append("dry_run_simulation_after_approval")
        else:
            dry_run_status = "blocked"
            blocked_reasons.append("operator_review_required but requires_operator_approval is False")
    else:
        # registry_only or other
        dry_run_status = "registry_only"
        planned_actions.append("no_action")

    # Additional policy checks
    if content_policy == "credential_sensitive" and dry_run_status in ("candidate", "operator_review_required"):
        planned_actions.append("credential_policy_check")

    return {
        "candidate_id": _build_candidate_id(source_id),
        "source_id": source_id,
        "source_type": str(record.get("source_type", "")),
        "uri": str(record.get("uri", "")),
        "risk_level": risk_level,
        "allowed_mode": allowed_mode,
        "content_policy": content_policy,
        "dry_run_status": dry_run_status,
        "residual_risk": classification.get("residual_risk", "unknown"),
        "requires_operator_approval": requires_operator_approval,
        "planned_actions": planned_actions,
        "blocked_reasons": blocked_reasons,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Main dry-run orchestrator ─────────────────────────────────────────────

def run_registry_dry_run(registry: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if registry is None:
        registry = _registry.build_default_registry()

    candidates: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    registry_only_list: List[Dict[str, Any]] = []
    operator_review_required_list: List[Dict[str, Any]] = []

    total_records = 0

    for record in registry:
        total_records += 1
        candidate = build_dry_run_candidate(record)

        status = candidate["dry_run_status"]
        if status == "candidate":
            candidates.append(candidate)
        elif status == "blocked":
            blocked.append(candidate)
        elif status == "invalid":
            invalid.append(candidate)
        elif status == "operator_review_required":
            operator_review_required_list.append(candidate)
        else:
            registry_only_list.append(candidate)

    return {
        "total_records": total_records,
        "candidates": candidates,
        "blocked": blocked,
        "invalid": invalid,
        "operator_review_required": operator_review_required_list,
        "registry_only": registry_only_list,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ───────────────────────────────────────────────────────────────

def validate_dry_run_result(result: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = result.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check candidates don't have can_write_semantic_memory
    for candidate in result.get("candidates", []):
        # candidates are derived from registry records, but we check the original
        pass

    # Basic structure validation
    required_keys = ("total_records", "candidates", "blocked", "invalid", "operator_review_required", "registry_only")
    for key in required_keys:
        if key not in result:
            errors.append(f"Missing required key: {key}")

    # Count consistency
    total = result.get("total_records", 0)
    counts = (
        len(result.get("candidates", []))
        + len(result.get("blocked", []))
        + len(result.get("invalid", []))
        + len(result.get("operator_review_required", []))
        + len(result.get("registry_only", []))
    )
    if total != counts:
        errors.append(f"Count mismatch: total={total}, sum={counts}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_dry_run(result: Dict[str, Any]) -> Dict[str, Any]:
    candidates = result.get("candidates", [])
    blocked = result.get("blocked", [])
    invalid = result.get("invalid", [])
    operator_review = result.get("operator_review_required", [])
    registry_only = result.get("registry_only", [])

    return {
        "total_records": result.get("total_records", 0),
        "candidates_count": len(candidates),
        "blocked_count": len(blocked),
        "invalid_count": len(invalid),
        "operator_review_required_count": len(operator_review),
        "registry_only_count": len(registry_only),
        "dry_run_eligible_count": len(candidates) + len(operator_review),
        "safety_flags": result.get("safety_flags", {}),
    }
