from __future__ import annotations

from decimal import Decimal

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.contract_ownership import ContractOwnershipStore, canonical_contract_identity
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import (
    CarryForwardPosition,
    CurrencyBalance,
    RegularCarryForward,
    SleeveLedgerError,
    SleeveLedgerStore,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _store(tmp_path) -> tuple[Database, SleeveLedgerStore]:
    db = Database.open(tmp_path / "sleeves.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    return db, SleeveLedgerStore(db)


def _carry(*, source_hash: str = "a" * 64) -> RegularCarryForward:
    return RegularCarryForward(
        allocation_usd=Decimal("500.00"),
        currency_balances=(
            CurrencyBalance(currency="USD", amount=Decimal("420.00")),
            CurrencyBalance(currency="EUR", amount=Decimal("40.00")),
        ),
        positions=(
            CarryForwardPosition(
                contract_identity_sha256="b" * 64,
                quantity=Decimal("2"),
                multiplier=Decimal("1"),
                average_cost=Decimal("35.00"),
                mark=Decimal("40.00"),
                market_value_usd=Decimal("80.00"),
            ),
        ),
        open_order_count=1,
        fill_count=3,
        fees_usd=Decimal("5.25"),
        realized_pnl_usd=Decimal("12.50"),
        unrealized_pnl_usd=Decimal("10.00"),
        historical_event_sha256=("c" * 64, "d" * 64),
        source_ledger_sha256=source_hash,
    )


def test_regular_bootstrap_preserves_exact_day1_economics(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        carry = _carry()
        receipt = store.bootstrap_regular(carry)
        state = store.project(CapitalSleeve.REGULAR_SLEEVE)

        assert receipt.duplicate is False
        assert state.initialized is True
        assert state.allocation_usd == Decimal("500.00")
        assert state.currency_balances == carry.currency_balances
        assert state.positions == carry.positions
        assert state.open_order_count == 1
        assert state.fill_count == 3
        assert state.fees_usd == Decimal("5.25")
        assert state.realized_pnl_usd == Decimal("12.50")
        assert state.unrealized_pnl_usd == Decimal("10.00")
        assert state.historical_event_sha256 == ("c" * 64, "d" * 64)
        assert state.source_ledger_sha256 == "a" * 64
    finally:
        db.close()


def test_extended_bootstrap_is_exactly_usd_500_and_flat(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        receipt = store.bootstrap_extended()
        state = store.project(CapitalSleeve.EXTENDED_SLEEVE)

        assert receipt.duplicate is False
        assert state.allocation_usd == Decimal("500.00")
        assert state.currency_balances == (
            CurrencyBalance(currency="USD", amount=Decimal("500.00")),
        )
        assert state.realized_pnl_usd == Decimal("0.00")
        assert state.unrealized_pnl_usd == Decimal("0.00")
        assert state.positions == ()
        assert state.open_order_count == 0
        assert state.fill_count == 0
    finally:
        db.close()


def test_regular_bootstrap_retry_requires_identical_carry_hash(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        first = store.bootstrap_regular(_carry())
        retry = store.bootstrap_regular(_carry())
        assert retry.duplicate is True
        assert retry.event_sha256 == first.event_sha256

        with pytest.raises(SleeveLedgerError, match="BOOTSTRAP_CONFLICT"):
            store.bootstrap_regular(_carry(source_hash="e" * 64))
        assert store.project(CapitalSleeve.REGULAR_SLEEVE).event_count == 1
    finally:
        db.close()


def test_currency_balances_are_separate_and_aggregate_by_currency(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        store.bootstrap_regular(_carry())
        store.bootstrap_extended()
        store.append(
            CapitalSleeve.EXTENDED_SLEEVE,
            "CURRENCY_CREDIT",
            {"currency": "EUR", "amount": "25.00"},
        )

        all_state = store.project_all()
        assert all_state.regular.balance("USD") == Decimal("420.00")
        assert all_state.extended.balance("USD") == Decimal("500.00")
        assert all_state.regular.balance("EUR") == Decimal("40.00")
        assert all_state.extended.balance("EUR") == Decimal("25.00")
        assert all_state.aggregate_balance("USD") == Decimal("920.00")
        assert all_state.aggregate_balance("EUR") == Decimal("65.00")
    finally:
        db.close()


def test_one_sleeve_cannot_spend_or_pledge_the_others_currency(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        store.bootstrap_regular(_carry())
        store.bootstrap_extended()

        with pytest.raises(SleeveLedgerError, match="SLEEVE_CURRENCY_INSUFFICIENT"):
            store.append(
                CapitalSleeve.EXTENDED_SLEEVE,
                "CURRENCY_DEBIT",
                {"currency": "EUR", "amount": "1.00"},
            )
        with pytest.raises(SleeveLedgerError, match="CROSS_SLEEVE_PLEDGE_FORBIDDEN"):
            store.append(
                CapitalSleeve.EXTENDED_SLEEVE,
                "LIABILITY_RESERVED",
                {
                    "amount_usd": "100.00",
                    "collateral_sleeve": "REGULAR_SLEEVE",
                },
            )

        assert store.project(CapitalSleeve.REGULAR_SLEEVE).balance("EUR") == Decimal("40.00")
        assert store.project(CapitalSleeve.EXTENDED_SLEEVE).balance("EUR") == Decimal("0.00")
    finally:
        db.close()


def test_broker_snapshot_projects_owned_positions_orders_fills_and_fees(tmp_path) -> None:
    db, store = _store(tmp_path)
    contract = canonical_contract_identity(
        {
            "conId": 9001,
            "secType": "FUT",
            "currency": "USD",
            "exchange": "GLOBEX",
            "localSymbol": "MESZ6",
            "multiplier": "5",
        }
    )
    try:
        store.bootstrap_regular(_carry())
        store.bootstrap_extended()
        ownership = ContractOwnershipStore(db)
        ownership.claim(CapitalSleeve.EXTENDED_SLEEVE, contract)
        receipt = store.reconcile_broker_snapshot(
            {
                "positions": [
                    {
                        "contract_identity_sha256": contract.sha256,
                        "quantity": "1",
                        "multiplier": "5",
                        "average_cost": "10",
                        "mark": "11",
                        "market_value_usd": "55",
                    }
                ],
                "open_orders": [
                    {"contract_identity_sha256": contract.sha256}
                ],
                "executions": [
                    {
                        "contract_identity_sha256": contract.sha256,
                        "execution_id_hash": "e" * 64,
                        "commission": "1.25",
                    }
                ],
            },
            ownership.projection(),
        )
        state = store.project(CapitalSleeve.EXTENDED_SLEEVE)
        assert receipt[CapitalSleeve.EXTENDED_SLEEVE.value]
        assert state.positions[0].contract_identity_sha256 == contract.sha256
        assert state.open_order_count == 1
        assert state.fill_count == 1
        assert state.fees_usd == Decimal("1.25")

        again = store.reconcile_broker_snapshot(
            {
                "positions": [
                    {
                        "contract_identity_sha256": contract.sha256,
                        "quantity": "1",
                        "multiplier": "5",
                        "average_cost": "10",
                        "mark": "11",
                        "market_value_usd": "55",
                    }
                ],
                "open_orders": [
                    {"contract_identity_sha256": contract.sha256}
                ],
                "executions": [
                    {
                        "contract_identity_sha256": contract.sha256,
                        "execution_id_hash": "e" * 64,
                        "commission": "1.25",
                    }
                ],
            },
            ownership.projection(),
        )
        assert again == receipt
        assert state.event_count + 0 == store.project(CapitalSleeve.EXTENDED_SLEEVE).event_count
    finally:
        db.close()
