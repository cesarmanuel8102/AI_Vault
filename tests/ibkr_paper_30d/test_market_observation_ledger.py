from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.market_observation import (
    MarketObservation,
    MarketSession,
    ObservationWindow,
)
from ibkr_paper_30d.market_observation_ledger import MarketObservationLedger

NOW = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)


def accepted_window(
    *, window_id: str = "window-1", offset: int = 0
) -> ObservationWindow:
    observations = tuple(
        MarketObservation(
            observation_id=f"{window_id}-obs-{sequence}",
            sequence=sequence,
            symbol=symbol,
            contract_id=sequence + 1,
            source="IBKR",
            market_session=MarketSession.REGULAR,
            realtime_or_delayed="REALTIME",
            entitlement_state="AVAILABLE",
            bid=Decimal("500.00"),
            ask=Decimal("500.02"),
            last=Decimal("500.01"),
            bid_size=Decimal("100"),
            ask_size=Decimal("120"),
            last_size=Decimal("10"),
            broker_quote_timestamp=NOW + timedelta(minutes=offset),
            local_receipt_timestamp=NOW + timedelta(minutes=offset, milliseconds=100),
            monotonic_receipt_ns=sequence + 1,
            raw_quote_age_ms=100,
            corrected_quote_age_ms=100,
            clock_skew_ms=0,
            round_trip_ms=20,
            source_health="HEALTHY",
            identity_receipt_sha256="a" * 64,
            reconciliation_receipt_sha256="b" * 64,
            accepted=True,
            reason_codes=(),
        )
        for sequence, symbol in enumerate(("SPY", "QQQ", "IEF"))
    )
    started = NOW + timedelta(minutes=offset)
    return ObservationWindow(
        window_id=window_id,
        started_at_utc=started,
        ended_at_utc=started + timedelta(minutes=5),
        observations=observations,
        identity_receipt_sha256="a" * 64,
        reconciliation_receipt_sha256="b" * 64,
        status="COMPLETE",
    )


def read_records(path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_ledger_appends_canonical_hash_chained_records(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")

    first = ledger.append_window(accepted_window())
    second = ledger.append_window(accepted_window(window_id="window-2", offset=35))

    records = read_records(ledger.path)
    assert first.durable is True
    assert second.first_sequence == 3
    assert [record["ledger_sequence"] for record in records] == list(range(6))
    assert records[0]["previous_record_sha256"] is None
    assert records[3]["previous_record_sha256"] == records[2]["record_sha256"]
    assert ledger.path.read_bytes().splitlines()[0] == canonical_bytes(records[0])
    assert ledger.verify().status == "VALID"


def test_ledger_hash_chain_detects_changed_record(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window())
    records = read_records(ledger.path)
    records[0]["symbol"] = "CHANGED"
    ledger.path.write_bytes(
        b"\n".join(canonical_bytes(item) for item in records) + b"\n"
    )

    assert ledger.verify().status == "HASH_MISMATCH"


def test_window_digest_detects_tamper_after_chain_is_recomputed(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window())
    records = read_records(ledger.path)
    records[0]["symbol"] = "CHANGED"
    previous = None
    for record in records:
        record["previous_record_sha256"] = previous
        unsigned = dict(record)
        unsigned.pop("record_sha256")
        previous = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        record["record_sha256"] = previous
    ledger.path.write_bytes(
        b"\n".join(canonical_bytes(item) for item in records) + b"\n"
    )

    assert ledger.verify().status == "WINDOW_HASH_MISMATCH"


@pytest.mark.parametrize(
    "metadata",
    [
        {"account_id": "forbidden"},
        {"nested": {"smtp_password": "forbidden"}},
        {"note": "paper account DU123456"},
    ],
)
def test_ledger_rejects_account_identity_and_secret_keys(tmp_path, metadata) -> None:
    contaminated = accepted_window().model_copy(update={"metadata": metadata})

    with pytest.raises(ValueError, match="FORBIDDEN_EVIDENCE_KEY"):
        MarketObservationLedger(tmp_path / "observations.jsonl").append_window(
            contaminated
        )


def test_existing_window_sequence_cannot_be_replaced(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    window = accepted_window()
    ledger.append_window(window)

    with pytest.raises(ValueError, match="SEQUENCE_NOT_MONOTONIC"):
        ledger.append_window(window)


def test_duplicate_observation_sequence_is_rejected(tmp_path) -> None:
    window = accepted_window()
    duplicate = window.model_copy(
        update={
            "observations": (
                window.observations[0],
                window.observations[1].model_copy(update={"sequence": 0}),
            )
        }
    )

    with pytest.raises(ValueError, match="SEQUENCE_NOT_MONOTONIC"):
        MarketObservationLedger(tmp_path / "observations.jsonl").append_window(
            duplicate
        )


def test_truncated_tail_is_reported_and_blocks_append(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window())
    ledger.path.write_bytes(ledger.path.read_bytes()[:-5])

    assert ledger.verify().status == "TRUNCATED_RECORD"
    with pytest.raises(ValueError, match="LEDGER_INTEGRITY_FAILURE"):
        ledger.append_window(accepted_window(window_id="window-2", offset=35))


def test_existing_writer_lock_rejects_concurrent_append(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.lock_path.touch()

    with pytest.raises(RuntimeError, match="LEDGER_BUSY"):
        ledger.append_window(accepted_window())


def test_parent_traversal_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="PATH_TRAVERSAL"):
        MarketObservationLedger(tmp_path / "child" / ".." / "observations.jsonl")


def test_reordered_records_break_sequence_verification(tmp_path) -> None:
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window())
    records = read_records(ledger.path)
    records[0], records[1] = records[1], records[0]
    ledger.path.write_bytes(
        b"\n".join(canonical_bytes(item) for item in records) + b"\n"
    )

    assert ledger.verify().status in {"SEQUENCE_NOT_MONOTONIC", "HASH_MISMATCH"}
