"""R13.2 contract: paper-only tax-lot audit and manual-review routing."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _audit(**overrides):
    from tmp_agent.brain_v9.core.paper_trading_compliance_audit import (
        audit_paper_tax_lot,
    )

    values = {
        "account_id": "paper-account-1",
        "symbol": "SPY",
        "opened_at_utc": "2026-09-09T00:00:00Z",
        "quantity": 10,
        "cost_basis": "500.00",
        "restricted": False,
        "evidence_complete": True,
        "seen_tax_lot_ids": (),
    }
    values.update(overrides)
    return audit_paper_tax_lot(**values)


def test_complete_unique_tax_lot_has_immutable_deterministic_receipt():
    first = _audit()
    second = _audit()

    assert first == second
    assert first.approved is True
    assert first.manual_review is False
    assert first.reason is None
    assert first.paper_only is True
    assert len(first.tax_lot_id) == 64
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.approved = False


def test_duplicate_tax_lot_is_denied_without_creating_an_effect():
    first = _audit()
    duplicate = _audit(seen_tax_lot_ids=(first.tax_lot_id,))

    assert duplicate.approved is False
    assert duplicate.manual_review is True
    assert duplicate.reason == "duplicate_tax_lot"
    assert duplicate.tax_lot_id == first.tax_lot_id


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"restricted": True}, "restricted_symbol_manual_review"),
        ({"evidence_complete": False}, "incomplete_evidence_manual_review"),
        ({"quantity": 0}, "invalid_quantity"),
        ({"cost_basis": "0"}, "invalid_cost_basis"),
    ],
)
def test_non_approvable_paper_tax_lots_are_denied_or_routed_to_manual_review(overrides, reason):
    receipt = _audit(**overrides)

    assert receipt.approved is False
    assert receipt.paper_only is True
    assert receipt.reason == reason


@pytest.mark.parametrize(
    "operation",
    (
        "broker_connect",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    ),
)
def test_audit_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.paper_trading_compliance_audit import (
        reject_paper_compliance_audit_effect,
    )

    with pytest.raises(ValueError, match="paper_only_compliance_audit_no_effects"):
        reject_paper_compliance_audit_effect(operation)


def test_evidence_declares_paper_only_no_deploy_audit_contract():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R13_2_COMPLIANCE_AUDIT_TAX_LOT_MANUAL_REVIEW.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R13.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["paper_only"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())
