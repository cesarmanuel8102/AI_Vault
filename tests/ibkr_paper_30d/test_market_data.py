from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.market_data import (
    DecisionClass,
    MarketDataGate,
    MarketDataPolicy,
    MarketDataSnapshot,
    QuoteSnapshot,
)


NOW = datetime(2026, 9, 20, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def policy() -> MarketDataPolicy:
    return MarketDataPolicy(
        version="MD_V1_TEST",
        max_new_trade_age_ms=2_000,
        max_position_management_age_ms=5_000,
        max_clock_skew_ms=250,
    )


@pytest.fixture
def gate(policy) -> MarketDataGate:
    return MarketDataGate(policy)


@pytest.fixture
def fresh_quote() -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol="SPY",
        contract_id=756733,
        source="IBKR",
        bid=Decimal("500.00"),
        ask=Decimal("500.02"),
        last=Decimal("500.01"),
        bid_size=Decimal("100"),
        ask_size=Decimal("120"),
        last_size=Decimal("10"),
        quote_timestamp=NOW - timedelta(milliseconds=500),
        local_receipt_timestamp=NOW - timedelta(milliseconds=450),
        market_session="REGULAR",
        realtime_or_delayed="REALTIME",
        data_entitlement_status="AVAILABLE",
        declared_quote_age_ms=500,
        source_health="HEALTHY",
    )


def evaluate(gate, quote, decision_class=DecisionClass.NEW_TRADE):
    snapshot = MarketDataSnapshot.freeze([quote], created_at_utc=NOW)
    return gate.evaluate(snapshot, decision_class, now=NOW)


def test_fresh_realtime_quote_passes_and_binds_snapshot(gate, fresh_quote) -> None:
    snapshot = MarketDataSnapshot.freeze([fresh_quote], created_at_utc=NOW)

    result = gate.evaluate(snapshot, DecisionClass.NEW_TRADE, now=NOW)

    assert result.status == "PASS"
    assert result.market_data_snapshot_id == snapshot.snapshot_id
    assert result.market_data_snapshot_sha256 == snapshot.sha256
    assert result.quote_age_at_decision_ms == 500


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"realtime_or_delayed": "DELAYED"}, "DELAYED_DATA"),
        ({"bid": None}, "MISSING_BID_ASK"),
        ({"bid": Decimal("501"), "ask": Decimal("500")}, "CROSSED_MARKET"),
        ({"data_entitlement_status": "UNAVAILABLE"}, "ENTITLEMENT_UNAVAILABLE"),
        ({"source_health": "DEGRADED"}, "SOURCE_UNHEALTHY"),
        ({"market_session": "CLOSED"}, "MARKET_SESSION_CLOSED"),
    ],
)
def test_invalid_quotes_block(gate, fresh_quote, mutation, reason) -> None:
    result = evaluate(gate, fresh_quote.model_copy(update=mutation))

    assert result.status == "BLOCK"
    assert reason in result.reason_codes


def test_new_trade_and_position_management_use_distinct_freshness(
    gate, fresh_quote
) -> None:
    old = fresh_quote.model_copy(
        update={
            "quote_timestamp": NOW - timedelta(milliseconds=3_000),
            "declared_quote_age_ms": 3_000,
        }
    )

    new_trade = evaluate(gate, old, DecisionClass.NEW_TRADE)
    management = evaluate(gate, old, DecisionClass.OPEN_POSITION_MANAGEMENT)

    assert new_trade.status == "BLOCK"
    assert "STALE_QUOTE" in new_trade.reason_codes
    assert management.status == "PASS"


def test_negative_age_beyond_clock_skew_blocks(gate, fresh_quote) -> None:
    future = fresh_quote.model_copy(
        update={
            "quote_timestamp": NOW + timedelta(seconds=10),
            "declared_quote_age_ms": -10_000,
        }
    )

    result = evaluate(gate, future)

    assert result.status == "BLOCK"
    assert "CLOCK_SKEW" in result.reason_codes


def test_declared_age_timestamp_mismatch_blocks(gate, fresh_quote) -> None:
    mismatched = fresh_quote.model_copy(update={"declared_quote_age_ms": 1_500})

    result = evaluate(gate, mismatched)

    assert result.status == "BLOCK"
    assert "TIMESTAMP_MISMATCH" in result.reason_codes


def test_missing_timestamp_provenance_blocks(gate, fresh_quote) -> None:
    missing = fresh_quote.model_copy(update={"quote_timestamp": None})

    result = evaluate(gate, missing)

    assert result.status == "BLOCK"
    assert "TIMESTAMP_PROVENANCE_UNCERTAIN" in result.reason_codes


def test_non_finite_and_non_positive_prices_are_rejected(gate, fresh_quote) -> None:
    non_positive = fresh_quote.model_copy(update={"last": Decimal("0")})
    non_finite = fresh_quote.model_copy(update={"bid": Decimal("NaN")})

    assert "INVALID_PRICE" in evaluate(gate, non_positive).reason_codes
    assert "INVALID_PRICE" in evaluate(gate, non_finite).reason_codes


def test_snapshot_hash_is_deterministic_and_changes_with_quote(fresh_quote) -> None:
    first = MarketDataSnapshot.freeze([fresh_quote], created_at_utc=NOW)
    second = MarketDataSnapshot.freeze([fresh_quote], created_at_utc=NOW)
    changed = MarketDataSnapshot.freeze(
        [fresh_quote.model_copy(update={"ask": Decimal("500.03")})],
        created_at_utc=NOW,
    )

    assert first.sha256 == second.sha256
    assert first.snapshot_id == second.snapshot_id
    assert changed.sha256 != first.sha256


def test_gate_reports_oldest_and_latest_quote_timestamps(gate, fresh_quote) -> None:
    older = fresh_quote.model_copy(
        update={
            "symbol": "QQQ",
            "contract_id": 320227571,
            "quote_timestamp": NOW - timedelta(milliseconds=900),
            "local_receipt_timestamp": NOW - timedelta(milliseconds=850),
            "declared_quote_age_ms": 900,
        }
    )
    newer = fresh_quote.model_copy(
        update={
            "symbol": "IEF",
            "contract_id": 15547844,
            "quote_timestamp": NOW - timedelta(milliseconds=100),
            "local_receipt_timestamp": NOW - timedelta(milliseconds=90),
            "declared_quote_age_ms": 100,
        }
    )
    snapshot = MarketDataSnapshot.freeze(
        [fresh_quote, older, newer],
        created_at_utc=NOW,
    )

    result = gate.evaluate(snapshot, DecisionClass.NEW_TRADE, now=NOW)

    assert result.status == "PASS"
    assert result.quote_timestamp == older.quote_timestamp
    assert result.oldest_quote_timestamp == older.quote_timestamp
    assert result.latest_quote_timestamp == newer.quote_timestamp
