from __future__ import annotations

from types import SimpleNamespace

from ibkr_paper_30d.open_order_management import (
    EXECUTION_CLIENT_ID,
    canonical_open_order,
)


def trade(*, limit_price=10):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=EXECUTION_CLIENT_ID,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=limit_price,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0
        ),
    )


def test_canonical_order_contains_complete_identity_and_hash():
    value = canonical_open_order(trade())

    assert value["orderRef"] == "codex-ibkr-paper-30d-a-cycle"
    assert value["orderId"] == 41
    assert value["permId"] == 9001
    assert value["clientId"] == EXECUTION_CLIENT_ID
    assert value["contract"]["conId"] == 756733
    assert len(value["state_sha256"]) == 64


def test_decimal_representation_does_not_change_state_hash():
    assert canonical_open_order(trade(limit_price=10))["state_sha256"] == (
        canonical_open_order(trade(limit_price="10.00"))["state_sha256"]
    )


def test_execution_client_is_outside_research_client_range():
    assert EXECUTION_CLIENT_ID == 19761
    assert not 19800 <= EXECUTION_CLIENT_ID <= 19899
