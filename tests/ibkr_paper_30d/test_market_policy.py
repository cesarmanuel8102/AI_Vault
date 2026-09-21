from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.market_data import (
    DecisionClass,
    MarketDataGate,
    MarketDataSnapshot,
    QuoteSnapshot,
)
from ibkr_paper_30d.market_observation import (
    MarketObservation,
    MarketSession,
    ObservationWindow,
)
from ibkr_paper_30d.market_observation_ledger import MarketObservationLedger
from ibkr_paper_30d.market_policy import (
    MarketPolicyFreezer,
    load_verified_policy,
)

START = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
SYMBOLS = ("SPY", "QQQ", "IEF")


def observation(
    sequence: int,
    symbol: str,
    timestamp: datetime,
    *,
    session: MarketSession = MarketSession.REGULAR,
    accepted: bool = True,
) -> MarketObservation:
    age = 100 + sequence % 50
    return MarketObservation(
        observation_id=f"obs-{timestamp.timestamp()}-{sequence}",
        sequence=sequence,
        symbol=symbol,
        contract_id=SYMBOLS.index(symbol) + 1,
        source="IBKR",
        market_session=session,
        realtime_or_delayed="REALTIME",
        entitlement_state="AVAILABLE",
        bid=Decimal("500.00"),
        ask=Decimal("500.02"),
        last=Decimal("500.01"),
        bid_size=Decimal("100"),
        ask_size=Decimal("120"),
        last_size=Decimal("10"),
        broker_quote_timestamp=timestamp - timedelta(milliseconds=age),
        local_receipt_timestamp=timestamp,
        monotonic_receipt_ns=sequence + 1,
        raw_quote_age_ms=age + 10,
        corrected_quote_age_ms=age,
        clock_skew_ms=10 + sequence % 5,
        round_trip_ms=20,
        source_health="HEALTHY",
        identity_receipt_sha256="a" * 64,
        reconciliation_receipt_sha256="b" * 64,
        accepted=accepted,
        reason_codes=() if accepted else (f"MARKET_SESSION_{session.value}",),
    )


def window(
    window_id: str,
    start: datetime,
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    points_per_symbol: int = 60,
    session: MarketSession = MarketSession.REGULAR,
    accepted: bool = True,
) -> ObservationWindow:
    items = []
    sequence = 0
    for point in range(points_per_symbol):
        timestamp = start + timedelta(seconds=point * 5)
        for symbol in symbols:
            items.append(
                observation(
                    sequence,
                    symbol,
                    timestamp,
                    session=session,
                    accepted=accepted,
                )
            )
            sequence += 1
    return ObservationWindow(
        window_id=window_id,
        started_at_utc=start,
        ended_at_utc=start + timedelta(minutes=5),
        observations=tuple(items),
        identity_receipt_sha256="a" * 64,
        reconciliation_receipt_sha256="b" * 64,
        status="COMPLETE",
    )


def build_ledger(tmp_path, *, starts=(0, 30, 65), symbols=SYMBOLS, points=60):
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    for index, offset in enumerate(starts):
        ledger.append_window(
            window(
                f"window-{index + 1}",
                START + timedelta(minutes=offset),
                symbols=symbols,
                points_per_symbol=points,
            )
        )
    return ledger


def test_weekend_evidence_cannot_freeze_policy(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    sunday = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    ledger.append_window(
        window(
            "weekend",
            sunday,
            session=MarketSession.CLOSED,
            accepted=False,
            points_per_symbol=1,
        )
    )

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert result.status == "BLOCK"
    assert "REGULAR_SESSION_EVIDENCE_REQUIRED" in result.reason_codes
    assert not (tmp_path / "policy.json").exists()


def test_three_separated_windows_and_540_records_are_required(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(window("short", START, points_per_symbol=1))

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert {"WINDOW_COUNT_INSUFFICIENT", "OBSERVATION_COUNT_INSUFFICIENT"} <= set(
        result.reason_codes
    )


def test_policy_thresholds_follow_documented_percentile_formulas(tmp_path) -> None:
    ledger = build_ledger(tmp_path)

    result = MarketPolicyFreezer(now_utc=lambda: START + timedelta(hours=8)).freeze(
        ledger, tmp_path / "policy.json"
    )

    assert result.status == "PASS"
    assert result.policy is not None
    assert result.statistics is not None
    expected = (
        math.ceil(
            (
                result.statistics.p99_quote_age_ms
                + max(250, 2 * result.statistics.quote_age_iqr_ms)
            )
            / 100
        )
        * 100
    )
    assert result.policy.max_new_trade_age_ms == expected
    assert load_verified_policy(tmp_path / "policy.json") == result.policy


def test_different_existing_v1_is_never_replaced(tmp_path) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy.json"
    destination.write_text('{"different":true}', encoding="utf-8")
    before = destination.read_bytes()

    result = MarketPolicyFreezer().freeze(ledger, destination)

    assert result.status == "VERSION_CONFLICT"
    assert destination.read_bytes() == before


def test_identical_existing_policy_is_already_frozen(tmp_path) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy.json"
    freezer = MarketPolicyFreezer(now_utc=lambda: START + timedelta(hours=8))
    first = freezer.freeze(ledger, destination)
    before = destination.read_bytes()

    second = MarketPolicyFreezer(now_utc=lambda: START + timedelta(days=1)).freeze(
        ledger, destination
    )

    assert first.status == "PASS"
    assert second.status == "ALREADY_FROZEN"
    assert destination.read_bytes() == before


def test_bad_ledger_hash_blocks_freeze(tmp_path) -> None:
    ledger = build_ledger(tmp_path)
    payload = bytearray(ledger.path.read_bytes())
    payload[payload.index(b"SPY")] = ord("X")
    ledger.path.write_bytes(payload)

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert result.status == "BLOCK"
    assert "LEDGER_INTEGRITY_FAILURE" in result.reason_codes


def test_insufficient_window_separation_blocks(tmp_path) -> None:
    ledger = build_ledger(tmp_path, starts=(0, 10, 20))

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert result.status == "BLOCK"
    assert "WINDOW_SEPARATION_INSUFFICIENT" in result.reason_codes


def test_missing_required_symbol_blocks(tmp_path) -> None:
    ledger = build_ledger(tmp_path, symbols=("SPY", "QQQ"), points=90)

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert result.status == "BLOCK"
    assert "SYMBOL_SET_INSUFFICIENT" in result.reason_codes


def test_truncated_policy_and_predecessor_mismatch_are_rejected(tmp_path) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy-v2.json"
    result = MarketPolicyFreezer().freeze(
        ledger,
        destination,
        version="MARKET_DATA_POLICY_V2",
        predecessor_sha256="c" * 64,
    )
    assert result.status == "PREDECESSOR_MISMATCH"

    truncated = tmp_path / "truncated.json"
    truncated.write_text('{"schema":"MARKET_DATA_POLICY_V1"', encoding="utf-8")
    with pytest.raises(ValueError, match="POLICY_INVALID"):
        load_verified_policy(truncated)


def test_conflicting_entitlement_blocks_freeze(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    for index, offset in enumerate((0, 30, 65)):
        evidence_window = window(
            f"window-{index + 1}",
            START + timedelta(minutes=offset),
            points_per_symbol=61,
        )
        if index == 0:
            observations = list(evidence_window.observations)
            observations[0] = observations[0].model_copy(
                update={
                    "accepted": False,
                    "entitlement_state": "UNAVAILABLE",
                    "reason_codes": ("ENTITLEMENT_UNAVAILABLE",),
                }
            )
            evidence_window = evidence_window.model_copy(
                update={"observations": tuple(observations)}
            )
        ledger.append_window(evidence_window)

    result = MarketPolicyFreezer().freeze(ledger, tmp_path / "policy.json")

    assert result.status == "BLOCK"
    assert "ENTITLEMENT_CONFLICT" in result.reason_codes


@pytest.mark.parametrize("session", ["PREMARKET", "AFTER_HOURS", "UNKNOWN"])
def test_runtime_new_trade_gate_requires_regular_session(tmp_path, session) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy.json"
    result = MarketPolicyFreezer().freeze(ledger, destination)
    assert result.policy is not None
    now = START + timedelta(hours=8)
    quote = QuoteSnapshot(
        symbol="SPY",
        contract_id=1,
        source="IBKR",
        bid=Decimal("500"),
        ask=Decimal("501"),
        quote_timestamp=now - timedelta(milliseconds=100),
        local_receipt_timestamp=now - timedelta(milliseconds=90),
        market_session=session,
        realtime_or_delayed="REALTIME",
        data_entitlement_status="AVAILABLE",
        declared_quote_age_ms=100,
        source_health="HEALTHY",
    )
    snapshot = MarketDataSnapshot.freeze([quote], created_at_utc=now)

    gate_result = MarketDataGate(result.policy).evaluate(
        snapshot, DecisionClass.NEW_TRADE, now=now
    )

    assert gate_result.status == "BLOCK"
    assert "MARKET_SESSION_NOT_REGULAR" in gate_result.reason_codes


def test_policy_frozen_with_stale_collector_version_is_rejected(tmp_path) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy.json"
    result = MarketPolicyFreezer(now_utc=lambda: START + timedelta(hours=8)).freeze(
        ledger, destination
    )
    assert result.status == "PASS"

    payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["evidence"]["collector_version"] = "STALE_COLLECTOR"
    unsigned = dict(payload)
    unsigned.pop("policy_sha256")
    payload["policy_sha256"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    destination.write_bytes(canonical_bytes(payload))

    with pytest.raises(ValueError, match="POLICY_INVALID"):
        load_verified_policy(destination)

@pytest.mark.parametrize(
    "mutation",
    ["policy_version", "controls_version"],
)
def test_verified_policy_rejects_version_incoherence(tmp_path, mutation) -> None:
    ledger = build_ledger(tmp_path)
    destination = tmp_path / "policy.json"
    result = MarketPolicyFreezer(now_utc=lambda: START + timedelta(hours=8)).freeze(
        ledger, destination
    )
    assert result.status == "PASS"

    payload = json.loads(destination.read_text(encoding="utf-8"))
    if mutation == "policy_version":
        payload["policy_version"] = "MARKET_DATA_POLICY_V2"
    else:
        payload["controls"]["version"] = "MARKET_DATA_POLICY_V2"

    unsigned = dict(payload)
    unsigned.pop("policy_sha256")
    payload["policy_sha256"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    destination.write_bytes(canonical_bytes(payload))

    with pytest.raises(ValueError, match="POLICY_INVALID"):
        load_verified_policy(destination)
