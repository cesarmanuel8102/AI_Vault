"""Deterministic paper-only audit and rollback receipts for BRAIN-101 R11.2.

The module intentionally models audit evidence only. It never imports or
executes broker, provider, network, or financial-autonomy runtime code.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_RISK_GATE_STATE = "PAPER_ONLY_APPROVED"
_FORBIDDEN_EFFECTS = frozenset(
    {
        "broker_connect",
        "broker_order",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "configuration_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class PaperOnlyFinancialAuditEvent:
    audit_id: str
    broker_gateway_id: str
    risk_gate_state: str
    paper_only: bool
    broker_connection_permitted: bool
    order_action_permitted: bool
    provider_calls_permitted: bool
    network_permitted: bool
    event_sha256: str


@dataclass(frozen=True)
class PaperOnlyAuditRollbackReceipt:
    audit_event_sha256: str
    rollback_validated: bool
    runtime_change_applied: bool
    receipt_sha256: str


@dataclass(frozen=True)
class PaperOnlyFinancialAuditResult:
    audit_event: PaperOnlyFinancialAuditEvent
    rollback_receipt: PaperOnlyAuditRollbackReceipt


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid_{field}")


def evaluate_paper_only_financial_autonomy_audit(
    *,
    audit_id: str,
    broker_gateway_id: str,
    risk_gate_state: str,
) -> PaperOnlyFinancialAuditResult:
    """Return immutable audit and rollback evidence without any runtime effect."""
    _validate_identifier(audit_id, "audit_id")
    _validate_identifier(broker_gateway_id, "broker_gateway_id")
    if risk_gate_state != _RISK_GATE_STATE:
        raise ValueError("invalid_risk_gate_state")

    event_payload = {
        "audit_id": audit_id,
        "broker_connection_permitted": False,
        "broker_gateway_id": broker_gateway_id,
        "network_permitted": False,
        "order_action_permitted": False,
        "paper_only": True,
        "provider_calls_permitted": False,
        "risk_gate_state": risk_gate_state,
    }
    audit_event = PaperOnlyFinancialAuditEvent(
        **event_payload,
        event_sha256=_canonical_sha256(event_payload),
    )
    receipt_payload = {
        "audit_event_sha256": audit_event.event_sha256,
        "rollback_validated": True,
        "runtime_change_applied": False,
    }
    return PaperOnlyFinancialAuditResult(
        audit_event=audit_event,
        rollback_receipt=PaperOnlyAuditRollbackReceipt(
            **receipt_payload,
            receipt_sha256=_canonical_sha256(receipt_payload),
        ),
    )


def reject_financial_autonomy_audit_effect(operation: str) -> None:
    """Fail closed for every operation outside the paper-only audit contract."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("paper_only_audit_no_effects")
    raise ValueError("unsupported_paper_only_audit_operation")
