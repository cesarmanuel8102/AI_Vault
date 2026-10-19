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
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash


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

    def accountValues(self):
        return [
            SimpleNamespace(tag="TotalCashValue", currency="BASE", value="999999"),
            SimpleNamespace(tag="TotalCashValue", currency="USD", value="1000000"),
            SimpleNamespace(tag="TotalCashValue", currency="EUR", value="125.50"),
            SimpleNamespace(
                tag="$LEDGER-CashBalance", currency="USD", value="1000500.31"
            ),
            SimpleNamespace(tag="$LEDGER-CashBalance", currency="EUR", value="125.50"),
            SimpleNamespace(tag="BuyingPower", currency="USD", value="9999999"),
        ]

    def accountSummary(self):
        pytest.fail("cash reconciliation must use connection-synchronized account values")

    def reqCurrentTime(self):
        return datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)

    def disconnect(self):
        self.disconnected = True


class FakeHistoricalIB:
    def __init__(self):
        self.requests = []
        self.disconnected = False

    def qualifyContracts(self, contract):
        contract.conId = contract.conId or 479624278
        contract.localSymbol = contract.localSymbol or contract.symbol
        return [contract]

    def reqHistoricalData(self, contract, **kwargs):
        self.requests.append((contract, kwargs))
        if kwargs["whatToShow"] != "AGGTRADES":
            return []
        return [
            SimpleNamespace(
                date="2026-10-11 19:00:00",
                open=84000,
                high=84100,
                low=83900,
                close=84050,
                volume=1.25,
                average=84025,
                barCount=8,
            )
        ]

    def disconnect(self):
        self.disconnected = True


class FakePersistentSessionIB:
    def __init__(self, *, fail_clock: bool = False):
        self.connected = False
        self.disconnected = False
        self.connect_calls = 0
        self.clock_calls = 0
        self.fail_clock = fail_clock

    def connect(self, host, port, *, clientId, timeout):
        self.connect_calls += 1
        self.connected = True

    def isConnected(self):
        return self.connected

    def managedAccounts(self):
        return ["DU1234567"]

    def reqCurrentTime(self):
        self.clock_calls += 1
        if self.fail_clock:
            raise TimeoutError("simulated transport timeout")
        return datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)

    def disconnect(self):
        self.disconnected = True
        self.connected = False


def test_persistent_research_session_reuses_one_authenticated_connection():
    subject = IBKRResearchToolbox(
        expected_account_hash=expected_identity_hash("DU1234567"),
        persistent_session=True,
    )
    created = []

    def factory():
        session = FakePersistentSessionIB()
        created.append(session)
        return session

    subject._new_ib = factory

    assert subject.broker_server_time_utc() == "2026-10-15T18:00:00Z"
    assert subject.broker_server_time_utc() == "2026-10-15T18:00:00Z"

    assert len(created) == 1
    assert created[0].connect_calls == 1
    assert created[0].clock_calls == 2
    assert created[0].disconnected is False


def test_persistent_research_session_reconnects_after_transport_timeout():
    subject = IBKRResearchToolbox(
        expected_account_hash=expected_identity_hash("DU1234567"),
        persistent_session=True,
    )
    created = []

    def factory():
        session = FakePersistentSessionIB(fail_clock=not created)
        created.append(session)
        return session

    subject._new_ib = factory

    with pytest.raises(TimeoutError, match="simulated transport timeout"):
        subject.broker_server_time_utc()

    assert created[0].disconnected is True
    assert subject.broker_server_time_utc() == "2026-10-15T18:00:00Z"
    assert len(created) == 2
    assert created[1].disconnected is False


def test_explicit_writer_client_bypasses_persistent_research_session():
    subject = IBKRResearchToolbox(
        expected_account_hash=expected_identity_hash("DU1234567"),
        persistent_session=True,
    )
    created = []

    def factory():
        session = FakePersistentSessionIB()
        created.append(session)
        return session

    subject._new_ib = factory

    research = subject._connect()
    research.disconnect()
    writer = subject._connect(client_id=19761)
    writer.disconnect()

    assert len(created) == 2
    assert created[0].disconnected is False
    assert created[1].disconnected is True


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


def test_account_reconciliation_snapshot_reads_raw_usd_cash_without_fx_translation():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake = FakeAccountSummaryIB()
    subject._connect = lambda: fake

    snapshot = subject.account_reconciliation_snapshot()

    assert snapshot["paper_only"] is True
    assert snapshot["account_identity_sha256"] == "a" * 64
    assert snapshot["currency_balances"] == [
        {"currency": "USD", "amount": "1000500.31"},
    ]
    assert snapshot["cash_balance_basis"] == "IBKR_LEDGER_CASH_BALANCE_USD_V1"
    assert len(snapshot["broker_snapshot_sha256"]) == 64
    assert fake.disconnected is True


def test_account_reconciliation_snapshot_resynchronizes_missing_ledger_cash_once():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)

    class DelayedLedgerIB(FakeAccountSummaryIB):
        def __init__(self):
            super().__init__()
            self.refresh_calls = []

        def accountValues(self):
            if not self.refresh_calls:
                return [
                    SimpleNamespace(
                        tag="TotalCashValue", currency="USD", value="1000000"
                    )
                ]
            return super().accountValues()

        def managedAccounts(self):
            return ["DU1234567"]

        def reqAccountUpdates(self, account):
            self.refresh_calls.append(account)

    fake = DelayedLedgerIB()
    subject._connect = lambda: fake

    snapshot = subject.account_reconciliation_snapshot()

    assert snapshot["currency_balances"] == [
        {"currency": "USD", "amount": "1000500.31"},
    ]
    assert fake.refresh_calls == ["DU1234567"]
    assert fake.disconnected is True


def test_account_reconciliation_snapshot_reuses_authenticated_broker_time():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake = FakeAccountSummaryIB()
    fake.reqCurrentTime = lambda: pytest.fail(
        "cash reconciliation must not request a second broker clock"
    )
    subject._connect = lambda: fake

    snapshot = subject.account_reconciliation_snapshot(
        observed_at_utc="2026-10-16T04:28:12Z"
    )

    assert snapshot["observed_at_utc"] == "2026-10-16T04:28:12Z"
    assert snapshot["currency_balances"] == [
        {"currency": "USD", "amount": "1000500.31"},
    ]
    assert fake.disconnected is True


def test_account_state_does_not_request_slow_account_summary():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake = FakeAccountSummaryIB()
    subject._connect = lambda: fake

    result = subject._account_state({})

    assert result["success"] is True
    assert result["server_time_utc"] == "2026-10-09T18:00:00Z"
    assert fake.disconnected is True


def test_account_reconciliation_snapshot_requires_raw_usd_cash():
    subject = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake = FakeAccountSummaryIB()
    fake.accountValues = lambda: [
        SimpleNamespace(tag="TotalCashValue", currency="USD", value="1000000"),
    ]
    subject._connect = lambda: fake

    with pytest.raises(ValueError, match="BROKER_RAW_USD_CASH_BALANCE_REQUIRED"):
        subject.account_reconciliation_snapshot()

    assert fake.disconnected is True


def test_host_clock_query_does_not_request_account_summary():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    fake = FakeAccountSummaryIB()
    fake.accountSummary = lambda: pytest.fail("clock query must not fetch account balances")
    subject._connect = lambda: fake
    assert subject.broker_server_time_utc() == "2026-10-09T18:00:00Z"
    assert fake.disconnected


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


def test_contract_builder_accepts_model_security_type_alias():
    subject = IBKRResearchToolbox(expected_account_hash="unused")

    contract = subject._contract_from_spec(
        {
            "symbol": "BTC",
            "security_type": "CRYPTO",
            "exchange": "PAXOS",
            "currency": "USD",
        }
    )

    assert contract.symbol == "BTC"
    assert contract.secType == "CRYPTO"
    assert contract.exchange == "PAXOS"
    assert contract.currency == "USD"


@pytest.mark.parametrize("key", ["conId", "con_id", "contract_id"])
def test_contract_id_only_does_not_invent_stock_routing(key):
    contract = IBKRResearchToolbox._contract_from_spec({key: 495759171})
    assert contract.conId == 495759171
    assert contract.secType == ""
    assert contract.exchange == ""
    assert contract.currency == ""


def test_contract_id_preserves_explicit_crypto_routing():
    contract = IBKRResearchToolbox._contract_from_spec(
        {"contract_id": 495759171, "sec_type": "CRYPTO", "exchange": "PAXOS", "currency": "USD"}
    )
    assert (contract.secType, contract.exchange, contract.currency) == ("CRYPTO", "PAXOS", "USD")


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


def test_crypto_historical_trades_is_normalized_to_aggregate_trades():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    fake = FakeHistoricalIB()
    subject._connect = lambda: fake

    result = subject._historical_bars(
        {
            "symbol": "BTC",
            "security_type": "CRYPTO",
            "exchange": "PAXOS",
            "currency": "USD",
            "duration": "1 D",
            "bar_size": "5 mins",
            "what_to_show": "TRADES",
            "use_rth": False,
        }
    )

    assert result["success"] is True
    assert result["whatToShow"] == "AGGTRADES"
    assert len(result["bars"]) == 1
    assert [item[1]["whatToShow"] for item in fake.requests] == ["AGGTRADES"]
    assert fake.disconnected is True


def test_empty_historical_response_is_explicitly_unavailable():
    subject = IBKRResearchToolbox(expected_account_hash="unused")
    fake = FakeHistoricalIB()
    fake.reqHistoricalData = lambda contract, **kwargs: []
    subject._connect = lambda: fake

    result = subject._historical_bars(
        {
            "symbol": "MES",
            "security_type": "FUT",
            "exchange": "CME",
            "currency": "USD",
            "expiry": "202612",
            "what_to_show": "TRADES",
        }
    )

    assert result["success"] is False
    assert result["error"] == "HISTORICAL_BARS_EMPTY"
    assert result["error_code"] == "HISTORICAL_BARS_EMPTY"
    assert result["bars"] == []
    assert fake.disconnected is True


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


def test_position_execution_contract_qualifies_crypto_when_venue_is_omitted():
    contract = SimpleNamespace(
        conId=766137558,
        symbol="SOL",
        localSymbol="SOL.USD",
        secType="CRYPTO",
        exchange="",
        primaryExchange="",
        currency="USD",
    )
    observed = {}
    resolved = SimpleNamespace(
        conId=766137558,
        symbol="SOL",
        localSymbol="SOL.USD",
        secType="CRYPTO",
        exchange="PAXOS",
        primaryExchange="",
        currency="USD",
    )

    def qualify(probe):
        observed.update(vars(probe))
        return [resolved]

    actual = resolve_position_execution_contract(
        SimpleNamespace(qualifyContracts=qualify), contract
    )

    assert observed["conId"] == 766137558
    assert not observed.get("symbol")
    assert not observed.get("secType")
    assert not observed.get("exchange")
    assert actual is resolved


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
