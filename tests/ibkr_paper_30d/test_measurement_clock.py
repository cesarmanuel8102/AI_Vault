from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.experiment_control import ExperimentClock
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.experiment_epoch import EpochDefinition, ExperimentEpochStore
from ibkr_paper_30d.measurement_clock import (
    MeasurementClockError,
    MeasurementClockStore,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_clock import BrokerTimeObservation


UTC = timezone.utc
START = datetime(2026, 10, 28, 12, 30, tzinfo=UTC)
BASE_CLOCK = ExperimentClock(
    experiment_id="ibkr-paper-30d",
    epoch_id="AUTONOMY_EPOCH_2",
    start_utc=datetime(2026, 9, 28, 18, 34, 8, tzinfo=UTC),
    end_utc=datetime(2026, 10, 28, 18, 34, 8, tzinfo=UTC),
    duration_days=30,
    initial_allocation=Decimal("500"),
    event_sha256="a" * 64,
)


def _observation(at: datetime = START) -> BrokerTimeObservation:
    return BrokerTimeObservation(
        server_time_utc=at,
        observed_at_utc=at + timedelta(seconds=1),
        authenticated=True,
        paper_session=True,
    )


def test_start_creates_append_only_30_day_measurement_clock(tmp_path) -> None:
    db_path = tmp_path / "clock.sqlite3"
    with Database.open(db_path) as db:
        clock = MeasurementClockStore(db).start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        row = db.execute(
            "SELECT payload_json,payload_sha256,event_sha256 FROM state_events "
            "WHERE event_type='EXPERIMENT_MEASUREMENT_CLOCK_STARTED'"
        ).fetchone()

    assert clock.start_utc == START
    assert clock.end_utc == START + timedelta(days=30)
    assert clock.event_sha256 == BASE_CLOCK.event_sha256
    assert row is not None
    import json

    payload = json.loads(str(row[0]))
    assert sha256_json(payload) == str(row[1])
    assert payload["base_clock_event_sha256"] == BASE_CLOCK.event_sha256
    assert len(str(row[2])) == 64


def test_start_is_idempotent_but_rejects_a_second_horizon(tmp_path) -> None:
    db_path = tmp_path / "clock.sqlite3"
    with Database.open(db_path) as db:
        store = MeasurementClockStore(db)
        first = store.start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        second = store.start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        assert second == first
        with pytest.raises(MeasurementClockError, match="MEASUREMENT_CLOCK_CONFLICT"):
            store.start(
                base_clock=BASE_CLOCK,
                observation=_observation(START + timedelta(minutes=1)),
                approved_git_head="b" * 40,
                actor_sid="S-1-5-21-owner",
                owner_authorized=True,
            )


@pytest.mark.parametrize(
    ("authenticated", "paper_session", "authorized", "code"),
    [
        (False, True, True, "BROKER_SESSION_NOT_AUTHENTICATED"),
        (True, False, True, "BROKER_SESSION_NOT_PAPER"),
        (True, True, False, "MEASUREMENT_CLOCK_OWNER_AUTHORIZATION_REQUIRED"),
    ],
)
def test_start_fails_closed_without_paper_time_and_owner_authority(
    tmp_path, authenticated, paper_session, authorized, code
) -> None:
    observation = BrokerTimeObservation(
        server_time_utc=START,
        observed_at_utc=START,
        authenticated=authenticated,
        paper_session=paper_session,
    )
    with Database.open(tmp_path / "clock.sqlite3") as db:
        with pytest.raises(MeasurementClockError, match=code):
            MeasurementClockStore(db).start(
                base_clock=BASE_CLOCK,
                observation=observation,
                approved_git_head="b" * 40,
                actor_sid="S-1-5-21-owner",
                owner_authorized=authorized,
            )


def test_effective_clock_preserves_authority_hash(tmp_path) -> None:
    with Database.open(tmp_path / "clock.sqlite3") as db:
        store = MeasurementClockStore(db)
        store.start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        effective = store.effective(BASE_CLOCK)

    assert effective.start_utc == START
    assert effective.end_utc == START + timedelta(days=30)
    assert effective.event_sha256 == BASE_CLOCK.event_sha256
    assert effective.initial_allocation == Decimal("500")


def test_epoch_clock_store_returns_effective_measurement_horizon(
    tmp_path, monkeypatch
) -> None:
    with Database.open(tmp_path / "clock.sqlite3") as db:
        MeasurementClockStore(db).start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        monkeypatch.setattr(
            "ibkr_paper_30d.successor_clock.clock_for_epoch",
            lambda db, epoch_id, experiment_id: BASE_CLOCK,
        )
        effective = ExperimentClockStore(db).clock_for_epoch("AUTONOMY_EPOCH_2")

    assert effective.start_utc == START
    assert effective.end_utc == START + timedelta(days=30)
    assert effective.event_sha256 == BASE_CLOCK.event_sha256


def test_epoch_projection_reports_measurement_horizon(tmp_path, monkeypatch) -> None:
    with Database.open(tmp_path / "clock.sqlite3") as db:
        MeasurementClockStore(db).start(
            base_clock=BASE_CLOCK,
            observation=_observation(),
            approved_git_head="b" * 40,
            actor_sid="S-1-5-21-owner",
            owner_authorized=True,
        )
        epoch = EpochDefinition(
            epoch_id="AUTONOMY_EPOCH_2",
            status="ACTIVE",
            start_utc=BASE_CLOCK.start_utc,
            end_utc=BASE_CLOCK.end_utc,
            duration_days=30,
            initial_allocation=Decimal("500"),
            baseline_state_event_count=0,
            baseline_cycle_count=0,
            baseline_ledger_event_count=0,
            previous_state_event_sha256=None,
            definition_sha256="c" * 64,
            activation_receipt_sha256="d" * 64,
        )
        store = ExperimentEpochStore(db)
        monkeypatch.setattr(store, "current", lambda: epoch)
        monkeypatch.setattr(
            "ibkr_paper_30d.successor_clock.clock_for_epoch",
            lambda db, epoch_id, experiment_id: BASE_CLOCK,
        )
        projection = store.projection(START + timedelta(days=1))

    assert projection["start_utc"] == "2026-10-28T12:30:00Z"
    assert projection["end_utc"] == "2026-11-27T12:30:00Z"
    assert projection["remaining_days"] == 29
