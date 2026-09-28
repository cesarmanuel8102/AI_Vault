from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    ExperimentControlError,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.successor_clock import (
    BrokerTimeObservation,
    SuccessorClockError,
    SuccessorClockStore,
    clock_for_epoch,
    validate_broker_time_observation,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

UTC = timezone.utc
LEGACY_START = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
FRESH_START = datetime(2026, 9, 28, 16, 30, tzinfo=UTC)
HEAD = "a" * 40
DEFINITION = "b" * 64
AUTH_EVENT = "owner-v2-1"
AUTH_RECEIPT = "c" * 64


def _legacy_clock(db: Database) -> str:
    clock = ExperimentClockStore(db).initialize_or_load(
        requested_start_utc=LEGACY_START,
        duration_days=30,
        initial_allocation=Decimal("500"),
    )
    definition_unsigned = {
        "schema": "AUTONOMY_EXPERIMENT_EPOCH_DEFINITION_V1",
        "epoch_id": "AUTONOMY_EPOCH_1",
        "status": "PROPOSED",
        "start_utc": "2026-09-23T13:30:00Z",
        "end_utc": "2026-10-23T13:30:00Z",
        "duration_days": 30,
        "initial_allocation": "500",
        "baseline_state_event_count": 0,
        "baseline_cycle_count": 0,
        "baseline_ledger_event_count": 0,
        "previous_state_event_sha256": None,
    }
    definition = {
        **definition_unsigned,
        "definition_sha256": sha256_json(definition_unsigned),
    }
    EventRepository(db).append("EXPERIMENT_EPOCH_DEFINED", definition)
    return clock.event_sha256


def _observation(
    server_time=FRESH_START,
    *,
    observed_at=FRESH_START + timedelta(seconds=1),
    authenticated=True,
    paper_session=True,
    preceding=None,
) -> BrokerTimeObservation:
    return BrokerTimeObservation(
        server_time_utc=server_time,
        observed_at_utc=observed_at,
        authenticated=authenticated,
        paper_session=paper_session,
        preceding_server_time_utc=preceding,
    )


def _start_successor(db: Database, observation=None):
    return SuccessorClockStore(db).start(
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256=DEFINITION,
        predecessor_epoch_id="AUTONOMY_EPOCH_1",
        predecessor_clock_event_sha256=ExperimentClockStore(db).load().event_sha256,
        observation=observation or _observation(),
        duration_days=30,
        initial_allocation=Decimal("500"),
        approved_git_head=HEAD,
        owner_authorization_event_id=AUTH_EVENT,
        owner_authorization_receipt_sha256=AUTH_RECEIPT,
    )


def test_clock_for_epoch_reads_unchanged_v1_clock(tmp_path) -> None:
    with Database.open(tmp_path / "clock.sqlite3") as db:
        original_event_sha = _legacy_clock(db)
        original_row = tuple(
            db.execute("SELECT * FROM experiment_clock_events").fetchone()
        )

        clock = clock_for_epoch(db, "AUTONOMY_EPOCH_1")
        after_row = tuple(
            db.execute("SELECT * FROM experiment_clock_events").fetchone()
        )

    assert clock.epoch_id == "AUTONOMY_EPOCH_1"
    assert clock.start_utc == LEGACY_START
    assert clock.end_utc == LEGACY_START + timedelta(days=30)
    assert clock.event_sha256 == original_event_sha
    assert after_row == original_row


def test_successor_clock_uses_fresh_broker_time_for_exact_thirty_days(tmp_path) -> None:
    with Database.open(tmp_path / "clock.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)

        clock = _start_successor(db)
        loaded = clock_for_epoch(db, "AUTONOMY_EPOCH_2")

    assert clock == loaded
    assert clock.epoch_id == "AUTONOMY_EPOCH_2"
    assert clock.start_utc == FRESH_START
    assert clock.end_utc - clock.start_utc == timedelta(days=30)


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (
            _observation(server_time=FRESH_START - timedelta(seconds=31)),
            "BROKER_TIME_STALE",
        ),
        (
            _observation(server_time=FRESH_START + timedelta(seconds=7)),
            "BROKER_TIME_FUTURE_SKEW",
        ),
        (
            _observation(server_time=datetime(2026, 9, 28, 16, 30)),
            "BROKER_TIME_INVALID",
        ),
        (_observation(authenticated=False), "BROKER_SESSION_NOT_AUTHENTICATED"),
        (_observation(paper_session=False), "BROKER_SESSION_NOT_PAPER"),
    ],
)
def test_invalid_broker_time_evidence_blocks(tmp_path, observation, reason) -> None:
    with Database.open(tmp_path / f"{reason}.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)

        with pytest.raises(SuccessorClockError, match=reason):
            validate_broker_time_observation(db, observation, require_prior=True)


def test_forged_caller_preceding_time_cannot_bypass_backward_check(tmp_path) -> None:
    with Database.open(tmp_path / "forged.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)
        forged = _observation(
            server_time=LEGACY_START - timedelta(seconds=3),
            observed_at=LEGACY_START - timedelta(seconds=2),
            preceding=LEGACY_START - timedelta(days=100),
        )

        with pytest.raises(SuccessorClockError, match="BROKER_TIME_MOVED_BACKWARD"):
            validate_broker_time_observation(db, forged, require_prior=True)


def test_missing_authoritative_prior_time_fails_closed_when_required(tmp_path) -> None:
    with Database.open(tmp_path / "missing-prior.sqlite3") as db:
        install_successor_schema_v2(db)

        with pytest.raises(
            SuccessorClockError,
            match="AUTHORITATIVE_PRIOR_BROKER_TIME_MISSING",
        ):
            validate_broker_time_observation(db, _observation(), require_prior=True)


def test_valid_hash_verified_prior_time_is_used(tmp_path) -> None:
    with Database.open(tmp_path / "valid-prior.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)

        value = validate_broker_time_observation(
            db,
            _observation(preceding=FRESH_START + timedelta(days=5)),
            require_prior=True,
        )

    assert value == FRESH_START


def test_clock_validation_and_non_launch_operations_create_no_clock(tmp_path) -> None:
    with Database.open(tmp_path / "read-only.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)
        before = db.execute(
            "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
        ).fetchone()[0]

        for _ in range(3):
            validate_broker_time_observation(db, _observation(), require_prior=True)
            clock_for_epoch(db, "AUTONOMY_EPOCH_1")

        after = db.execute(
            "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
        ).fetchone()[0]

    assert before == after == 0


def test_legacy_load_fails_closed_after_successor_clock_exists(tmp_path) -> None:
    with Database.open(tmp_path / "ambiguous.sqlite3") as db:
        _legacy_clock(db)
        install_successor_schema_v2(db)
        _start_successor(db)

        with pytest.raises(
            ExperimentControlError,
            match="EXPERIMENT_CLOCK_EPOCH_REQUIRED",
        ):
            ExperimentClockStore(db).load()
