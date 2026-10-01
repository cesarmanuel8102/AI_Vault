from __future__ import annotations

import sqlite3

import pytest

from ibkr_paper_30d.continuity_schema import (
    CONTINUITY_TABLES,
    ContinuitySchemaError,
    install_continuity_schema_v3,
    verify_continuity_schema_v3,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _base_tables(db: Database) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def test_database_open_does_not_implicitly_install_continuity_schema_v3(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        assert CONTINUITY_TABLES.isdisjoint(_base_tables(db))
        assert db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=3"
        ).fetchone()[0] == 0


def test_install_requires_successor_schema_v2(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        with pytest.raises(ContinuitySchemaError, match="V2_REQUIRED"):
            install_continuity_schema_v3(db)


def test_install_creates_exact_v3_tables_indexes_and_immutable_triggers(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        receipt = install_continuity_schema_v3(db)
        verification = verify_continuity_schema_v3(db)

        assert receipt == {
            "schema": "CONTINUITY_SCHEMA_V3_INSTALLATION_V1",
            "status": "PASS",
            "installed": True,
        }
        assert verification["status"] == "PASS"
        assert verification["schema_version"] == 3
        assert CONTINUITY_TABLES <= _base_tables(db)
        for table in CONTINUITY_TABLES:
            triggers = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                    (table,),
                )
            }
            assert triggers == {f"{table}_no_update", f"{table}_no_delete"}
            assert all(name.endswith(("_no_update", "_no_delete")) for name in triggers)


def test_install_is_idempotent(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        assert install_continuity_schema_v3(db)["installed"] is True
        assert install_continuity_schema_v3(db)["installed"] is False
        assert db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=3"
        ).fetchone()[0] == 1


def test_continuity_rows_reject_update_and_delete(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        db.execute(
            "INSERT INTO continuity_watchdog_events("
            "event_id,order_ref,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?)",
            ("e1", "order-1", "OBSERVED", "{}", "a", None, "b", "2026-10-01T00:00:00Z"),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE continuity_watchdog_events SET event_type='X' WHERE event_id='e1'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM continuity_watchdog_events WHERE event_id='e1'")


def test_partial_or_malformed_v3_schema_blocks(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        db.execute("CREATE TABLE continuity_plan_events(sequence INTEGER PRIMARY KEY)")
        with pytest.raises(ContinuitySchemaError, match="V3_INVALID"):
            install_continuity_schema_v3(db)


def test_install_changes_no_epoch_clock_authorization_order_or_ledger_rows(tmp_path) -> None:
    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        EventRepository(db).append("PREEXISTING", {"value": 1})
        tracked = (
            "state_events",
            "autonomous_ledger_events",
            "experiment_clock_events",
            "experiment_authorization_events",
            "experiment_order_registry",
            "experiment_epoch_clock_events_v2",
            "experiment_epoch_authorization_events_v2",
        )
        before = {
            table: db.execute(f"SELECT * FROM {table}").fetchall()
            for table in tracked
        }

        install_continuity_schema_v3(db)

        after = {
            table: db.execute(f"SELECT * FROM {table}").fetchall()
            for table in tracked
        }
        assert after == before
