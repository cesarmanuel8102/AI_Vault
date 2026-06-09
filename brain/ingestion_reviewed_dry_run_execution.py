"""
brain/ingestion_reviewed_dry_run_execution.py
FRONT-INGESTION-REVIEWED-DRY-RUN-EXECUTION-01

Reviewed dry-run execution planner.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module consumes approval decision results and determines which items
are eligible for reviewed dry-run execution. In the default state, zero
items are approved (all are more_context_required or blocked), so the
gate correctly reports zero execution candidates.

This module does NOT execute real ingestion, does NOT read content,
does NOT write to storage, and does NOT trigger any real actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_approval_decision_dry_run as _approval_decision


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

def build_execution_id(decision_id: str) -> str:
    return f"exec:{decision_id}"


def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


# ─── Execution item builder ────────────────────────────────────────────────

def build_execution_item(decision: Dict[str, Any]) -> Dict[str, Any]:
    decision_id = str(decision.get("decision_id", ""))
    source_id = str(decision.get("source_id", ""))
    decision_status = str(decision.get("decision_status", ""))

    # Map decision_status to execution_status and allowed_execution_mode
    execution_status = "invalid"
    allowed_execution_mode = "none"
    execution_reason = ""

    if decision_status == "accepted_for_future_dry_run":
        execution_status = "reviewed_dry_run_planned"
        allowed_execution_mode = "future_controlled_dry_run_only"
        execution_reason = (
            "Reviewed dry-run execution planned. "
            "This is still a planning step; no real ingestion executed."
        )
    elif decision_status == "more_context_required":
        execution_status = "reviewed_dry_run_skipped_no_approval"
        allowed_execution_mode = "none"
        execution_reason = (
            "Reviewed dry-run execution skipped: "
            "item has not been approved (more context required)."
        )
    elif decision_status == "kept_blocked":
        execution_status = "blocked"
        allowed_execution_mode = "none"
        execution_reason = "Item is blocked; no execution allowed."
    elif decision_status == "no_action":
        execution_status = "no_action"
        allowed_execution_mode = "none"
        execution_reason = "No action needed for this item."
    elif decision_status == "rejected":
        execution_status = "rejected"
        allowed_execution_mode = "none"
        execution_reason = "Item was rejected; no execution allowed."
    elif decision_status == "denied_invalid_decision":
        execution_status = "invalid"
        allowed_execution_mode = "none"
        execution_reason = "Invalid decision; no execution allowed."

    return {
        "execution_id": build_execution_id(decision_id),
        "decision_id": decision_id,
        "source_id": source_id,
        "decision_status": decision_status,
        "execution_status": execution_status,
        "execution_reason": execution_reason,
        "allowed_execution_mode": allowed_execution_mode,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Main execution orchestrator ───────────────────────────────────────────

def run_reviewed_dry_run_execution(
    decision_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if decision_result is None:
        decision_result = _approval_decision.run_approval_decision_dry_run()

    execution_items: List[Dict[str, Any]] = []
    reviewed_dry_run_planned: List[Dict[str, Any]] = []
    reviewed_dry_run_skipped_no_approval: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    no_action: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []

    # Process all decisions
    all_decisions = decision_result.get("decisions", [])

    for decision in all_decisions:
        item = build_execution_item(decision)
        execution_items.append(item)

        status = item["execution_status"]
        if status == "reviewed_dry_run_planned":
            reviewed_dry_run_planned.append(item)
        elif status == "reviewed_dry_run_skipped_no_approval":
            reviewed_dry_run_skipped_no_approval.append(item)
        elif status == "blocked":
            blocked.append(item)
        elif status == "no_action":
            no_action.append(item)
        elif status == "rejected":
            rejected.append(item)
        else:
            invalid.append(item)

    return {
        "total_records": len(all_decisions),
        "execution_items": execution_items,
        "reviewed_dry_run_planned": reviewed_dry_run_planned,
        "reviewed_dry_run_skipped_no_approval": reviewed_dry_run_skipped_no_approval,
        "blocked": blocked,
        "no_action": no_action,
        "rejected": rejected,
        "invalid": invalid,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_reviewed_dry_run_execution(result: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = result.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check that no execution item claims real execution
    for item in result.get("execution_items", []):
        if item.get("allowed_execution_mode") not in ("none", "future_controlled_dry_run_only"):
            errors.append(
                f"Item {item.get('source_id')} has unexpected allowed_execution_mode: {item.get('allowed_execution_mode')}"
            )

    # Basic structure validation
    required_keys = (
        "total_records",
        "execution_items",
        "reviewed_dry_run_planned",
        "reviewed_dry_run_skipped_no_approval",
        "blocked",
        "no_action",
        "rejected",
        "invalid",
    )
    for key in required_keys:
        if key not in result:
            errors.append(f"Missing required key: {key}")

    # Count consistency
    total = result.get("total_records", 0)
    counts = (
        len(result.get("reviewed_dry_run_planned", []))
        + len(result.get("reviewed_dry_run_skipped_no_approval", []))
        + len(result.get("blocked", []))
        + len(result.get("no_action", []))
        + len(result.get("rejected", []))
        + len(result.get("invalid", []))
    )
    if total != counts:
        errors.append(f"Count mismatch: total={total}, sum={counts}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_reviewed_dry_run_execution(result: Dict[str, Any]) -> Dict[str, Any]:
    planned = result.get("reviewed_dry_run_planned", [])
    skipped = result.get("reviewed_dry_run_skipped_no_approval", [])
    blocked = result.get("blocked", [])
    no_action = result.get("no_action", [])
    rejected = result.get("rejected", [])
    invalid = result.get("invalid", [])

    return {
        "total_records": result.get("total_records", 0),
        "reviewed_dry_run_planned_count": len(planned),
        "reviewed_dry_run_skipped_no_approval_count": len(skipped),
        "blocked_count": len(blocked),
        "no_action_count": len(no_action),
        "rejected_count": len(rejected),
        "invalid_count": len(invalid),
        "safety_flags": result.get("safety_flags", {}),
    }
