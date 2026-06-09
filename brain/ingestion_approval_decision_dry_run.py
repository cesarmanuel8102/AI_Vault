"""
brain/ingestion_approval_decision_dry_run.py
FRONT-INGESTION-APPROVAL-DECISION-DRY-RUN-01

Approval decision dry-run simulator for operator review queue.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module consumes the operator review queue and simulates operator
decisions without executing real ingestion, reading content, or triggering
any external action. Approval here only means "approved for future dry-run
step", NOT real ingestion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_operator_review as _operator_review


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

def build_decision_id(review_id: str) -> str:
    return f"decision:{review_id}"


def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


def default_requested_decision_for_item(item: Dict[str, Any]) -> str:
    return str(item.get("default_decision", "request_more_context"))


# ─── Decision applicator ───────────────────────────────────────────────────

def apply_decision_to_item(
    item: Dict[str, Any],
    requested_decision: Optional[str] = None,
) -> Dict[str, Any]:
    if requested_decision is None:
        requested_decision = default_requested_decision_for_item(item)

    review_status = str(item.get("review_status", ""))
    allowed_decisions = list(item.get("allowed_decisions", []))
    review_id = str(item.get("review_id", ""))
    source_id = str(item.get("source_id", ""))

    # Validate requested decision is in allowed list
    if requested_decision not in allowed_decisions:
        return {
            "decision_id": build_decision_id(review_id),
            "review_id": review_id,
            "source_id": source_id,
            "review_status": review_status,
            "requested_decision": requested_decision,
            "applied_decision": "deny",
            "decision_status": "denied_invalid_decision",
            "decision_reason": (
                f"Decision '{requested_decision}' is not allowed for review_status '{review_status}'. "
                f"Allowed: {allowed_decisions}"
            ),
            "allowed_next_step": "none",
            "approval_authorizes_real_ingestion": False,
            "can_write_semantic_memory": False,
            "can_promote_faiss": False,
            "safety_flags": _deep_copy_safety_flags(),
        }

    # Apply decision based on review_status and requested_decision
    decision_status = "no_action"
    allowed_next_step = "none"
    decision_reason = ""

    if review_status == "pending_operator_review":
        if requested_decision == "approve_for_future_dry_run":
            decision_status = "accepted_for_future_dry_run"
            allowed_next_step = "future_controlled_dry_run_only"
            decision_reason = (
                "Operator approved for future controlled dry-run step. "
                "This does NOT authorize real ingestion."
            )
        elif requested_decision == "reject":
            decision_status = "rejected"
            allowed_next_step = "none"
            decision_reason = "Operator rejected the source."
        elif requested_decision == "request_more_context":
            decision_status = "more_context_required"
            allowed_next_step = "operator_review"
            decision_reason = "Operator requested more context before deciding."
    elif review_status == "blocked":
        if requested_decision == "keep_blocked":
            decision_status = "kept_blocked"
            allowed_next_step = "none"
            decision_reason = "Source remains blocked."
    elif review_status == "registry_only":
        if requested_decision == "no_action":
            decision_status = "no_action"
            allowed_next_step = "none"
            decision_reason = "No action needed for registry-only source."
    elif review_status == "not_reviewable":
        if requested_decision == "reject":
            decision_status = "rejected"
            allowed_next_step = "none"
            decision_reason = "Invalid source rejected."
        elif requested_decision == "request_more_context":
            decision_status = "more_context_required"
            allowed_next_step = "operator_review"
            decision_reason = "More context requested for invalid source."

    return {
        "decision_id": build_decision_id(review_id),
        "review_id": review_id,
        "source_id": source_id,
        "review_status": review_status,
        "requested_decision": requested_decision,
        "applied_decision": requested_decision,
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "allowed_next_step": allowed_next_step,
        "approval_authorizes_real_ingestion": False,
        "can_write_semantic_memory": False,
        "can_promote_faiss": False,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Main dry-run orchestrator ─────────────────────────────────────────────

def run_approval_decision_dry_run(
    queue: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if queue is None:
        queue = _operator_review.build_review_queue()

    decisions: List[Dict[str, Any]] = []
    accepted_for_future_dry_run: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    more_context_required: List[Dict[str, Any]] = []
    kept_blocked: List[Dict[str, Any]] = []
    no_action: List[Dict[str, Any]] = []
    denied_invalid_decision: List[Dict[str, Any]] = []

    # Process all items from the review queue
    all_items = queue.get("items", [])

    for item in all_items:
        decision = apply_decision_to_item(item)
        decisions.append(decision)

        status = decision["decision_status"]
        if status == "accepted_for_future_dry_run":
            accepted_for_future_dry_run.append(decision)
        elif status == "rejected":
            rejected.append(decision)
        elif status == "more_context_required":
            more_context_required.append(decision)
        elif status == "kept_blocked":
            kept_blocked.append(decision)
        elif status == "no_action":
            no_action.append(decision)
        elif status == "denied_invalid_decision":
            denied_invalid_decision.append(decision)

    return {
        "total_records": len(all_items),
        "decisions": decisions,
        "accepted_for_future_dry_run": accepted_for_future_dry_run,
        "rejected": rejected,
        "more_context_required": more_context_required,
        "kept_blocked": kept_blocked,
        "no_action": no_action,
        "denied_invalid_decision": denied_invalid_decision,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_decision_result(result: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = result.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check that no decision claims real ingestion authorization
    for decision in result.get("decisions", []):
        if decision.get("approval_authorizes_real_ingestion") is True:
            errors.append(
                f"Decision {decision.get('decision_id')} claims approval_authorizes_real_ingestion=True"
            )
        if decision.get("can_write_semantic_memory") is True:
            errors.append(
                f"Decision {decision.get('decision_id')} claims can_write_semantic_memory=True"
            )
        if decision.get("can_promote_faiss") is True:
            errors.append(
                f"Decision {decision.get('decision_id')} claims can_promote_faiss=True"
            )

    # Basic structure validation
    required_keys = (
        "total_records",
        "decisions",
        "accepted_for_future_dry_run",
        "rejected",
        "more_context_required",
        "kept_blocked",
        "no_action",
        "denied_invalid_decision",
    )
    for key in required_keys:
        if key not in result:
            errors.append(f"Missing required key: {key}")

    # Count consistency
    total = result.get("total_records", 0)
    counts = (
        len(result.get("accepted_for_future_dry_run", []))
        + len(result.get("rejected", []))
        + len(result.get("more_context_required", []))
        + len(result.get("kept_blocked", []))
        + len(result.get("no_action", []))
        + len(result.get("denied_invalid_decision", []))
    )
    if total != counts:
        errors.append(f"Count mismatch: total={total}, sum={counts}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_decision_result(result: Dict[str, Any]) -> Dict[str, Any]:
    accepted = result.get("accepted_for_future_dry_run", [])
    rejected = result.get("rejected", [])
    more_context = result.get("more_context_required", [])
    kept_blocked = result.get("kept_blocked", [])
    no_action = result.get("no_action", [])
    denied = result.get("denied_invalid_decision", [])

    return {
        "total_records": result.get("total_records", 0),
        "accepted_for_future_dry_run_count": len(accepted),
        "rejected_count": len(rejected),
        "more_context_required_count": len(more_context),
        "kept_blocked_count": len(kept_blocked),
        "no_action_count": len(no_action),
        "denied_invalid_decision_count": len(denied),
        "safety_flags": result.get("safety_flags", {}),
    }
