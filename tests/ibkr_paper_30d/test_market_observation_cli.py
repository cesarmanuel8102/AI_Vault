from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.cli import (
    freeze_market_policy,
    observe_market_data,
    validate_market_observation,
)
from ibkr_paper_30d.market_data import MarketDataPolicy, QuoteSnapshot
from ibkr_paper_30d.market_observation import (
    MarketObservation,
    MarketSession,
    ObservationWindow,
)
from ibkr_paper_30d.market_observation_collector import RawQuote
from ibkr_paper_30d.market_observation_ledger import MarketObservationLedger


NOW = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stopped = False

    def start(self, symbols) -> None:
        self.start_calls += 1

    def identity_receipt_sha256(self) -> str:
        return "a" * 64

    def heartbeat_ok(self) -> bool:
        return True

    def source_health(self) -> str:
        return "HEALTHY"

    def snapshot(self, symbol: str) -> RawQuote:
        return RawQuote(
            symbol=symbol,
            contract_id={"SPY": 1, "QQQ": 2, "IEF": 3}[symbol],
            liquid_hours="20260921:0930-20260921:1600",
            timezone_id="US/Eastern",
            realtime_or_delayed="REALTIME",
            entitlement_state="AVAILABLE",
            bid=Decimal("500"),
            ask=Decimal("501"),
            broker_quote_timestamp=NOW - timedelta(milliseconds=100),
            local_receipt_timestamp=NOW,
            monotonic_receipt_ns=1,
            clock_skew_ms=0,
            round_trip_ms=20,
            source_health="HEALTHY",
        )

    def stop(self) -> None:
        self.stopped = True


def passing_readonly_report() -> dict[str, object]:
    return {
        "status": "PASS",
        "paper_account_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "heartbeat_ok": True,
    }


def policy() -> MarketDataPolicy:
    return MarketDataPolicy(
        version="MARKET_DATA_POLICY_V1",
        max_new_trade_age_ms=2_000,
        max_position_management_age_ms=5_000,
        max_clock_skew_ms=250,
    )


def quote(**updates) -> QuoteSnapshot:
    values = {
        "symbol": "SPY",
        "contract_id": 1,
        "source": "IBKR",
        "bid": Decimal("500"),
        "ask": Decimal("501"),
        "quote_timestamp": NOW - timedelta(milliseconds=100),
        "local_receipt_timestamp": NOW - timedelta(milliseconds=90),
        "market_session": "REGULAR",
        "realtime_or_delayed": "REALTIME",
        "data_entitlement_status": "AVAILABLE",
        "declared_quote_age_ms": 100,
        "source_health": "HEALTHY",
    }
    values.update(updates)
    return QuoteSnapshot(**values)


def test_observe_refuses_without_identity_and_reconciliation_pass(tmp_path) -> None:
    source = FakeSource()

    report = observe_market_data(
        readonly_report={"paper_account_identity_gate": "BLOCK"},
        output_root=tmp_path,
        source=source,
    )

    assert report["status"] == "BLOCK"
    assert report["broker_calls_made"] == 0
    assert report["market_data_policy_frozen"] is False
    assert source.start_calls == 0


def test_observe_appends_sanitized_read_only_window(tmp_path) -> None:
    source = FakeSource()

    report = observe_market_data(
        readonly_report=passing_readonly_report(),
        output_root=tmp_path,
        source=source,
        expected_account_hash="a" * 64,
        cadence_seconds=5,
        window_seconds=0,
        now_utc=lambda: NOW,
    )

    assert report["status"] == "PASS"
    assert report["observation_count"] == 3
    assert report["real_order_writes_attempted"] == 0
    assert report["market_data_policy_frozen"] is False
    assert source.start_calls == 1
    assert source.stopped is True
    serialized = json.dumps(report)
    assert "DU123456" not in serialized
    assert MarketObservationLedger(tmp_path / "market_observations.jsonl").verify().valid


def test_freeze_refuses_closed_market_ledger(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "closed.jsonl")
    item = MarketObservation(
        observation_id="closed-1",
        sequence=0,
        symbol="SPY",
        contract_id=1,
        source="IBKR",
        market_session=MarketSession.CLOSED,
        realtime_or_delayed="REALTIME",
        entitlement_state="AVAILABLE",
        local_receipt_timestamp=NOW,
        monotonic_receipt_ns=1,
        source_health="HEALTHY",
        identity_receipt_sha256="a" * 64,
        reconciliation_receipt_sha256="b" * 64,
        accepted=False,
        reason_codes=("MARKET_SESSION_CLOSED",),
    )
    ledger.append_window(
        ObservationWindow(
            window_id="closed",
            started_at_utc=NOW,
            ended_at_utc=NOW + timedelta(minutes=5),
            observations=(item,),
            identity_receipt_sha256="a" * 64,
            reconciliation_receipt_sha256="b" * 64,
            status="COMPLETE",
        )
    )

    report = freeze_market_policy(ledger, tmp_path / "policy.json")

    assert report["market_data_policy_frozen"] is False
    assert report["market_data_gate"] == "BLOCK"
    assert report["real_order_writes_attempted"] == 0


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"quote_timestamp": NOW - timedelta(seconds=10), "declared_quote_age_ms": 10_000}, "STALE_QUOTE"),
        ({"realtime_or_delayed": "DELAYED"}, "DELAYED_DATA"),
        ({"bid": None}, "MISSING_BID_ASK"),
        ({"quote_timestamp": None}, "TIMESTAMP_PROVENANCE_UNCERTAIN"),
    ],
)
def test_validate_blocks_stale_delayed_missing_and_bad_provenance(updates, reason) -> None:
    report = validate_market_observation(policy(), [quote(**updates)], now=NOW)

    assert report["market_data_gate"] == "BLOCK"
    assert reason in report["reason_codes"]
    assert report["real_order_writes_attempted"] == 0


def test_validate_passes_fresh_quote_without_order_authority() -> None:
    report = validate_market_observation(policy(), [quote()], now=NOW)

    assert report["market_data_gate"] == "PASS"
    assert report["market_data_policy_frozen"] is True
    assert report["real_order_writes_attempted"] == 0
    assert report["new_order_authority"] == "FROZEN"
