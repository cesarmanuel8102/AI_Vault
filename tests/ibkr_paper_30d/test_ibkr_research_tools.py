from __future__ import annotations

from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import ResearchRequest, ResearchTool
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox


def trade():
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
            clientId=19761,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=10,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(status="Submitted", filled=0, remaining=2),
    )


class FakeIB:
    def __init__(self):
        self.disconnected = False
        self.req_all_open_orders_calls = 0

    def reqAllOpenOrders(self):
        self.req_all_open_orders_calls += 1
        return [trade()]

    def disconnect(self):
        self.disconnected = True


def test_open_orders_are_global_canonical_snapshots():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    fake = FakeIB()
    subject._connect = lambda: fake

    result = subject._open_orders({})

    value = result["open_orders"][0]
    assert result["success"] is True
    assert value["permId"] == 9001
    assert value["clientId"] == 19761
    assert value["contract"]["conId"] == 756733
    assert len(value["state_sha256"]) == 64
    assert fake.req_all_open_orders_calls == 1
    assert fake.disconnected is True


def test_contract_builder_accepts_canonical_nested_contract_arguments():
    subject = IBKRResearchToolbox(expected_account_hash="unused")

    contract = subject._contract_from_spec(
        {
            "contract": {
                "conId": 395194484,
                "symbol": "XP",
                "secType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
            "wait_seconds": 2,
        }
    )

    assert contract.conId == 395194484
    assert contract.symbol == "XP"
    assert contract.secType == "STK"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"


def test_contract_builder_rejects_conflicting_nested_and_flat_identity():
    subject = IBKRResearchToolbox(expected_account_hash="unused")

    with pytest.raises(ValueError, match="CONTRACT_ARGUMENT_IDENTITY_CONFLICT"):
        subject._contract_from_spec(
            {
                "symbol": "SPY",
                "contract": {
                    "conId": 395194484,
                    "symbol": "XP",
                    "secType": "STK",
                },
            }
        )


def test_contract_builder_rejects_conflicting_aliases_within_one_level():
    subject = IBKRResearchToolbox(expected_account_hash="unused")

    with pytest.raises(ValueError, match="CONTRACT_ARGUMENT_IDENTITY_CONFLICT"):
        subject._contract_from_spec(
            {
                "conId": 111,
                "contract_id": 222,
                "contract": {
                    "conId": 111,
                    "symbol": "XP",
                    "secType": "STK",
                },
            }
        )


def test_toolbox_normalizes_connection_subclass_error_category(monkeypatch):
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    monkeypatch.setattr(
        subject,
        "_positions",
        lambda _args: (_ for _ in ()).throw(ConnectionRefusedError("offline")),
    )
    request = ResearchRequest(
        request_id="connection-category",
        tool=ResearchTool.POSITIONS,
        arguments={},
        purpose="classify broker transport failure",
    )

    result = subject.execute(request, SimpleNamespace())

    assert result.success is False
    assert result.error == "ConnectionError:tool_failed"
