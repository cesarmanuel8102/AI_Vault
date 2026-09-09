"""Pure, paper-only tax-lot audit receipts for the R13.2 contract."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json


@dataclass(frozen=True)
class PaperTaxLotAuditReceipt:
    tax_lot_id: str
    approved: bool
    manual_review: bool
    reason: str | None
    paper_only: bool
    receipt_sha256: str


def _sha256(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_paper_tax_lot(
    *,
    account_id: str,
    symbol: str,
    opened_at_utc: str,
    quantity: int | float,
    cost_basis: str,
    restricted: bool,
    evidence_complete: bool,
    seen_tax_lot_ids: tuple[str, ...],
) -> PaperTaxLotAuditReceipt:
    """Return a deterministic audit receipt without creating a financial effect."""
    identity = {
        "account_id": account_id,
        "symbol": symbol,
        "opened_at_utc": opened_at_utc,
        "quantity": quantity,
        "cost_basis": cost_basis,
    }
    tax_lot_id = _sha256(identity)
    try:
        valid_cost_basis = Decimal(cost_basis) > 0
    except (InvalidOperation, ValueError):
        valid_cost_basis = False
    if quantity <= 0:
        reason, manual_review = "invalid_quantity", False
    elif not valid_cost_basis:
        reason, manual_review = "invalid_cost_basis", False
    elif tax_lot_id in seen_tax_lot_ids:
        reason, manual_review = "duplicate_tax_lot", True
    elif restricted:
        reason, manual_review = "restricted_symbol_manual_review", True
    elif not evidence_complete:
        reason, manual_review = "incomplete_evidence_manual_review", True
    else:
        reason, manual_review = None, False
    receipt = {
        "tax_lot_id": tax_lot_id,
        "approved": reason is None,
        "manual_review": manual_review,
        "reason": reason,
        "paper_only": True,
    }
    return PaperTaxLotAuditReceipt(**receipt, receipt_sha256=_sha256(receipt))


def reject_paper_compliance_audit_effect(operation: str) -> None:
    """Reject every effectful operation; this module only audits supplied data."""
    raise ValueError("paper_only_compliance_audit_no_effects")
