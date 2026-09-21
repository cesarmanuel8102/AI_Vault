from __future__ import annotations

from decimal import Decimal

from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.persistence import Database


def fill(exec_hash, side, price, *, con_id=101, symbol="TEST", sec_type="OPT", multiplier="100", commission="1"):
    return {
        "execution_id_hash": exec_hash,
        "side": side,
        "quantity": "1",
        "price": str(price),
        "commission": commission,
        "contract": {
            "conId": con_id,
            "symbol": symbol,
            "secType": sec_type,
            "multiplier": multiplier,
        },
    }


def test_option_multiplier_and_marks_drive_isolated_equity(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db, allocation=Decimal("500.00"))
        ledger.record_fill(fill("e1", "BUY", "2.00"))
        after_fill = ledger.project()

        assert after_fill.cash == Decimal("299.00")
        assert after_fill.market_value == Decimal("200.00")
        assert after_fill.equity == Decimal("499.00")
        assert after_fill.fees == Decimal("1.00")

        ledger.record_mark(contract_id=101, symbol="TEST", price=Decimal("3.00"))
        marked = ledger.project()

        assert marked.market_value == Decimal("300.00")
        assert marked.equity == Decimal("599.00")
        assert marked.high_water_mark == Decimal("599.00")


def test_closing_fill_returns_cash_and_zeroes_position(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        ledger.record_fill(fill("e1", "BUY", "2.00"))
        ledger.record_fill(fill("e2", "SELL", "4.00"))
        state = ledger.project()

        assert state.cash == Decimal("698.00")
        assert state.market_value == Decimal("0.00")
        assert state.equity == Decimal("698.00")
        assert state.fees == Decimal("2.00")
        assert state.positions == ()


def test_execution_hash_deduplicates_delayed_fill_reconciliation(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        first = ledger.record_fill(fill("same-exec", "BUY", "2.00"))
        second = ledger.record_fill(fill("same-exec", "BUY", "2.00"))
        state = ledger.project()

        assert first != second
        assert second.startswith("duplicate:")
        assert state.event_count == 1
        assert state.cash == Decimal("299.00")


def test_defined_risk_spread_legs_are_accounted_independently(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        ledger.record_fill(fill("long", "BUY", "2.00", con_id=201, symbol="XYZ"))
        ledger.record_fill(fill("short", "SELL", "1.00", con_id=202, symbol="XYZ"))
        ledger.record_mark(contract_id=201, symbol="XYZ", price=Decimal("2.50"))
        ledger.record_mark(contract_id=202, symbol="XYZ", price=Decimal("1.20"))
        state = ledger.project()

        assert state.cash == Decimal("398.00")
        assert state.market_value == Decimal("130.00")
        assert state.equity == Decimal("528.00")
        assert len(state.positions) == 2


def test_weighted_average_cost_survives_partial_close(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db, allocation=Decimal("1000.00"))
        ledger.record_fill(fill("e1", "BUY", "2.00", con_id=301, symbol="XYZ", commission="0"))
        second = fill("e2", "BUY", "4.00", con_id=301, symbol="XYZ", commission="0")
        second["quantity"] = "1"
        ledger.record_fill(second)
        state = ledger.project()
        pos = state.positions[0]
        assert pos.quantity == Decimal("2")
        assert pos.average_cost == Decimal("3.00")

        close = fill("e3", "SELL", "5.00", con_id=301, symbol="XYZ", commission="0")
        close["quantity"] = "1"
        ledger.record_fill(close)
        state = ledger.project()
        pos = state.positions[0]
        assert pos.quantity == Decimal("1")
        assert pos.average_cost == Decimal("3.00")
        assert state.cash == Decimal("900.00")
        assert state.market_value == Decimal("500.00")
        assert state.equity == Decimal("1400.00")


def test_late_commission_report_appends_adjustment_without_double_counting_fill(tmp_path):
    fill = {
        "execution_id_hash": "late-commission-1",
        "orderRef": "codex-ibkr-paper-30d-a-test",
        "permId": 10,
        "orderId": 11,
        "clientId": 12,
        "execution_time": "2026-09-21T13:31:00Z",
        "side": "BUY",
        "quantity": "1",
        "price": "2.00",
        "commission": "0",
        "contract": {
            "conId": 123,
            "symbol": "XYZ",
            "secType": "OPT",
            "multiplier": "100",
        },
    }
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        ledger.record_fill(fill)
        first = ledger.project()
        assert first.equity == Decimal("500.00")
        assert first.fees == Decimal("0.00")

        updated = dict(fill)
        updated["commission"] = "1.25"
        event_id = ledger.record_fill(updated)
        assert not event_id.startswith("duplicate:")

        second = ledger.project()
        assert second.event_count == 2
        assert second.equity == Decimal("498.75")
        assert second.fees == Decimal("1.25")

        duplicate = ledger.record_fill(updated)
        assert duplicate.startswith("duplicate:")
        assert ledger.project().event_count == 2

        missing_again = dict(updated)
        missing_again["commission"] = None
        duplicate_missing = ledger.record_fill(missing_again)
        assert duplicate_missing.startswith("duplicate:")
        final = ledger.project()
        assert final.event_count == 2
        assert final.fees == Decimal("1.25")


def test_missing_exec_id_then_real_exec_id_does_not_double_count(tmp_path):
    base = {
        "orderRef": "codex-ibkr-paper-30d-a-test",
        "permId": 10,
        "orderId": 11,
        "clientId": 12,
        "execution_time": "2026-09-21T13:31:00Z",
        "side": "BUY",
        "quantity": "1",
        "price": "2.00",
        "commission": None,
        "contract": {
            "conId": 123,
            "symbol": "XYZ",
            "secType": "OPT",
            "multiplier": "100",
        },
    }
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)

        first = dict(base)
        first["execution_id_hash"] = None
        first_id = ledger.record_fill(first)
        assert not first_id.startswith("duplicate:")

        second = dict(base)
        second["execution_id_hash"] = "f" * 64
        second["commission"] = "1.00"
        second_id = ledger.record_fill(second)
        assert not second_id.startswith("duplicate:")

        state = ledger.project()
        assert state.event_count == 2
        assert state.equity == Decimal("499.00")
        assert state.fees == Decimal("1.00")
        assert len(state.positions) == 1
        assert state.positions[0].quantity == Decimal("1")
