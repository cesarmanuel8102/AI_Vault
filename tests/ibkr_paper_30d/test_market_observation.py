from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.market_observation import (
    ClockSample,
    MarketObservation,
    MarketSession,
    classify_session,
    corrected_quote_age_ms,
)


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def observation(**updates: object) -> MarketObservation:
    values: dict[str, object] = {
        "observation_id": "obs-001",
        "sequence": 1,
        "symbol": "SPY",
        "contract_id": 756733,
        "source": "IBKR",
        "market_session": MarketSession.REGULAR,
        "realtime_or_delayed": "REALTIME",
        "entitlement_state": "AVAILABLE",
        "bid": Decimal("500.00"),
        "ask": Decimal("500.02"),
        "last": Decimal("500.01"),
        "bid_size": Decimal("100"),
        "ask_size": Decimal("120"),
        "last_size": Decimal("10"),
        "broker_quote_timestamp": utc(2026, 9, 21, 14, 0),
        "local_receipt_timestamp": utc(2026, 9, 21, 14, 0),
        "monotonic_receipt_ns": 123,
        "raw_quote_age_ms": 0,
        "corrected_quote_age_ms": 0,
        "clock_skew_ms": 0,
        "round_trip_ms": 20,
        "source_health": "HEALTHY",
        "identity_receipt_sha256": "a" * 64,
        "reconciliation_receipt_sha256": "b" * 64,
        "accepted": True,
        "reason_codes": (),
        "metadata": {},
    }
    values.update(updates)
    return MarketObservation(**values)


def test_sunday_and_missing_hours_are_not_regular() -> None:
    sunday = utc(2026, 9, 20, 14)

    assert (
        classify_session(sunday, "20260920:CLOSED", "US/Eastern")
        is MarketSession.CLOSED
    )
    assert classify_session(sunday, "", "US/Eastern") is MarketSession.UNKNOWN


def test_regular_premarket_and_after_hours_follow_broker_liquid_hours() -> None:
    hours = "20260921:0930-20260921:1600"

    assert classify_session(utc(2026, 9, 21, 13), hours, "US/Eastern") is MarketSession.PREMARKET
    assert classify_session(utc(2026, 9, 21, 15), hours, "US/Eastern") is MarketSession.REGULAR
    assert classify_session(utc(2026, 9, 21, 21), hours, "US/Eastern") is MarketSession.AFTER_HOURS


def test_early_close_contract_hours_are_honored() -> None:
    hours = "20261127:0930-20261127:1300"

    assert classify_session(utc(2026, 11, 27, 18, 30), hours, "US/Eastern") is MarketSession.AFTER_HOURS


def test_malformed_stale_or_unknown_timezone_hours_fail_closed() -> None:
    now = utc(2026, 9, 21, 15)

    assert classify_session(now, "bad", "US/Eastern") is MarketSession.UNKNOWN
    assert classify_session(now, "20260918:0930-20260918:1600", "US/Eastern") is MarketSession.UNKNOWN
    assert classify_session(now, "20260921:0930-20260921:1600", "Mars/Olympus") is MarketSession.UNKNOWN


def test_clock_corrected_age_uses_midpoint_skew() -> None:
    local_send = utc(2026, 9, 21, 14)
    local_receive = local_send + timedelta(milliseconds=100)
    broker_time = local_send - timedelta(milliseconds=150)
    sample = ClockSample.from_round_trip(local_send, broker_time, local_receive)
    quote_time = broker_time - timedelta(milliseconds=500)

    assert sample.round_trip_ms == 100
    assert sample.clock_skew_ms == 200
    assert corrected_quote_age_ms(quote_time, local_receive, sample) == 550


def test_negative_corrected_age_beyond_uncertainty_is_rejected() -> None:
    base = utc(2026, 9, 21, 14)
    sample = ClockSample.from_round_trip(base, base, base + timedelta(milliseconds=20))

    assert corrected_quote_age_ms(base + timedelta(seconds=1), base, sample) is None


def test_observation_rejects_naive_datetime_and_nonfinite_price() -> None:
    with pytest.raises(ValidationError):
        observation(local_receipt_timestamp=datetime(2026, 9, 21, 14))
    with pytest.raises(ValidationError):
        observation(bid=Decimal("NaN"))


@pytest.mark.parametrize(
    "metadata",
    [
        {"account_id": "forbidden"},
        {"nested": {"smtp_password": "forbidden"}},
        {"note": "DU123456"},
    ],
)
def test_observation_rejects_account_or_secret_metadata(metadata: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        observation(metadata=metadata)
