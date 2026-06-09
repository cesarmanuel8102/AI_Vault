"""
brain/ingestion_manual_approval_sample.py
FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01

Manual approval sample demonstrating the full ingestion pipeline end-to-end
with a single synthetic pre-approved source.

Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module creates a synthetic low-risk source, runs it through the entire
pipeline (registry → dry-run → operator review → approval decision → reviewed
execution), and demonstrates that the item reaches reviewed_dry_run_planned
status. No real ingestion is executed. This is a teaching/validation module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import brain.ingestion_approval_decision_dry_run as _approval_decision
import brain.ingestion_dry_run as _dry_run
import brain.ingestion_operator_review as _operator_review
import brain.ingestion_registry as _registry
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


def build_synthetic_approved_registry() -> List[Dict[str, Any]]:
    """
    Build a single-record registry representing a synthetic source that an
    operator has manually approved for future dry-run execution.

    The source is low-risk, public, and explicitly set to dry_run_only mode.
    This mimics the scenario where an operator reviewed a source and decided
    it is safe to proceed to the next controlled dry-run step.
    """
    return [
        _registry.build_source_record(
            source_id="synthetic_approved_document",
            source_type="uploaded_document",
            uri="inline://synthetic_approved_fixture",
            display_name="Synthetic Approved Document",
            description=(
                "Synthetic fixture representing an operator-approved "
                "document for future controlled dry-run execution."
            ),
            risk_level="low",
            allowed_mode="dry_run_only",
            content_policy="public",
            requires_operator_approval=False,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=[
                "Synthetic fixture for FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01.",
                "This source is pre-approved in the sample to demonstrate pipeline flow.",
                "Real ingestion is NOT executed by this module.",
            ],
        ),
    ]


def build_synthetic_denied_registry() -> List[Dict[str, Any]]:
    """
    Build a single-record registry representing a synthetic source that an
    operator has manually denied.

    The source is high-risk and requires operator approval, simulating a
    rejection scenario in the pipeline.
    """
    return [
        _registry.build_source_record(
            source_id="synthetic_denied_document",
            source_type="uploaded_document",
            uri="inline://synthetic_denied_fixture",
            display_name="Synthetic Denied Document",
            description=(
                "Synthetic fixture representing an operator-denied "
                "document to demonstrate rejection flow."
            ),
            risk_level="high",
            allowed_mode="operator_review_required",
            content_policy="user_private",
            requires_operator_approval=True,
            can_auto_ingest=False,
            can_write_semantic_memory=False,
            can_promote_faiss=False,
            notes=[
                "Synthetic fixture for FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01.",
                "This source is pre-denied in the sample to demonstrate rejection handling.",
            ],
        ),
    ]


# ─── Pipeline runner ───────────────────────────────────────────────────────

def run_manual_approval_sample(
    registry: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Run the full ingestion pipeline end-to-end on a synthetic registry.

    Steps:
      1. Registry validation (ingestion_registry)
      2. Dry-run planning (ingestion_dry_run)
      3. Operator review queue (ingestion_operator_review)
      4. Approval decision (ingestion_approval_decision_dry_run)
      5. Reviewed dry-run execution (ingestion_reviewed_dry_run_execution)

    Returns a result dict containing the output of every stage plus a
    synthetic_decision that overrides the default decision to simulate
    manual operator approval.
    """
    if registry is None:
        registry = build_synthetic_approved_registry()

    # Stage 1: Registry
    total_records = len(registry)
    registry_validations = [_registry.validate_source_record(r) for r in registry]
    all_registry_valid = all(v["ok"] for v in registry_validations)

    # Stage 2: Dry-run
    dry_run_result = _dry_run.run_registry_dry_run(registry)

    # Stage 3: Operator review queue
    review_queue = _operator_review.build_review_queue(dry_run_result)

    # Stage 4: Approval decision (default)
    decision_result = _approval_decision.run_approval_decision_dry_run(review_queue)

    # Stage 4b: Apply synthetic manual approval/rejection override
    # For teaching/validation purposes, we simulate operator decisions:
    # - "approved" sources → approve_for_future_dry_run
    # - "denied" sources → reject
    # - everything else → default decision
    synthetic_decisions: List[Dict[str, Any]] = []
    for item in review_queue.get("items", []):
        sid = str(item.get("source_id", ""))
        if "approved" in sid:
            synthetic_decision = _approval_decision.apply_decision_to_item(
                item, requested_decision="approve_for_future_dry_run"
            )
        elif "denied" in sid:
            synthetic_decision = _approval_decision.apply_decision_to_item(
                item, requested_decision="reject"
            )
        else:
            synthetic_decision = _approval_decision.apply_decision_to_item(item)
        synthetic_decisions.append(synthetic_decision)

    # Build a synthetic decision result using the overridden decisions
    synthetic_decision_result: Dict[str, Any] = {
        "total_records": len(synthetic_decisions),
        "decisions": synthetic_decisions,
        "accepted_for_future_dry_run": [
            d for d in synthetic_decisions
            if d["decision_status"] == "accepted_for_future_dry_run"
        ],
        "rejected": [
            d for d in synthetic_decisions if d["decision_status"] == "rejected"
        ],
        "more_context_required": [
            d for d in synthetic_decisions
            if d["decision_status"] == "more_context_required"
        ],
        "kept_blocked": [
            d for d in synthetic_decisions if d["decision_status"] == "kept_blocked"
        ],
        "no_action": [
            d for d in synthetic_decisions if d["decision_status"] == "no_action"
        ],
        "denied_invalid_decision": [
            d for d in synthetic_decisions
            if d["decision_status"] == "denied_invalid_decision"
        ],
        "safety_flags": _deep_copy_safety_flags(),
    }

    # Stage 5: Reviewed dry-run execution on synthetic decisions
    execution_result = _reviewed_execution.run_reviewed_dry_run_execution(
        synthetic_decision_result
    )

    return {
        "total_records": total_records,
        "registry_valid": all_registry_valid,
        "registry_validations": registry_validations,
        "dry_run_result": dry_run_result,
        "review_queue": review_queue,
        "default_decision_result": decision_result,
        "synthetic_decision_result": synthetic_decision_result,
        "execution_result": execution_result,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ─────────────────────────────────────────────────────────────

def validate_manual_approval_sample(result: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = result.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check that no stage claims real ingestion
    exec_result = result.get("execution_result", {})
    for item in exec_result.get("execution_items", []):
        if item.get("allowed_execution_mode") not in ("none", "future_controlled_dry_run_only"):
            errors.append(
                f"Item {item.get('source_id')} has unexpected allowed_execution_mode: {item.get('allowed_execution_mode')}"
            )

    # Check that execution result is present and has expected structure
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

    # Count consistency in execution result
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

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_manual_approval_sample(result: Dict[str, Any]) -> Dict[str, Any]:
    exec_result = result.get("execution_result", {})
    synthetic_decisions = result.get("synthetic_decision_result", {})

    planned = exec_result.get("reviewed_dry_run_planned", [])
    skipped = exec_result.get("reviewed_dry_run_skipped_no_approval", [])
    blocked = exec_result.get("blocked", [])
    no_action = exec_result.get("no_action", [])
    rejected = exec_result.get("rejected", [])
    invalid = exec_result.get("invalid", [])

    accepted = synthetic_decisions.get("accepted_for_future_dry_run", [])

    return {
        "total_records": result.get("total_records", 0),
        "registry_valid": result.get("registry_valid", False),
        "reviewed_dry_run_planned_count": len(planned),
        "reviewed_dry_run_skipped_no_approval_count": len(skipped),
        "blocked_count": len(blocked),
        "no_action_count": len(no_action),
        "rejected_count": len(rejected),
        "invalid_count": len(invalid),
        "synthetic_accepted_count": len(accepted),
        "safety_flags": result.get("safety_flags", {}),
    }
