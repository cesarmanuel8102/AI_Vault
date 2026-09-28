from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import ibkr_paper_30d.experiment_epoch as epoch_module
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
HEAD = "a" * 40
OWNER_RECEIPT_SHA256 = "b" * 64
OBJECTIVE_SHA256 = "c" * 64
CONFIGURATION_SHA256 = "d" * 64


def _preview(store: ExperimentEpochStore, **overrides):
    values = {
        "epoch_id": "AUTONOMY_EPOCH_1",
        "start_utc": START,
        "duration_days": 30,
        "initial_allocation": Decimal("500"),
        "approved_git_head": HEAD,
        "owner_authorization_event_id": "owner-auth-1",
        "owner_authorization_receipt_sha256": OWNER_RECEIPT_SHA256,
        "objective_sha256": OBJECTIVE_SHA256,
        "configuration_sha256": CONFIGURATION_SHA256,
    }
    values.update(overrides)
    return store.preview(**values)


def _owner_receipt(event_id: str = "owner-auth-1") -> dict[str, object]:
    return {
        "schema": "DAY1_OWNER_AUTHORIZATION_V1",
        "authorization_event_id": event_id,
        "authorization_state": "AUTHORIZED",
        "actor_sid": "S-1-5-21-test",
    }


def _activate(db: Database, **overrides):
    values = {
        "epoch_id": "AUTONOMY_EPOCH_1",
        "start_utc": START,
        "duration_days": 30,
        "initial_allocation": Decimal("500"),
        "approved_git_head": HEAD,
        "observed_git_head": HEAD,
        "owner_authorization_receipt": _owner_receipt(),
        "owner_authorization_receipt_sha256": OWNER_RECEIPT_SHA256,
        "objective_sha256": OBJECTIVE_SHA256,
        "configuration_sha256": CONFIGURATION_SHA256,
        "kernel_status": "PASS",
        "runtime_provenance_status": "PASS",
        "activated_at_utc": START - timedelta(minutes=5),
    }
    values.update(overrides)
    return epoch_module.activate_epoch_transition(db, **values)


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

        first = _preview(store)
        second = _preview(store)
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
            _preview(
                ExperimentEpochStore(db),
                start_utc=datetime(2026, 9, 28, 13, 30),
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
        preview = _preview(store)

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
        definition = store.define(_preview(store))
        invalid = activation_receipt(
            epoch_id=definition.epoch_id,
            definition_sha256="0" * 64,
            owner_authorization_event_id="owner-auth-1",
            approved_git_head=HEAD,
            owner_authorization_receipt_sha256=OWNER_RECEIPT_SHA256,
        )

        with pytest.raises(EpochError, match="receipt definition hash"):
            store.activate(definition.epoch_id, invalid)
        assert store.current() is None


def test_activated_projection_scopes_counts_and_horizon_to_epoch(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        store = ExperimentEpochStore(db)
        definition = store.define(_preview(store))
        _owner_authorization(db)
        receipt = activation_receipt(
            epoch_id=definition.epoch_id,
            definition_sha256=definition.definition_sha256,
            owner_authorization_event_id="owner-auth-1",
            approved_git_head=HEAD,
            owner_authorization_receipt_sha256=OWNER_RECEIPT_SHA256,
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
        preview = _preview(store)
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
        store.define(_preview(store))
        db.execute("DROP TRIGGER state_events_no_update")
        db.execute("UPDATE state_events SET payload_json='{}' WHERE sequence=1")

        with pytest.raises(EpochError, match="state event chain"):
            store.current()


def test_activation_transition_defines_and_activates_exactly_once(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        _owner_authorization(db)
        legacy_rows = db.execute(
            "SELECT * FROM state_events ORDER BY sequence"
        ).fetchall()

        result = _activate(db)

        counts = dict(
            db.execute(
                "SELECT event_type,COUNT(*) FROM state_events "
                "WHERE event_type LIKE 'EXPERIMENT_EPOCH_%' GROUP BY event_type"
            ).fetchall()
        )
        definition = json.loads(
            db.execute(
                "SELECT payload_json FROM state_events "
                "WHERE event_type='EXPERIMENT_EPOCH_DEFINED'"
            ).fetchone()[0]
        )
        after_legacy_rows = db.execute(
            "SELECT * FROM state_events WHERE sequence<=? ORDER BY sequence",
            (len(legacy_rows),),
        ).fetchall()

    assert result["status"] == "PASS"
    assert counts == {
        "EXPERIMENT_EPOCH_ACTIVATED": 1,
        "EXPERIMENT_EPOCH_DEFINED": 1,
    }
    assert definition["approved_git_head"] == HEAD
    assert definition["previous_history_classification"] == "PRE_EPOCH_HISTORY"
    assert definition["owner_authorization_event_id"] == "owner-auth-1"
    assert definition["owner_authorization_receipt_sha256"] == OWNER_RECEIPT_SHA256
    assert definition["objective_sha256"] == OBJECTIVE_SHA256
    assert definition["configuration_sha256"] == CONFIGURATION_SHA256
    assert definition["owner_activation_required"] is True
    assert after_legacy_rows == legacy_rows
    assert result["broker_write_calls"] == 0
    assert result["day1_started"] is False


def test_exact_activation_rerun_is_idempotent(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _owner_authorization(db)
        first = _activate(db)
        rows_after_first = db.execute(
            "SELECT * FROM state_events ORDER BY sequence"
        ).fetchall()

        second = _activate(db)
        rows_after_second = db.execute(
            "SELECT * FROM state_events ORDER BY sequence"
        ).fetchall()

    assert first["status"] == "PASS"
    assert second["status"] == "VALID_ALREADY_ACTIVATED"
    assert rows_after_second == rows_after_first


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"observed_git_head": "f" * 40}, "APPROVED_HEAD_MISMATCH"),
        ({"kernel_status": "BLOCK"}, "KERNEL_BLOCK"),
        ({"runtime_provenance_status": "BLOCK"}, "RUNTIME_PROVENANCE_BLOCK"),
        (
            {"owner_authorization_receipt": _owner_receipt("missing")},
            "OWNER_AUTHORIZATION_EVENT_MISMATCH",
        ),
    ],
)
def test_activation_preconditions_fail_before_epoch_writes(
    tmp_path, overrides, reason
) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _owner_authorization(db)
        with pytest.raises(EpochError, match=reason):
            _activate(db, **overrides)
        epoch_count = db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type LIKE 'EXPERIMENT_EPOCH_%'"
        ).fetchone()[0]

    assert epoch_count == 0


def test_changed_legacy_commitment_blocks_activation(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _legacy_history(db)
        _owner_authorization(db)
        store = ExperimentEpochStore(db)
        store.define(_preview(store))
        db.execute("DROP TRIGGER state_events_no_update")
        db.execute("UPDATE state_events SET payload_json='{}' WHERE sequence=1")

        with pytest.raises(EpochError, match="pre-epoch history commitment"):
            _activate(db)
        activation_count = db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type='EXPERIMENT_EPOCH_ACTIVATED'"
        ).fetchone()[0]

    assert activation_count == 0


def test_conflicting_active_epoch_blocks_without_duplicate(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _owner_authorization(db)
        _activate(db)

        with pytest.raises(EpochError, match="CONFLICTING_EPOCH_ACTIVATION"):
            _activate(db, approved_git_head="e" * 40, observed_git_head="e" * 40)
        activation_count = db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type='EXPERIMENT_EPOCH_ACTIVATED'"
        ).fetchone()[0]

    assert activation_count == 1


def test_exact_rerun_revalidates_owner_authorization_event_hash(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _owner_authorization(db)
        _activate(db)
        db.execute("DROP TRIGGER experiment_authorization_events_no_update")
        db.execute(
            "UPDATE experiment_authorization_events SET payload_json='{}' "
            "WHERE event_id='owner-auth-1'"
        )

        with pytest.raises(EpochError, match="OWNER_AUTHORIZATION_EVENT_INVALID"):
            _activate(db)


def test_activation_rejects_invalid_database_integrity_before_writes(
    tmp_path, monkeypatch
) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        original_execute = db.execute

        def execute(sql, parameters=()):
            if sql == "PRAGMA integrity_check":

                class InvalidIntegrityResult:
                    @staticmethod
                    def fetchall():
                        return [("database disk image is malformed",)]

                return InvalidIntegrityResult()
            return original_execute(sql, parameters)

        monkeypatch.setattr(db, "execute", execute)
        with pytest.raises(EpochError, match="DATABASE_INTEGRITY_BLOCK"):
            _activate(db)

        epoch_count = original_execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type LIKE 'EXPERIMENT_EPOCH_%'"
        ).fetchone()[0]

    assert epoch_count == 0


def test_activation_event_cryptographically_binds_definition(tmp_path) -> None:
    with Database.open(tmp_path / "epoch.sqlite3") as db:
        _owner_authorization(db)
        _activate(db)
        rows = db.execute(
            "SELECT event_type,payload_json,payload_sha256 FROM state_events "
            "WHERE event_type LIKE 'EXPERIMENT_EPOCH_%' ORDER BY sequence"
        ).fetchall()

    definition = json.loads(rows[0][1])
    activation = json.loads(rows[1][1])
    assert sha256_json(definition) == rows[0][2]
    assert sha256_json(activation) == rows[1][2]
    assert activation["definition_sha256"] == definition["definition_sha256"]
    assert activation["approved_git_head"] == definition["approved_git_head"]
    assert (
        activation["owner_authorization_receipt_sha256"]
        == definition["owner_authorization_receipt_sha256"]
    )
