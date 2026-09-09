"""Deterministic, paper-only compliance policy decisions for R13.1."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


_POLICY = {"max_day_trades_in_window": 3, "paper_live_boundary": "paper_only"}


@dataclass(frozen=True)
class PaperComplianceDecision:
    approved: bool
    paper_only: bool
    denial_reasons: tuple[str, ...]
    policy: dict[str, object]
    receipt_sha256: str


def _receipt(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate_paper_trading_compliance(
    *, day_trades_in_window: int, wash_sale_detected: bool, market_hours_open: bool,
    restricted_symbol: bool, short_sale_permission: bool, account_permission: bool,
    jurisdiction_approved: bool, data_license_approved: bool, paper_only: bool,
) -> PaperComplianceDecision:
    checks = (
        (day_trades_in_window >= _POLICY["max_day_trades_in_window"] + 1, "pdt_threshold_exceeded"),
        (wash_sale_detected, "wash_sale_detected"),
        (not market_hours_open, "market_hours_closed"),
        (restricted_symbol, "restricted_symbol"),
        (not short_sale_permission, "short_sale_permission_missing"),
        (not account_permission, "account_permission_missing"),
        (not jurisdiction_approved, "jurisdiction_not_approved"),
        (not data_license_approved, "data_license_not_approved"),
        (not paper_only, "paper_only_required"),
    )
    reasons = tuple(reason for failed, reason in checks if failed)
    # A non-paper request is denied but cannot change this evaluator's paper-only boundary.
    result = {"approved": not reasons, "paper_only": True, "denial_reasons": reasons, "policy": _POLICY}
    return PaperComplianceDecision(**result, receipt_sha256=_receipt(result))


def reject_paper_compliance_effect(operation: str) -> None:
    raise ValueError("paper_only_compliance_policy_no_effects")
