"""
brain/ingestion_manual_approval_batch_sample.py
FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-02

Multi-source synthetic manual approval/rejection batch sample.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module demonstrates mixed operator decisions across all 6 default registry
sources. It does NOT execute real ingestion, does NOT read content, does NOT
write to storage, and does NOT trigger any real actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_approval_decision_dry_run as _approval_decision
import brain.ingestion_operator_review as _operator_review
import brain.ingestion_reviewed_dry_run_execution as _reviewed_execution


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

def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


def build_manual_batch_id(operator_id: str) -> str:
    return f"batch:manual:{operator_id}"


def find_review_item_by_source_id(
    queue: Dict[str, Any],
    source_id: str,
) -> Optional[Dict[str, Any]]:
    """Find a review item in the queue by its source_id."""
    for item in queue.get("items", []):
        if str(item.get("source_id", "")) == source_id:
            return item
    return None


# ─── Default decision plan ───────────────────────────────────────────────

def build_default_manual_decision_plan() -> List[Dict[str, str]]:
    """
    Build the default manual decision plan for all 6 sources.

    Demonstrates mixed operator decisions:
    - 1 approved (local_file)
    - 1 rejected (uploaded_document)
    - 2 request_more_context (connector, web_reference)
    - 1 kept_blocked (api_reference)
    - 1 no_action (manual_text)
    """
    return [
        {
            "source_id": "local_file_dry_run_only",
            "requested_decision": "approve_for_future_dry_run",
        },
        {
            "source_id": "uploaded_document_operator_review",
            "requested_decision": "reject",
        },
        {
            "source_id": "connector_reference_operator_review",
            "requested_decision": "request_more_context",
        },
        {
            "source_id": "web_reference_operator_review",
            "requested_decision": "request_more_context",
        },
        {
            "source_id": "api_reference_blocked_until_credentials_policy",
            "requested_decision": "keep_blocked",
        },
        {
            "source_id": "manual_text_low_risk",
            "requested_decision": "no_action",
        },
    ]


# ─── Decision plan applicator ────────────────────────────────────────────

def apply_manual_decision_plan(
    decision_plan: List[Dict[str, str]],
    operator_id: str = "sample_operator",
) -> Dict[str, Any]:
    """
    Apply a manual decision plan to the operator review queue.

    Returns a result dict with all decisions, grouped by status,
    compatible with run_reviewed_dry_run_execution().
    """
    queue = _operator_review.build_review_queue()
    batch_id = build_manual_batch_id(operator_id)

    decisions: List[Dict[str, Any]] = []
    accepted_for_future_dry_run: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    more_context_required: List[Dict[str, Any]] = []
    kept_blocked: List[Dict[str, Any]] = []
    no_action: List[Dict[str, Any]] = []
    denied_invalid_decision: List[Dict[str, Any]] = []

    # Track which sources were found
    processed_sources: set = set()

    for entry in decision_plan:
        source_id = str(entry.get("source_id", ""))
        requested_decision = str(entry.get("requested_decision", ""))

        item = find_review_item_by_source_id(queue, source_id)
        if item is None:
            # Source not found — create synthetic error decision
            decision = {
                "decision_id": f"{batch_id}:source_not_found:{source_id}",
                "review_id": "",
                "source_id": source_id,
                "review_status": "not_found",
                "requested_decision": requested_decision,
                "applied_decision": "deny",
                "decision_status": "source_not_found",
                "decision_reason": f"Source '{source_id}' not found in review queue.",
                "allowed_next_step": "none",
                "approval_authorizes_real_ingestion": False,
                "can_write_semantic_memory": False,
                "can_promote_faiss": False,
                "safety_flags": _deep_copy_safety_flags(),
            }
            decisions.append(decision)
            denied_invalid_decision.append(decision)
            processed_sources.add(source_id)
            continue

        # Apply the requested decision
        decision = _approval_decision.apply_decision_to_item(
            item, requested_decision=requested_decision
        )
        decisions.append(decision)
        processed_sources.add(source_id)

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
        else:
            denied_invalid_decision.append(decision)

    # Process any sources in queue not in decision_plan using their default
    # decisions (this ensures all 6 sources are accounted for)
    for item in queue.get("items", []):
        sid = str(item.get("source_id", ""))
        if sid not in processed_sources:
            default_decision = _approval_decision.apply_decision_to_item(item)
            decisions.append(default_decision)
            status = default_decision["decision_status"]
            if status == "accepted_for_future_dry_run":
                accepted_for_future_dry_run.append(default_decision)
            elif status == "rejected":
                rejected.append(default_decision)
            elif status == "more_context_required":
                more_context_required.append(default_decision)
            elif status == "kept_blocked":
                kept_blocked.append(default_decision)
            elif status == "no_action":
                no_action.append(default_decision)
            else:
                denied_invalid_decision.append(default_decision)

    return {
        "batch_id": batch_id,
        "operator_id": operator_id,
        "total_records": len(decisions),
        "decisions": decisions,
        "accepted_for_future_dry_run": accepted_for_future_dry_run,
        "rejected": rejected,
        "more_context_required": more_context_required,
        "kept_blocked": kept_blocked,
        "no_action": no_action,
        "denied_invalid_decision": denied_invalid_decision,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Main batch orchestrator ───────────────────────────────────────────────

def run_manual_approval_batch_sample(
    operator_id: str = "sample_operator",
) -> Dict[str, Any]:
    """
    Run the full multi-source manual approval batch sample.

    Steps:
      1. Build review queue (ingestion_operator_review)
      2. Apply default decision plan (mixed approvals/rejections)
      3. Run reviewed dry-run execution (ingestion_reviewed_dry_run_execution)

    Returns a result dict with both the decision result and execution result.
    """
    decision_plan = build_default_manual_decision_plan()
    decision_result = apply_manual_decision_plan(decision_plan, operator_id)

    # Run reviewed dry-run execution on the synthetic decisions
    execution_result = _reviewed_execution.run_reviewed_dry_run_execution(
        decision_result
    )

    return {
        "batch_id": decision_result["batch_id"],
        "operator_id": operator_id,
        "total_records": decision_result["total_records"],
        "decision_result": decision_result,
        "execution_result": execution_result,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_manual_approval_batch_sample(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = result.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check execution result structure
    exec_result = result.get("execution_result", {})
    required_exec_keys = (
        "total_records",
        "execution_items",
        "reviewed_dry_run_planned",
        "reviewed_dry_run_skipped_no_approval",
        "blocked",
        "no_action",
        "rejected",
        "invalid",
    )
    for key in required_exec_keys:
        if key not in exec_result:
            errors.append(f"Missing execution_result key: {key}")

    # Check that no execution item claims real ingestion
    for item in exec_result.get("execution_items", []):
        if item.get("allowed_execution_mode") not in (
            "none",
            "future_controlled_dry_run_only",
        ):
            errors.append(
                f"Item {item.get('source_id')} has unexpected allowed_execution_mode: {item.get('allowed_execution_mode')}"
            )

    # Count consistency
    total = exec_result.get("total_records", 0)
    counts = (
        len(exec_result.get("reviewed_dry_run_planned", []))
        + len(exec_result.get("reviewed_dry_run_skipped_no_approval", []))
        + len(exec_result.get("blocked", []))
        + len(exec_result.get("no_action", []))
        + len(exec_result.get("rejected", []))
        + len(exec_result.get("invalid", []))
    )
    if total != counts:
        errors.append(f"Execution count mismatch: total={total}, sum={counts}")

    # Decision result count consistency
    dec_result = result.get("decision_result", {})
    dec_total = dec_result.get("total_records", 0)
    dec_counts = (
        len(dec_result.get("accepted_for_future_dry_run", []))
        + len(dec_result.get("rejected", []))
        + len(dec_result.get("more_context_required", []))
        + len(dec_result.get("kept_blocked", []))
        + len(dec_result.get("no_action", []))
        + len(dec_result.get("denied_invalid_decision", []))
    )
    if dec_total != dec_counts:
        errors.append(
            f"Decision count mismatch: total={dec_total}, sum={dec_counts}"
        )

    # Check that total counts match between decision and execution
    if dec_total != total:
        errors.append(
            f"Decision/execution total mismatch: decisions={dec_total}, executions={total}"
        )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_manual_approval_batch_sample(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    exec_result = result.get("execution_result", {})
    dec_result = result.get("decision_result", {})

    planned = exec_result.get("reviewed_dry_run_planned", [])
    skipped = exec_result.get("reviewed_dry_run_skipped_no_approval", [])
    blocked = exec_result.get("blocked", [])
    no_action = exec_result.get("no_action", [])
    rejected = exec_result.get("rejected", [])
    invalid = exec_result.get("invalid", [])

    accepted = dec_result.get("accepted_for_future_dry_run", [])

    return {
        "batch_id": result.get("batch_id", ""),
        "operator_id": result.get("operator_id", ""),
        "total_records": result.get("total_records", 0),
        "approved_count": len(accepted),
        "rejected_count": len(rejected),
        "more_context_required_count": len(
            dec_result.get("more_context_required", [])
        ),
        "kept_blocked_count": len(dec_result.get("kept_blocked", [])),
        "no_action_count": len(no_action),
        "reviewed_dry_run_planned_count": len(planned),
        "reviewed_dry_run_skipped_no_approval_count": len(skipped),
        "blocked_count": len(blocked),
        "invalid_count": len(invalid),
        "safety_flags": result.get("safety_flags", {}),
    }
