"""Pure paper-only portfolio compliance and risk receipts for BRAIN-101 R15.2."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class PaperPortfolioComplianceRiskReceipt:
    portfolio_id: str
    accepted: bool
    reason: str
    compliance_status: str
    risk_status: str
    audit_recorded: bool
    rollback_validated: bool
    paper_only: bool
    receipt_id: str


def _receipt_id(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def evaluate_paper_portfolio_compliance_risk(
    *,
    portfolio_id: str,
    proposed_weight_bps: int,
    risk_limit_bps: int,
    compliance_approved: bool,
    audit_event_id: str,
    rollback_reference: str,
    paper_only: bool,
    broker_action: bool,
    provider_call: bool,
    network_call: bool,
    runtime_execution: bool,
    scheduler_activation: bool,
    live_trading: bool,
    real_money: bool,
) -> PaperPortfolioComplianceRiskReceipt:
    """Evaluate in-memory paper controls without broker, provider, or runtime effects."""
    validations = (
        (not paper_only, "paper_only_required"),
        (proposed_weight_bps > risk_limit_bps, "risk_limit_exceeded"),
        (not compliance_approved, "compliance_rejected"),
        (not audit_event_id.strip(), "audit_event_required"),
        (not rollback_reference.strip(), "rollback_reference_required"),
        (broker_action, "broker_action_forbidden"),
        (provider_call, "provider_action_forbidden"),
        (network_call, "network_action_forbidden"),
        (runtime_execution, "runtime_execution_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
    )
    reason = next((reason for invalid, reason in validations if invalid), "")
    accepted = not reason
    identity = {
        "portfolio_id": portfolio_id,
        "proposed_weight_bps": proposed_weight_bps,
        "risk_limit_bps": risk_limit_bps,
        "compliance_approved": compliance_approved,
        "audit_event_id": audit_event_id,
        "rollback_reference": rollback_reference,
        "accepted": accepted,
        "reason": reason,
    }
    return PaperPortfolioComplianceRiskReceipt(
        portfolio_id=portfolio_id,
        accepted=accepted,
        reason=reason,
        compliance_status="APPROVED" if accepted else "REJECTED",
        risk_status="WITHIN_LIMIT" if accepted else "NOT_APPLIED",
        audit_recorded=accepted,
        rollback_validated=accepted,
        paper_only=paper_only,
        receipt_id=_receipt_id(identity),
    )


def reject_paper_portfolio_compliance_risk_effect(operation: str) -> None:
    """Reject every request to make an external effect from this paper-only boundary."""
    del operation
    raise ValueError("paper_portfolio_compliance_risk_no_effects")
