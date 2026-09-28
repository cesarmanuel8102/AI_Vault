from __future__ import annotations

import pytest

from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import (
    SuccessorSchemaError,
    install_successor_schema_v2,
    verify_successor_schema_v2,
)

V2_TABLES = {
    "experiment_epoch_clock_events_v2",
    "experiment_epoch_authorization_events_v2",
}


def _tables(db: Database) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def test_database_open_does_not_install_successor_schema_v2(tmp_path) -> None:
    path = tmp_path / "production-shaped-v1.sqlite3"

    with Database.open(path) as db:
        versions = [
            int(row[0])
            for row in db.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            ).fetchall()
        ]
        tables = _tables(db)

    assert versions == [1]
    assert V2_TABLES.isdisjoint(tables)


def test_explicit_install_creates_verified_append_only_v2_schema(tmp_path) -> None:
    with Database.open(tmp_path / "schema-v2.sqlite3") as db:
        result = install_successor_schema_v2(db)
        verification = verify_successor_schema_v2(db)
        clock_columns = [
            str(row[1])
            for row in db.execute(
                "PRAGMA table_info(experiment_epoch_clock_events_v2)"
            ).fetchall()
        ]
        authorization_columns = [
            str(row[1])
            for row in db.execute(
                "PRAGMA table_info(experiment_epoch_authorization_events_v2)"
            ).fetchall()
        ]
        versions = [
            int(row[0])
            for row in db.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            ).fetchall()
        ]

    assert result["status"] == "PASS"
    assert result["installed"] is True
    assert verification == {
        "schema": "SUCCESSOR_SCHEMA_V2_VERIFICATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "schema_version": 2,
    }
    assert clock_columns == [
        "sequence",
        "event_id",
        "experiment_id",
        "epoch_id",
        "event_type",
        "payload_json",
        "payload_sha256",
        "previous_event_sha256",
        "event_sha256",
        "created_at_utc",
    ]
    assert authorization_columns == [
        "sequence",
        "event_id",
        "experiment_id",
        "epoch_id",
        "state",
        "definition_sha256",
        "approved_git_head",
        "payload_json",
        "payload_sha256",
        "created_at_utc",
    ]
    assert versions == [1, 2]


@pytest.mark.parametrize("table", sorted(V2_TABLES))
def test_v2_tables_have_immutable_update_and_delete_triggers(
    tmp_path, table: str
) -> None:
    with Database.open(tmp_path / f"{table}.sqlite3") as db:
        install_successor_schema_v2(db)
        triggers = {
            str(row[0])
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                (table,),
            ).fetchall()
        }

    assert triggers == {f"{table}_no_update", f"{table}_no_delete"}


def test_repeated_install_is_idempotent_and_creates_no_control_state(tmp_path) -> None:
    with Database.open(tmp_path / "idempotent.sqlite3") as db:
        first = install_successor_schema_v2(db)
        before = {
            "state": db.execute("SELECT COUNT(*) FROM state_events").fetchone()[0],
            "clock": db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0],
            "authorization": db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_authorization_events_v2"
            ).fetchone()[0],
        }

        second = install_successor_schema_v2(db)
        after = {
            "state": db.execute("SELECT COUNT(*) FROM state_events").fetchone()[0],
            "clock": db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0],
            "authorization": db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_authorization_events_v2"
            ).fetchone()[0],
        }
        version_count = db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=2"
        ).fetchone()[0]

    assert first["installed"] is True
    assert second["installed"] is False
    assert before == after == {"state": 0, "clock": 0, "authorization": 0}
    assert version_count == 1


def test_install_blocks_when_integrity_check_fails(tmp_path, monkeypatch) -> None:
    with Database.open(tmp_path / "integrity.sqlite3") as db:
        original_execute = db.execute

        def execute(sql, parameters=()):
            if sql == "PRAGMA integrity_check":

                class Result:
                    @staticmethod
                    def fetchall():
                        return [("database disk image is malformed",)]

                return Result()
            return original_execute(sql, parameters)

        monkeypatch.setattr(db, "execute", execute)

        with pytest.raises(SuccessorSchemaError, match="DATABASE_INTEGRITY_BLOCK"):
            install_successor_schema_v2(db)

        assert V2_TABLES.isdisjoint(_tables(db))


def test_install_rejects_partial_or_conflicting_v2_schema(tmp_path) -> None:
    with Database.open(tmp_path / "partial.sqlite3") as db:
        db.execute("CREATE TABLE experiment_epoch_clock_events_v2(sequence INTEGER)")

        with pytest.raises(SuccessorSchemaError, match="SUCCESSOR_SCHEMA_V2_INVALID"):
            install_successor_schema_v2(db)

        assert (
            db.execute(
                "SELECT COUNT(*) FROM schema_versions WHERE version=2"
            ).fetchone()[0]
            == 0
        )


def test_verify_is_read_only_and_blocks_missing_schema(tmp_path) -> None:
    with Database.open(tmp_path / "missing.sqlite3") as db:
        before = db.connection.total_changes
        with pytest.raises(SuccessorSchemaError, match="SUCCESSOR_SCHEMA_V2_MISSING"):
            verify_successor_schema_v2(db)
        after = db.connection.total_changes

    assert after == before
