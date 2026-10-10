from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import ResearchRequest, ResearchTool
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.ibkr_research_tools import (
    IBKRResearchToolbox,
    PositionExecutionContractError,
    capability_evidence_from_broker_checks,
    resolve_position_execution_contract,
)


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


class FakeAccountSummaryIB:
    def __init__(self):
        self.disconnected = False

    def accountSummary(self):
        return [
            SimpleNamespace(tag="TotalCashValue", currency="BASE", value="999999"),
            SimpleNamespace(tag="TotalCashValue", currency="USD", value="1000000"),
            SimpleNamespace(tag="TotalCashValue", currency="EUR", value="125.50"),
            SimpleNamespace(tag="BuyingPower", currency="USD", value="9999999"),
        ]

    def reqCurrentTime(self):
        return datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)

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


def test_account_reconciliation_snapshot_reads_independent_broker_cash():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake = FakeAccountSummaryIB()
    subject._connect = lambda: fake

    snapshot = subject.account_reconciliation_snapshot()

    assert snapshot["paper_only"] is True
    assert snapshot["account_identity_sha256"] == "a" * 64
    assert snapshot["currency_balances"] == [
        {"currency": "EUR", "amount": "125.50"},
        {"currency": "USD", "amount": "1000000"},
    ]
    assert len(snapshot["broker_snapshot_sha256"]) == 64
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


def test_position_execution_contract_fails_closed_when_qualification_is_absent():
    contract = SimpleNamespace(
        conId=7884,
        symbol="HAE",
        secType="STK",
        exchange="NYSE",
        primaryExchange="",
    )
    broker = SimpleNamespace(qualifyContracts=lambda resolved: [])

    with pytest.raises(
        PositionExecutionContractError,
        match="POSITION_ACTION_CONTRACT_QUALIFICATION_NOT_FOUND",
    ):
        resolve_position_execution_contract(broker, contract)


def test_position_execution_contract_fails_closed_on_identity_change():
    contract = SimpleNamespace(
        conId=7884,
        symbol="HAE",
        secType="STK",
        exchange="NYSE",
        primaryExchange="",
    )

    def qualify(resolved):
        resolved.conId = 9999
        return [resolved]

    broker = SimpleNamespace(qualifyContracts=qualify)

    with pytest.raises(
        PositionExecutionContractError,
        match="POSITION_ACTION_CONTRACT_IDENTITY_MISMATCH",
    ):
        resolve_position_execution_contract(broker, contract)


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


def test_broker_checks_remain_descriptive_until_every_execution_fact_is_proven():
    now = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
    evidence = capability_evidence_from_broker_checks(
        candidate={"symbol": "MODEL_CHOSEN", "secType": "FUT"},
        paper_account_sha256="a" * 64,
        contract_qualified=True,
        permissions_verified=True,
        market_data_verified=True,
        order_semantics_verified=True,
        quantity_semantics_verified=True,
        bounded_economics_verified=False,
        paper_limitations=("PAPER_SIMULATION_ONLY",),
        observed_at_utc=now,
        expires_at_utc=now + timedelta(hours=1),
    )
    assert evidence.research_visible is True
    assert evidence.execution_ready is False


def test_v4_equity_selection_is_bound_to_the_declared_sleeve():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    bundle = SimpleNamespace(
        multi_sleeve_v4_active=True,
        experiment_subledger_snapshot={"equity": "9999.00"},
        multi_sleeve_portfolio={
            "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
            "sleeves": {
                "regular": {"equity_usd": "475.00"},
                "extended": {"equity_usd": "321.50"},
            },
        },
    )

    assert subject._capital_equity(bundle, CapitalSleeve.REGULAR_SLEEVE) == Decimal(
        "475.00"
    )
    assert subject._capital_equity(bundle, CapitalSleeve.EXTENDED_SLEEVE) == Decimal(
        "321.50"
    )


def test_v4_equity_selection_fails_closed_without_a_sleeve_binding():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    bundle = SimpleNamespace(
        multi_sleeve_v4_active=True,
        experiment_subledger_snapshot={"equity": "9999.00"},
        multi_sleeve_portfolio={
            "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
            "sleeves": {
                "regular": {"equity_usd": "475.00"},
                "extended": {"equity_usd": "321.50"},
            },
        },
    )

    with pytest.raises(ValueError, match="V4_SLEEVE_BINDING_REQUIRED"):
        subject._capital_equity(bundle, None)
