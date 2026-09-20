from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.market_observation import MarketSession
from ibkr_paper_30d.market_observation_collector import (
    _IBKRMarketDataClient,
    MarketObservationCollector,
    ObservationAborted,
    ObservationConfig,
    ObservationPrerequisites,
    RawQuote,
)


NOW = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, identities: list[str], quotes: dict[str, RawQuote]):
        self.identities = identities
        self.quotes = quotes
        self.index = 0
        self.started = False
        self.stopped = False

    def start(self, symbols: tuple[str, ...]) -> None:
        self.started = True

    def identity_receipt_sha256(self) -> str:
        value = self.identities[min(self.index, len(self.identities) - 1)]
        self.index += 1
        return value

    def heartbeat_ok(self) -> bool:
        return True

    def source_health(self) -> str:
        return "HEALTHY"

    def snapshot(self, symbol: str) -> RawQuote:
        return self.quotes[symbol]

    def stop(self) -> None:
        self.stopped = True


def quote(symbol: str, **updates: object) -> RawQuote:
    values: dict[str, object] = {
        "symbol": symbol,
        "contract_id": {"SPY": 1, "QQQ": 2, "IEF": 3}[symbol],
        "liquid_hours": "20260921:0930-20260921:1600",
        "timezone_id": "US/Eastern",
        "realtime_or_delayed": "REALTIME",
        "entitlement_state": "AVAILABLE",
        "bid": Decimal("500.00"),
        "ask": Decimal("500.02"),
        "last": Decimal("500.01"),
        "bid_size": Decimal("100"),
        "ask_size": Decimal("120"),
        "last_size": Decimal("10"),
        "broker_quote_timestamp": NOW - timedelta(milliseconds=200),
        "local_receipt_timestamp": NOW,
        "monotonic_receipt_ns": 1,
        "clock_skew_ms": 0,
        "round_trip_ms": 20,
        "source_health": "HEALTHY",
    }
    values.update(updates)
    return RawQuote(**values)


def prerequisites() -> ObservationPrerequisites:
    return ObservationPrerequisites(
        identity_receipt_sha256="a" * 64,
        reconciliation_receipt_sha256="b" * 64,
        paper_identity_proven=True,
        broker_reconciliation_gate="PASS",
    )


def config() -> ObservationConfig:
    return ObservationConfig(
        symbols=("SPY", "QQQ", "IEF"),
        cadence_seconds=1,
        window_seconds=1,
    )


def test_collector_rejects_identity_change_mid_window() -> None:
    source = FakeSource(
        ["a" * 64, "c" * 64],
        {symbol: quote(symbol) for symbol in config().symbols},
    )
    times = iter((NOW, NOW + timedelta(seconds=1)))
    collector = MarketObservationCollector(
        source,
        now_utc=lambda: next(times),
        monotonic_ns=lambda: 1,
        sleep=lambda _: None,
    )

    with pytest.raises(ObservationAborted, match="PAPER_IDENTITY_UNCERTAIN"):
        collector.collect_window(config(), prerequisites())

    assert source.stopped is True


def test_collector_rejects_heartbeat_loss_and_stops_source() -> None:
    source = FakeSource(
        ["a" * 64, "a" * 64],
        {symbol: quote(symbol) for symbol in config().symbols},
    )
    heartbeat_values = iter((True, False))
    source.heartbeat_ok = lambda: next(heartbeat_values)  # type: ignore[method-assign]
    collector = MarketObservationCollector(source, now_utc=lambda: NOW, sleep=lambda _: None)

    with pytest.raises(ObservationAborted, match="BROKER_HEARTBEAT_TIMEOUT"):
        collector.collect_window(config(), prerequisites())

    assert source.stopped is True


def test_collector_cleans_up_after_partial_source_start_failure() -> None:
    source = FakeSource(
        ["a" * 64],
        {symbol: quote(symbol) for symbol in config().symbols},
    )

    def fail_start(symbols: tuple[str, ...]) -> None:
        source.started = True
        raise ObservationAborted("BROKER_HANDSHAKE_TIMEOUT")

    source.start = fail_start  # type: ignore[method-assign]

    with pytest.raises(ObservationAborted, match="BROKER_HANDSHAKE_TIMEOUT"):
        MarketObservationCollector(source).collect_window(config(), prerequisites())

    assert source.stopped is True


def test_collector_builds_accepted_regular_realtime_observations() -> None:
    source = FakeSource(
        ["a" * 64, "a" * 64],
        {symbol: quote(symbol) for symbol in config().symbols},
    )
    times = iter((NOW, NOW + timedelta(seconds=1)))
    window = MarketObservationCollector(
        source,
        now_utc=lambda: next(times),
        monotonic_ns=lambda: 1,
        sleep=lambda _: None,
    ).collect_window(config(), prerequisites())

    assert window.status == "COMPLETE"
    assert len(window.observations) == 6
    assert all(item.accepted for item in window.observations)
    assert {item.market_session for item in window.observations} == {
        MarketSession.REGULAR
    }


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"realtime_or_delayed": "DELAYED"}, "DELAYED_DATA"),
        ({"broker_quote_timestamp": None}, "TIMESTAMP_PROVENANCE_UNCERTAIN"),
        ({"bid": None}, "MISSING_BID_ASK"),
        ({"bid": Decimal("501"), "ask": Decimal("500")}, "CROSSED_MARKET"),
        ({"source_health": "DEGRADED"}, "SOURCE_UNHEALTHY"),
    ],
)
def test_invalid_quotes_are_retained_as_rejected_evidence(
    updates: dict[str, object], reason: str
) -> None:
    source = FakeSource(
        ["a" * 64, "a" * 64],
        {symbol: quote(symbol, **updates) for symbol in config().symbols},
    )
    times = iter((NOW, NOW + timedelta(seconds=1)))
    window = MarketObservationCollector(
        source,
        now_utc=lambda: next(times),
        monotonic_ns=lambda: 1,
        sleep=lambda _: None,
    ).collect_window(config(), prerequisites())

    assert all(not item.accepted for item in window.observations)
    assert all(reason in item.reason_codes for item in window.observations)


def test_collector_source_exposes_no_order_write_surface() -> None:
    import ibkr_paper_30d.market_observation_collector as module

    source = inspect.getsource(module)
    forbidden = ("place" + "Order", "cancel" + "Order", "reqGlobal" + "Cancel")
    assert not any(name in source for name in forbidden)


def test_ibkr_callbacks_retain_broker_timestamp_and_local_receipt() -> None:
    client = _IBKRMarketDataClient(now_utc=lambda: NOW, monotonic_ns=lambda: 42)
    client.register_request(7100, "SPY", 1, "20260921:0930-20260921:1600", "US/Eastern")
    client.register_request(7101, "SPY", 1, "20260921:0930-20260921:1600", "US/Eastern")

    client.marketDataType(7100, 1)
    client.tickByTickBidAsk(7100, int(NOW.timestamp()), 500.0, 500.02, 100, 120, None)
    client.tickByTickAllLast(7101, 1, int(NOW.timestamp()), 500.01, 10, None, "NYSE", "")

    raw = client.raw_quote("SPY")
    assert raw.broker_quote_timestamp == NOW
    assert raw.local_receipt_timestamp == NOW
    assert raw.monotonic_receipt_ns == 42
    assert raw.realtime_or_delayed == "REALTIME"


def test_ibkr_contract_details_resolve_identity_and_session_metadata() -> None:
    client = _IBKRMarketDataClient()
    client.register_contract_request(7000, "SPY")
    details = SimpleNamespace(
        contract=SimpleNamespace(conId=756733),
        liquidHours="20260921:0930-20260921:1600",
        timeZoneId="US/Eastern",
    )

    client.contractDetails(7000, details)
    client.contractDetailsEnd(7000)

    assert client.resolved_contract(7000) == (
        "SPY",
        756733,
        "20260921:0930-20260921:1600",
        "US/Eastern",
    )


def test_broker_clock_sample_uses_round_trip_midpoint() -> None:
    times = iter((NOW, NOW + timedelta(milliseconds=200)))
    client = _IBKRMarketDataClient(now_utc=lambda: next(times))

    client.begin_clock_sample()
    client.currentTime(int(NOW.timestamp()))

    assert client.clock_sample is not None
    assert client.clock_sample.round_trip_ms == 200
    assert client.clock_sample.clock_skew_ms == 100


def test_callback_before_request_registration_is_ignored() -> None:
    client = _IBKRMarketDataClient(now_utc=lambda: NOW, monotonic_ns=lambda: 42)

    client.tickByTickBidAsk(9999, int(NOW.timestamp()), 500, 501, 1, 1, None)

    assert client.quotes == {}


@pytest.mark.parametrize("error_code", [502, 1100, 1300, 2103])
def test_disconnect_and_farm_failures_degrade_source(error_code: int) -> None:
    from ibkr_paper_30d.market_observation_collector import IBKRMarketDataSource

    source = IBKRMarketDataSource()
    source.client.error(-1, error_code, "synthetic transport failure")

    assert source.source_health() == "DEGRADED"
