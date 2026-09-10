"""Pure simulated paper-execution lifecycle receipts for BRAIN-101 R15.1."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class PaperExecutionLifecycleReceipt:
    order_id: str
    accepted: bool
    reason: str
    phase: str
    cancellation_recorded: bool
    duplicate_prevented: bool
    reconciliation_status: str
    paper_only: bool
    receipt_id: str


def _receipt_id(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def evaluate_paper_execution_lifecycle(
    *,
    order_id: str,
    event_sequence: tuple[str, ...],
    paper_only: bool,
    market_data_source: str,
    broker_action: bool,
    provider_call: bool,
    network_call: bool,
    runtime_execution: bool,
    scheduler_activation: bool,
    live_trading: bool,
    real_money: bool,
) -> PaperExecutionLifecycleReceipt:
    """Evaluate an in-memory lifecycle only; this function cannot execute an order."""
    validations = (
        (not paper_only, "paper_only_required"),
        (market_data_source != "local_fixture", "local_market_data_required"),
        (broker_action, "broker_action_forbidden"),
        (provider_call, "provider_action_forbidden"),
        (network_call, "network_action_forbidden"),
        (runtime_execution, "runtime_execution_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
        (len(set(event_sequence)) != len(event_sequence), "duplicate_event_detected"),
        (event_sequence != ("SUBMITTED", "CANCELLED", "RECONCILED"), "cancellation_required"),
    )
    reason = next((reason for invalid, reason in validations if invalid), "")
    accepted = not reason
    identity = {
        "order_id": order_id,
        "event_sequence": event_sequence,
        "accepted": accepted,
        "reason": reason,
    }
    payload = {
        "order_id": order_id,
        "accepted": accepted,
        "reason": reason,
        "phase": "RECONCILED" if accepted else "REJECTED",
        "cancellation_recorded": accepted,
        "duplicate_prevented": accepted,
        "reconciliation_status": "MATCHED" if accepted else "NOT_APPLIED",
        "paper_only": paper_only,
    }
    return PaperExecutionLifecycleReceipt(**payload, receipt_id=_receipt_id(identity))


def reject_paper_execution_effect(operation: str) -> None:
    """Reject every execution request outside deterministic simulated-paper evaluation."""
    del operation
    raise ValueError("paper_execution_lifecycle_no_effects")
