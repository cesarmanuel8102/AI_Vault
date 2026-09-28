from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.experiment_epoch import (
    EpochError,
    ExperimentEpochStore,
    activation_receipt,
)
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository

START = datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc)


def _legacy_history(db: Database) -> None:
    EventRepository(db).append("LEGACY_LAUNCH_ACCEPTED", {"legacy": 1})
    AutonomousExperimentLedger(db).append("LEGACY_MARK", {"legacy": 1})
    db.execute(
        "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) "
        "VALUES('legacy-bundle','legacy-cycle','{}',?,'2026-09-20T00:00:00Z')",
        (sha256_json({}),),
    )


def _owner_authorization(db: Database, event_id: str = "owner-auth-1") -> None:
    payload = {"actor": "owner", "state": "AUTHORIZED"}
    db.execute(
        "INSERT INTO experiment_authorization_events("
        "event_id,experiment_id,state,clock_event_sha256,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?)",
        (
            event_id,
            "ibkr-paper-30d",
            "AUTHORIZED",
            "a" * 64,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            sha256_json(payload),
            "2026-09-27T00:00:00Z",
        ),
    )


def test_rebaseline_preview_is_deterministic_and_performs_zero_writes(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        before = {
            table: [
                tuple(row)
                for row in db.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
            ]
            for table in (
                "state_events",
                "autonomous_ledger_events",
                "trader_input_bundles",
            )
        }
        store = ExperimentEpochStore(db)

        first = store.preview(
            epoch_id="AUTONOMY_EPOCH_1",
            start_utc=START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        second = store.preview(
            epoch_id="AUTONOMY_EPOCH_1",
            start_utc=START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        after = {
            table: [
                tuple(row)
                for row in db.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
            ]
            for table in before
        }

    assert first == second
    assert first["status"] == "PROPOSED"
    assert first["previous_history_classification"] == "PRE_EPOCH_HISTORY"
    assert first["baseline_cycle_count"] == 1
    assert first["baseline_ledger_event_count"] == 1
    assert before == after


def test_epoch_preview_rejects_naive_start_time(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        with pytest.raises(EpochError, match="timezone-aware"):
            ExperimentEpochStore(db).preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=datetime(2026, 9, 28, 13, 30),
                duration_days=30,
                initial_allocation=Decimal("500"),
            )


def test_epoch_projection_rejects_naive_current_time(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        with pytest.raises(EpochError, match="timezone-aware"):
            ExperimentEpochStore(db).projection(datetime(2026, 9, 28, 13, 30))


def test_define_appends_epoch_event_without_rewriting_legacy_bytes(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        legacy = bytes(
            db.execute(
                "SELECT payload_json FROM state_events WHERE sequence=1"
            ).fetchone()[0],
            "utf-8",
        )
        store = ExperimentEpochStore(db)
        preview = store.preview(
            epoch_id="AUTONOMY_EPOCH_1",
            start_utc=START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )

        definition = store.define(preview)

        assert (
            bytes(
                db.execute(
                    "SELECT payload_json FROM state_events WHERE sequence=1"
                ).fetchone()[0],
                "utf-8",
            )
            == legacy
        )
        event_types = [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM state_events ORDER BY sequence"
            ).fetchall()
        ]
        assert event_types == ["LEGACY_LAUNCH_ACCEPTED", "EXPERIMENT_EPOCH_DEFINED"]
        assert definition.status == "PROPOSED"
        assert definition.definition_sha256 == preview["definition_sha256"]


def test_activation_requires_owner_receipt_bound_to_definition(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        store = ExperimentEpochStore(db)
        definition = store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=START,
                duration_days=30,
                initial_allocation=Decimal("500"),
            )
        )
        invalid = activation_receipt(
            epoch_id=definition.epoch_id,
            definition_sha256="0" * 64,
            owner_authorization_event_id="owner-auth-1",
        )

        with pytest.raises(EpochError, match="receipt definition hash"):
            store.activate(definition.epoch_id, invalid)
        assert store.current() is None


def test_activated_projection_scopes_counts_and_horizon_to_epoch(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        store = ExperimentEpochStore(db)
        definition = store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=START,
                duration_days=30,
                initial_allocation=Decimal("500"),
            )
        )
        _owner_authorization(db)
        receipt = activation_receipt(
            epoch_id=definition.epoch_id,
            definition_sha256=definition.definition_sha256,
            owner_authorization_event_id="owner-auth-1",
        )
        activated = store.activate(definition.epoch_id, receipt)
        epoch_bundle = {"epoch": 1}
        db.execute(
            "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) "
            "VALUES('epoch-bundle','epoch-cycle',?,?, '2026-09-28T14:00:00Z')",
            (
                json.dumps(epoch_bundle, sort_keys=True, separators=(",", ":")),
                sha256_json(epoch_bundle),
            ),
        )

        projection = store.projection(START + timedelta(days=2))

    assert activated.status == "ACTIVE"
    assert projection["epoch_id"] == "AUTONOMY_EPOCH_1"
    assert projection["state"] == "ACTIVE"
    assert projection["cycle_count"] == 1
    assert projection["historical_cycle_count"] == 1
    assert projection["remaining_days"] == 28.0
    assert projection["previous_history_classification"] == "PRE_EPOCH_HISTORY"


def test_without_activation_projection_truthfully_classifies_all_history(
    tmp_path,
) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        projection = ExperimentEpochStore(db).projection(START)

    assert projection["state"] == "PRE_EPOCH_HISTORY"
    assert projection["epoch_id"] is None
    assert projection["activation_required"] is True
    assert projection["historical_cycle_count"] == 1


def test_invalid_legacy_chain_is_anchored_without_rewriting_history(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        db.execute("DROP TRIGGER state_events_no_update")
        db.execute(
            "UPDATE state_events SET event_sha256=? WHERE sequence=1", ("f" * 64,)
        )
        legacy_bytes = bytes(
            db.execute(
                "SELECT payload_json FROM state_events WHERE sequence=1"
            ).fetchone()[0],
            "utf-8",
        )
        store = ExperimentEpochStore(db)

        projection = store.projection(START)
        preview = store.preview(
            epoch_id="AUTONOMY_EPOCH_1",
            start_utc=START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        definition = store.define(preview)

        assert projection["state"] == "PRE_EPOCH_HISTORY"
        assert (
            projection["previous_history_chain_status"] == "LEGACY_UNVERIFIED_ANCHORED"
        )
        assert preview["previous_history_chain_status"] == "LEGACY_UNVERIFIED_ANCHORED"
        assert len(preview["legacy_state_events_sha256"]) == 64
        assert definition.status == "PROPOSED"
        assert (
            bytes(
                db.execute(
                    "SELECT payload_json FROM state_events WHERE sequence=1"
                ).fetchone()[0],
                "utf-8",
            )
            == legacy_bytes
        )


def test_tampered_state_event_chain_blocks_epoch_projection(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        store = ExperimentEpochStore(db)
        store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=START,
                duration_days=30,
                initial_allocation=Decimal("500"),
            )
        )
        db.execute("DROP TRIGGER state_events_no_update")
        db.execute("UPDATE state_events SET payload_json='{}' WHERE sequence=1")

        with pytest.raises(EpochError, match="state event chain"):
            store.current()
