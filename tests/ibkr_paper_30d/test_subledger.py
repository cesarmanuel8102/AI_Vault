from __future__ import annotations

from decimal import Decimal

from ibkr_paper_30d.subledger import (
    BrokerAccountSnapshot,
    Subledger,
    SubledgerEvent,
)


def buy(symbol: str, quantity: str, price: str) -> SubledgerEvent:
    return SubledgerEvent(
        event_type="BUY_FILL",
        symbol=symbol,
        quantity=Decimal(quantity),
        price=Decimal(price),
    )


def sell(symbol: str, quantity: str, price: str) -> SubledgerEvent:
    return SubledgerEvent(
        event_type="SELL_FILL",
        symbol=symbol,
        quantity=Decimal(quantity),
        price=Decimal(price),
    )


def mark(symbol: str, price: str) -> SubledgerEvent:
    return SubledgerEvent(event_type="MARK", symbol=symbol, price=Decimal(price))


def fee(amount: str) -> SubledgerEvent:
    return SubledgerEvent(event_type="FEE", amount=Decimal(amount))


def test_broker_buying_power_cannot_raise_allocation() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    state = ledger.project([])
    snapshot = BrokerAccountSnapshot(
        cash=Decimal("100000.00"),
        settled_cash=Decimal("100000.00"),
        buying_power=Decimal("400000.00"),
        net_liquidation=Decimal("100000.00"),
        market_value=Decimal("0"),
    )

    receipt = ledger.reconcile(snapshot, state)

    assert receipt.maximum_allocated_capital == Decimal("500.00")
    assert receipt.broker_buying_power == Decimal("400000.00")


def test_fill_fee_and_mark_update_equity() -> None:
    ledger = Subledger.start(Decimal("500.00"))

    state = ledger.project([buy("SPY", "1", "100"), fee("1"), mark("SPY", "110")])

    assert state.cash == Decimal("399.00")
    assert state.market_value == Decimal("110.00")
    assert state.unrealized_pnl == Decimal("10.00")
    assert state.fees == Decimal("1.00")
    assert state.equity == Decimal("509.00")
    assert state.high_water_mark == Decimal("509.00")


def test_sell_fill_realizes_profit_without_double_counting() -> None:
    ledger = Subledger.start(Decimal("500.00"))

    state = ledger.project(
        [buy("SPY", "1", "100"), mark("SPY", "110"), sell("SPY", "1", "110")]
    )

    assert state.cash == Decimal("510.00")
    assert state.market_value == Decimal("0.00")
    assert state.realized_pnl == Decimal("10.00")
    assert state.unrealized_pnl == Decimal("0.00")
    assert state.equity == Decimal("510.00")


def test_high_water_and_drawdown_follow_event_sequence() -> None:
    ledger = Subledger.start(Decimal("500.00"))

    state = ledger.project(
        [buy("SPY", "1", "100"), mark("SPY", "120"), mark("SPY", "80")]
    )

    assert state.high_water_mark == Decimal("520.00")
    assert state.equity == Decimal("480.00")
    assert state.drawdown == Decimal("40.00")


def test_reprojection_after_restart_is_identical() -> None:
    events = [buy("SPY", "2", "100"), fee("2"), mark("SPY", "105")]

    before = Subledger.start(Decimal("500.00")).project(events)
    after = Subledger.start(Decimal("500.00")).project(list(events))

    assert before == after


def test_broker_subledger_mismatch_blocks_reconciliation() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    state = ledger.project([buy("SPY", "1", "100"), mark("SPY", "100")])
    broker = BrokerAccountSnapshot(
        cash=Decimal("512.70"),
        settled_cash=Decimal("512.70"),
        buying_power=Decimal("512.70"),
        net_liquidation=Decimal("512.70"),
        market_value=Decimal("0"),
    )

    receipt = ledger.reconcile(broker, state)

    assert receipt.status == "BLOCK"
    assert "POSITION_VALUE_MISMATCH" in receipt.reason_codes


def test_fee_cannot_drive_cash_below_zero_silently() -> None:
    ledger = Subledger.start(Decimal("500.00"))

    state = ledger.project([fee("501")])

    assert state.valid is False
    assert state.reason_codes == ("NEGATIVE_CASH", "NEGATIVE_SETTLED_CASH")


def test_long_option_uses_contract_multiplier_in_cash_and_equity() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="BUY_FILL",
            symbol="XYZ",
            contract_id=101,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("2.00"),
            multiplier=Decimal("100"),
        ),
        SubledgerEvent(
            event_type="MARK",
            symbol="XYZ",
            contract_id=101,
            security_type="OPT",
            price=Decimal("3.00"),
        ),
    ]

    state = ledger.project(events)

    assert state.cash == Decimal("300.00")
    assert state.market_value == Decimal("300.00")
    assert state.unrealized_pnl == Decimal("100.00")
    assert state.equity == Decimal("600.00")


def test_short_option_leg_is_valid_and_marks_signed_market_value() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="SELL_FILL",
            symbol="XYZ",
            contract_id=202,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("1.50"),
            multiplier=Decimal("100"),
        ),
        SubledgerEvent(
            event_type="MARK",
            symbol="XYZ",
            contract_id=202,
            security_type="OPT",
            price=Decimal("1.00"),
        ),
    ]

    state = ledger.project(events)

    assert state.valid is True
    assert state.cash == Decimal("650.00")
    assert state.market_value == Decimal("-100.00")
    assert state.unrealized_pnl == Decimal("50.00")
    assert state.equity == Decimal("550.00")


def test_closing_short_option_realizes_profit() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="SELL_FILL",
            symbol="XYZ",
            contract_id=303,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("2.00"),
            multiplier=Decimal("100"),
        ),
        SubledgerEvent(
            event_type="BUY_FILL",
            symbol="XYZ",
            contract_id=303,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("1.25"),
            multiplier=Decimal("100"),
        ),
    ]

    state = ledger.project(events)

    assert state.cash == Decimal("575.00")
    assert state.market_value == Decimal("0.00")
    assert state.realized_pnl == Decimal("75.00")
    assert state.equity == Decimal("575.00")


def test_defined_risk_vertical_can_hold_long_and_short_option_legs() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="BUY_FILL",
            symbol="XYZ",
            contract_id=401,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("2.00"),
            multiplier=Decimal("100"),
        ),
        SubledgerEvent(
            event_type="SELL_FILL",
            symbol="XYZ",
            contract_id=402,
            security_type="OPT",
            quantity=Decimal("1"),
            price=Decimal("1.00"),
            multiplier=Decimal("100"),
        ),
        SubledgerEvent(
            event_type="MARK",
            symbol="XYZ",
            contract_id=401,
            security_type="OPT",
            price=Decimal("3.00"),
        ),
        SubledgerEvent(
            event_type="MARK",
            symbol="XYZ",
            contract_id=402,
            security_type="OPT",
            price=Decimal("1.50"),
        ),
    ]

    state = ledger.project(events)

    assert state.valid is True
    assert state.cash == Decimal("400.00")
    assert state.market_value == Decimal("150.00")
    assert state.unrealized_pnl == Decimal("50.00")
    assert state.equity == Decimal("550.00")


def test_future_uses_variation_pnl_not_notional_cash() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="BUY_FILL",
            symbol="MES",
            contract_id=501,
            security_type="FUT",
            quantity=Decimal("1"),
            price=Decimal("5000"),
            multiplier=Decimal("5"),
        ),
        SubledgerEvent(
            event_type="MARK",
            symbol="MES",
            contract_id=501,
            security_type="FUT",
            price=Decimal("5010"),
        ),
    ]

    state = ledger.project(events)

    assert state.cash == Decimal("500.00")
    assert state.market_value == Decimal("50.00")
    assert state.unrealized_pnl == Decimal("50.00")
    assert state.equity == Decimal("550.00")


def test_future_close_moves_realized_variation_to_cash() -> None:
    ledger = Subledger.start(Decimal("500.00"))
    events = [
        SubledgerEvent(
            event_type="BUY_FILL",
            symbol="MES",
            contract_id=502,
            security_type="FUT",
            quantity=Decimal("1"),
            price=Decimal("5000"),
            multiplier=Decimal("5"),
        ),
        SubledgerEvent(
            event_type="SELL_FILL",
            symbol="MES",
            contract_id=502,
            security_type="FUT",
            quantity=Decimal("1"),
            price=Decimal("5010"),
            multiplier=Decimal("5"),
        ),
    ]

    state = ledger.project(events)

    assert state.cash == Decimal("550.00")
    assert state.realized_pnl == Decimal("50.00")
    assert state.market_value == Decimal("0.00")
    assert state.equity == Decimal("550.00")
