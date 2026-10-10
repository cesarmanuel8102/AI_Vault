from __future__ import annotations

import pytest

from ibkr_paper_30d.sleeve_reconciliation import SleeveReconciler


REGULAR = "REGULAR_SLEEVE"
EXTENDED = "EXTENDED_SLEEVE"
STOCK = "a" * 64
FUTURE = "b" * 64


def _ledgers():
    return {
        "regular": {
            "currency_balances": [{"currency": "USD", "amount": "380"}],
            "positions": [{"contract_identity_sha256": STOCK, "quantity": "1"}],
            "open_order_count": 0,
            "fees_usd": "1",
        },
        "extended": {
            "currency_balances": [{"currency": "USD", "amount": "450"}],
            "positions": [{"contract_identity_sha256": FUTURE, "quantity": "2"}],
            "open_order_count": 1,
            "fees_usd": "2",
        },
        "aggregate_currency_balances": [{"currency": "USD", "amount": "830"}],
    }


def _ownership():
    return {
        "active_contracts": [
            {"contract_identity_sha256": STOCK, "sleeve": REGULAR},
            {"contract_identity_sha256": FUTURE, "sleeve": EXTENDED},
        ],
        "projection_sha256": "c" * 64,
    }


def _account():
    return {
        "paper_only": True,
        "currency_balances": [{"currency": "USD", "amount": "830"}],
        "positions": [
            {"contract_identity_sha256": STOCK, "quantity": "1"},
            {"contract_identity_sha256": FUTURE, "quantity": "2"},
        ],
        "open_orders": [{"contract_identity_sha256": FUTURE}],
        "executions": [
            {"contract_identity_sha256": STOCK, "execution_id": "one"},
            {"contract_identity_sha256": FUTURE, "execution_id": "two"},
        ],
        "fees": [
            {"contract_identity_sha256": STOCK, "amount": "1"},
            {"contract_identity_sha256": FUTURE, "amount": "2"},
        ],
        "financing": [],
    }


def test_exact_account_to_sleeve_reconciliation_passes() -> None:
    receipt = SleeveReconciler.reconcile(_account(), _ledgers(), _ownership())

    assert receipt.status == "PASS"
    assert receipt.freeze_new_entries is False
    assert receipt.per_sleeve[REGULAR]["position_count"] == 1
    assert receipt.per_sleeve[EXTENDED]["open_order_count"] == 1


def test_unattributed_or_aggregate_mismatch_freezes_new_entries() -> None:
    account = _account()
    account["positions"].append(
        {"contract_identity_sha256": "d" * 64, "quantity": "1"}
    )
    account["currency_balances"] = [{"currency": "USD", "amount": "831"}]

    receipt = SleeveReconciler.reconcile(account, _ledgers(), _ownership())

    assert receipt.status == "BLOCK"
    assert receipt.freeze_new_entries is True
    assert "UNATTRIBUTED_ACCOUNT_EVENT" in receipt.reason_codes
    assert "AGGREGATE_CURRENCY_MISMATCH:USD" in receipt.reason_codes


def test_verified_descendant_inherits_source_sleeve() -> None:
    account = _account()
    account["positions"].append(
        {
            "contract_identity_sha256": "d" * 64,
            "source_contract_identity_sha256": STOCK,
            "lineage_event": "OPTION_ASSIGNMENT",
            "quantity": "0",
        }
    )

    receipt = SleeveReconciler.reconcile(account, _ledgers(), _ownership())

    assert receipt.status == "PASS"
    assert receipt.lineage_assignments["d" * 64] == REGULAR


def test_unknown_lineage_or_cross_sleeve_cash_never_borrows_authority() -> None:
    account = _account()
    account["financing"] = [
        {"contract_identity_sha256": "e" * 64, "amount": "10"}
    ]

    receipt = SleeveReconciler.reconcile(account, _ledgers(), _ownership())

    assert receipt.status == "BLOCK"
    assert "UNATTRIBUTED_ACCOUNT_EVENT" in receipt.reason_codes


@pytest.mark.parametrize(
    "lineage_event",
    (
        "OPTION_ASSIGNMENT",
        "OPTION_EXERCISE",
        "BAG_LEG_MATERIALIZATION",
        "SETTLEMENT",
        "SPLIT",
        "MERGER",
        "SPIN_OFF",
        "CONTRACT_REPLACEMENT",
    ),
)
def test_verified_descendant_events_inherit_ownership_and_economics(
    lineage_event: str,
) -> None:
    account = _account()
    descendant = "d" * 64
    account["executions"].append(
        {
            "contract_identity_sha256": descendant,
            "source_contract_identity_sha256": STOCK,
            "lineage_event": lineage_event,
            "execution_id": f"descendant-{lineage_event}",
        }
    )
    account["fees"].append(
        {
            "contract_identity_sha256": descendant,
            "source_contract_identity_sha256": STOCK,
            "lineage_event": lineage_event,
            "amount": "0.25",
        }
    )
    ledgers = _ledgers()
    ledgers["regular"]["fees_usd"] = "1.25"

    receipt = SleeveReconciler.reconcile(account, ledgers, _ownership())

    assert receipt.status == "PASS"
    assert receipt.lineage_assignments[descendant] == REGULAR
    assert receipt.per_sleeve[REGULAR]["fees_usd"] == "1.25"


def test_fill_and_commission_mismatch_is_attributed_but_blocks() -> None:
    account = _account()
    account["fees"][0]["amount"] = "1.50"

    receipt = SleeveReconciler.reconcile(account, _ledgers(), _ownership())

    assert receipt.status == "BLOCK"
    assert "SLEEVE_FEES_MISMATCH:REGULAR_SLEEVE" in receipt.reason_codes
    assert "UNATTRIBUTED_ACCOUNT_EVENT" not in receipt.reason_codes
