"""
brain/ingestion_operator_review.py
FRONT-INGESTION-OPERATOR-REVIEW-01

Operator review queue planner for dry-run ingestion candidates.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module consumes dry-run results and structures the operator review
decision queue. It does NOT execute ingestion, does NOT read content,
does NOT write to storage, and does NOT trigger real actions.

Approval here only means "approved for future dry-run step", NOT real ingestion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_dry_run as _dry_run


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

def build_review_id(source_id: str) -> str:
    return f"review:{source_id}"


def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


# ─── Review item builder ─────────────────────────────────────────────────

def build_review_item(candidate: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(candidate.get("source_id", ""))
    dry_run_status = str(candidate.get("dry_run_status", ""))
    risk_level = str(candidate.get("risk_level", ""))
    allowed_mode = str(candidate.get("allowed_mode", ""))

    # Map dry_run_status to review_status, allowed_decisions, and default_decision
    review_status = "registry_only"
    default_decision = "no_action"
    allowed_decisions: List[str] = []

    if dry_run_status == "operator_review_required":
        review_status = "pending_operator_review"
        default_decision = "request_more_context"
        allowed_decisions = [
            "approve_for_future_dry_run",
            "reject",
            "request_more_context",
        ]
    elif dry_run_status == "candidate":
        review_status = "pending_operator_review"
        default_decision = "request_more_context"
        allowed_decisions = [
            "approve_for_future_dry_run",
            "reject",
            "request_more_context",
        ]
    elif dry_run_status == "blocked":
        review_status = "blocked"
        default_decision = "keep_blocked"
        allowed_decisions = ["keep_blocked"]
    elif dry_run_status == "registry_only":
        review_status = "registry_only"
        default_decision = "no_action"
        allowed_decisions = ["no_action"]
    elif dry_run_status == "invalid":
        review_status = "not_reviewable"
        default_decision = "reject"
        allowed_decisions = ["reject", "request_more_context"]

    # Override for blocked risk level
    if risk_level == "blocked":
        review_status = "blocked"
        default_decision = "keep_blocked"
        allowed_decisions = ["keep_blocked"]

    return {
        "review_id": build_review_id(source_id),
        "source_id": source_id,
        "source_type": str(candidate.get("source_type", "")),
        "uri": str(candidate.get("uri", "")),
        "risk_level": risk_level,
        "allowed_mode": allowed_mode,
        "content_policy": str(candidate.get("content_policy", "")),
        "dry_run_status": dry_run_status,
        "residual_risk": str(candidate.get("residual_risk", "unknown")),
        "requires_operator_approval": bool(candidate.get("requires_operator_approval", False)),
        "planned_actions": list(candidate.get("planned_actions", [])),
        "blocked_reasons": list(candidate.get("blocked_reasons", [])),
        "review_status": review_status,
        "allowed_decisions": allowed_decisions,
        "default_decision": default_decision,
        "safety_flags": _deep_copy_safety_flags(),
        "approval_authorizes_real_ingestion": False,
        "can_write_semantic_memory": False,
        "can_promote_faiss": False,
    }


# ─── Main review queue builder ─────────────────────────────────────────────

def build_review_queue(dry_run_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if dry_run_result is None:
        dry_run_result = _dry_run.run_registry_dry_run()

    items: List[Dict[str, Any]] = []
    pending_operator_review: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    registry_only: List[Dict[str, Any]] = []
    not_reviewable: List[Dict[str, Any]] = []

    total_records = 0

    # Process all categories from dry-run result
    all_candidates = (
        dry_run_result.get("candidates", [])
        + dry_run_result.get("blocked", [])
        + dry_run_result.get("invalid", [])
        + dry_run_result.get("operator_review_required", [])
        + dry_run_result.get("registry_only", [])
    )

    for candidate in all_candidates:
        total_records += 1
        review_item = build_review_item(candidate)
        items.append(review_item)

        status = review_item["review_status"]
        if status == "pending_operator_review":
            pending_operator_review.append(review_item)
        elif status == "blocked":
            blocked.append(review_item)
        elif status == "registry_only":
            registry_only.append(review_item)
        else:
            not_reviewable.append(review_item)

    return {
        "total_records": total_records,
        "items": items,
        "pending_operator_review": pending_operator_review,
        "blocked": blocked,
        "registry_only": registry_only,
        "not_reviewable": not_reviewable,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_review_queue(queue: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = queue.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check that no item claims real ingestion authorization
    for item in queue.get("items", []):
        if item.get("approval_authorizes_real_ingestion") is True:
            errors.append(
                f"Item {item.get('source_id')} claims approval_authorizes_real_ingestion=True"
            )
        if item.get("can_write_semantic_memory") is True:
            errors.append(
                f"Item {item.get('source_id')} claims can_write_semantic_memory=True"
            )
        if item.get("can_promote_faiss") is True:
            errors.append(
                f"Item {item.get('source_id')} claims can_promote_faiss=True"
            )

    # Basic structure validation
    required_keys = ("total_records", "items", "pending_operator_review", "blocked", "registry_only", "not_reviewable")
    for key in required_keys:
        if key not in queue:
            errors.append(f"Missing required key: {key}")

    # Count consistency
    total = queue.get("total_records", 0)
    counts = (
        len(queue.get("pending_operator_review", []))
        + len(queue.get("blocked", []))
        + len(queue.get("registry_only", []))
        + len(queue.get("not_reviewable", []))
    )
    if total != counts:
        errors.append(f"Count mismatch: total={total}, sum={counts}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "queue": queue,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_review_queue(queue: Dict[str, Any]) -> Dict[str, Any]:
    pending = queue.get("pending_operator_review", [])
    blocked = queue.get("blocked", [])
    registry_only = queue.get("registry_only", [])
    not_reviewable = queue.get("not_reviewable", [])

    return {
        "total_records": queue.get("total_records", 0),
        "pending_operator_review_count": len(pending),
        "blocked_count": len(blocked),
        "registry_only_count": len(registry_only),
        "not_reviewable_count": len(not_reviewable),
        "safety_flags": queue.get("safety_flags", {}),
    }
