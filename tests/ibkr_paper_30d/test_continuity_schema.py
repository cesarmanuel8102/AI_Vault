from __future__ import annotations

import sqlite3

import pytest

from ibkr_paper_30d.continuity_schema import (
    CONTINUITY_TABLES,
    ContinuitySchemaError,
    _V3_TABLES,
    install_continuity_schema_v3,
    install_continuity_schema_v4,
    verify_continuity_schema_v3,
    verify_continuity_schema_v4,
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
        assert _V3_TABLES.isdisjoint(_base_tables(db))
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
        assert _V3_TABLES <= _base_tables(db)
        for table in _V3_TABLES:
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


def test_v4_installation_on_fresh_db(tmp_path) -> None:
    with Database.open(tmp_path / "fresh.sqlite3") as db:
        install_successor_schema_v2(db)
        receipt = install_continuity_schema_v4(db)
        assert receipt["installed"] is True
        verification = verify_continuity_schema_v4(db)
        assert verification["status"] == "PASS"
        assert verification["schema_version"] == 5
        assert "continuity_execution_intents" in _base_tables(db)


def test_v4_installation_is_idempotent(tmp_path) -> None:
    with Database.open(tmp_path / "idempotent.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
        receipt = install_continuity_schema_v4(db)
        assert receipt["installed"] is False
        verify_continuity_schema_v4(db)


def test_v4_migration_from_v3_preserves_data(tmp_path) -> None:
    with Database.open(tmp_path / "migrate.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        db.execute(
            "INSERT INTO continuity_plan_events(event_id,plan_id,order_ref,event_type,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES('e1','p1','o1','ACTIVATED','{}','a','','b','2026-10-01T00:00:00Z')"
        )
        rows_before = db.execute("SELECT COUNT(*) FROM continuity_plan_events").fetchone()[0]
        assert rows_before == 1

        receipt = install_continuity_schema_v4(db)
        assert receipt["installed"] is True
        verify_continuity_schema_v4(db)

        rows_after = db.execute("SELECT COUNT(*) FROM continuity_plan_events").fetchone()[0]
        assert rows_after == 1
        assert "continuity_execution_intents" in _base_tables(db)


def test_v4_rejects_corrupt_intents_table(tmp_path) -> None:
    with Database.open(tmp_path / "corrupt.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        # Manually create a malformed intents table
        db.execute(
            "CREATE TABLE continuity_execution_intents(sequence INTEGER PRIMARY KEY)"
        )
        db.execute(
            "INSERT INTO schema_versions(version,applied_at_utc) VALUES(4,'2026-10-01T00:00:00Z')"
        )
        with pytest.raises(ContinuitySchemaError, match="V4_INVALID"):
            verify_continuity_schema_v4(db)


def _autoindex_cols(db: Database, table: str) -> list[list[str]]:
    result = []
    for row in db.execute(f"PRAGMA index_list({table})"):
        idx_name = str(row[1])
        if "autoindex" in idx_name:
            cols = [str(col[2]) for col in db.execute(f"PRAGMA index_info({idx_name})")]
            result.append(cols)
    return result


def test_new_schema_allows_cross_stream_identical_payloads(tmp_path) -> None:
    """UNIQUE(order_ref, event_sha256) must allow identical payloads in different streams."""
    from ibkr_paper_30d.continuity_store import ContinuityStore

    path = tmp_path / "cross.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
        store = ContinuityStore(db)
        _, id_a = store.reserve_execution_intent(
            plan_id="plan-a", order_ref="order-1",
            evaluation_id="ea", execution_key="ka",
            command_type="MODIFY", command_sha256="c" * 64,
            payload={"identical": True},
        )
        store.transition_execution_intent(
            intent_id=id_a,
            plan_id="plan-a",
            order_ref="order-1",
            evaluation_id="ea",
            execution_key="ka",
            intent_state="SUBMISSION_ATTEMPTED",
            command_type="MODIFY",
            command_sha256="c" * 64,
            payload={"identical": True},
        )
        store.transition_execution_intent(
            intent_id=id_a,
            plan_id="plan-a",
            order_ref="order-1",
            evaluation_id="ea",
            execution_key="ka",
            intent_state="BROKER_CONFIRMED",
            command_type="MODIFY",
            command_sha256="c" * 64,
            payload={"identical": True},
        )
        _, id_b = store.reserve_execution_intent(
            plan_id="plan-b", order_ref="order-2",
            evaluation_id="eb", execution_key="kb",
            command_type="MODIFY", command_sha256="d" * 64,
            payload={"identical": True},
        )
        assert id_a is not None
        assert id_b is not None
        assert id_a != id_b


def test_old_schema_blocks_cross_stream_identical_payloads(tmp_path) -> None:
    """The old global UNIQUE(event_sha256) must block identical payloads across streams."""
    path = tmp_path / "old.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        # Create v3 tables
        install_continuity_schema_v3(db)
        # Manually create the OLD intents table with global UNIQUE(event_sha256)
        db.execute("DROP TABLE IF EXISTS continuity_execution_intents")
        db.execute(
            """CREATE TABLE continuity_execution_intents(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                intent_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                evaluation_id TEXT,
                execution_key TEXT,
                intent_state TEXT NOT NULL,
                event_type TEXT NOT NULL,
                command_type TEXT,
                command_sha256 TEXT,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL UNIQUE,
                created_at_utc TEXT NOT NULL
            )"""
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_plan ON continuity_execution_intents(plan_id,sequence)"
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_order ON continuity_execution_intents(order_ref,sequence)"
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_state ON continuity_execution_intents(intent_state,sequence)"
        )
        # Verify it has the old global unique autoindex
        autoindexes = _autoindex_cols(db, "continuity_execution_intents")
        assert any("event_sha256" in cols and "order_ref" not in cols for cols in autoindexes)
        # Insert first stream
        db.execute(
            "INSERT INTO continuity_execution_intents"
            "(event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev-1", "i-1", "p-a", "order-1", "e", "k", "INTENT_RECORDED", "INTENT_RECORDED",
             "MODIFY", "c" * 64, '{"same":true}', "ph1", None, "SAME_SHA", "2026-01-01T00:00:00Z"),
        )
        # Second stream with same event_sha256 must be blocked
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO continuity_execution_intents"
                "(event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("ev-2", "i-2", "p-b", "order-2", "e", "k", "INTENT_RECORDED", "INTENT_RECORDED",
                 "MODIFY", "c" * 64, '{"same":true}', "ph1", None, "SAME_SHA", "2026-01-01T00:00:00Z"),
            )


def test_offline_migration_preserves_hashes_and_order(tmp_path) -> None:
    """OFFLINE migration from old to new schema must preserve sequence, hashes, chains."""
    import shutil

    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    target = tmp_path / "migrated.sqlite3"

    with Database.open(source) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        # Create OLD intents table
        db.execute("DROP TABLE IF EXISTS continuity_execution_intents")
        db.execute(
            """CREATE TABLE continuity_execution_intents(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                intent_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                evaluation_id TEXT,
                execution_key TEXT,
                intent_state TEXT NOT NULL,
                event_type TEXT NOT NULL,
                command_type TEXT,
                command_sha256 TEXT,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL UNIQUE,
                created_at_utc TEXT NOT NULL
            )"""
        )
        for stmt in (
            "CREATE INDEX continuity_execution_intents_plan ON continuity_execution_intents(plan_id,sequence)",
            "CREATE INDEX continuity_execution_intents_order ON continuity_execution_intents(order_ref,sequence)",
            "CREATE INDEX continuity_execution_intents_state ON continuity_execution_intents(intent_state,sequence)",
        ):
            db.execute(stmt)
        # Insert two chains
        for order_ref in ("order-1", "order-2"):
            prev = None
            for i in range(2):
                event_sha = f"sha-{order_ref}-{i}"
                db.execute(
                    "INSERT INTO continuity_execution_intents"
                    "(event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"ev-{order_ref}-{i}", f"intent-{order_ref}", f"plan-{order_ref}",
                     order_ref, f"eval-{i}", f"key-{i}", "INTENT_RECORDED" if i == 0 else "SUBMISSION_ATTEMPTED",
                     "INTENT_RECORDED" if i == 0 else "SUBMISSION_ATTEMPTED",
                     "MODIFY", "c" * 64, f'{{"i":{i}}}', f"ph{i}", prev, event_sha,
                     "2026-01-01T00:00:00Z"),
                )
                prev = event_sha
        db.connection.commit()

    # OFFLINE migration
    shutil.copy(str(source), str(backup))
    with Database.open(backup) as db:
        db.execute("BEGIN EXCLUSIVE")
        db.execute("DROP TABLE IF EXISTS continuity_execution_intents_new")
        db.execute(
            """CREATE TABLE continuity_execution_intents_new(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                intent_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                evaluation_id TEXT,
                execution_key TEXT,
                intent_state TEXT NOT NULL,
                event_type TEXT NOT NULL,
                command_type TEXT,
                command_sha256 TEXT,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                UNIQUE(order_ref, event_sha256)
            )"""
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_new_plan ON continuity_execution_intents_new(plan_id,sequence)"
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_new_order ON continuity_execution_intents_new(order_ref,sequence)"
        )
        db.execute(
            "CREATE INDEX continuity_execution_intents_new_state ON continuity_execution_intents_new(intent_state,sequence)"
        )
        rows = list(db.execute(
            "SELECT sequence,event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc "
            "FROM continuity_execution_intents ORDER BY sequence"
        ))
        for row in rows:
            db.execute(
                "INSERT INTO continuity_execution_intents_new"
                "(sequence,event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
        old_count = db.execute("SELECT COUNT(*) FROM continuity_execution_intents").fetchone()[0]
        new_count = db.execute("SELECT COUNT(*) FROM continuity_execution_intents_new").fetchone()[0]
        assert old_count == new_count
        # Verify chain integrity per stream
        for order_ref in ("order-1", "order-2"):
            old_chain = list(db.execute(
                "SELECT sequence,previous_event_sha256,event_sha256 FROM continuity_execution_intents WHERE order_ref=? ORDER BY sequence",
                (order_ref,),
            ))
            new_chain = list(db.execute(
                "SELECT sequence,previous_event_sha256,event_sha256 FROM continuity_execution_intents_new WHERE order_ref=? ORDER BY sequence",
                (order_ref,),
            ))
            assert old_chain == new_chain
        db.execute("DROP TABLE continuity_execution_intents")
        db.execute("ALTER TABLE continuity_execution_intents_new RENAME TO continuity_execution_intents")
        db.execute(
            "CREATE TRIGGER continuity_execution_intents_no_update BEFORE UPDATE ON continuity_execution_intents "
            "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
        )
        db.execute(
            "CREATE TRIGGER continuity_execution_intents_no_delete BEFORE DELETE ON continuity_execution_intents "
            "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
        )
        db.connection.commit()

    shutil.copy(str(backup), str(target))
    with Database.open(target) as db:
        # After migration, cross-stream identical sha should succeed
        db.execute(
            "INSERT INTO continuity_execution_intents"
            "(event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev-cross-1", "i-c1", "p-c1", "order-c1", "e", "k", "INTENT_RECORDED", "INTENT_RECORDED",
             "MODIFY", "c" * 64, '{"same":true}', "ph1", None, "SAME_SHA", "2026-01-01T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO continuity_execution_intents"
            "(event_id,intent_id,plan_id,order_ref,evaluation_id,execution_key,intent_state,event_type,command_type,command_sha256,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev-cross-2", "i-c2", "p-c2", "order-c2", "e", "k", "INTENT_RECORDED", "INTENT_RECORDED",
             "MODIFY", "c" * 64, '{"same":true}', "ph1", None, "SAME_SHA", "2026-01-01T00:00:00Z"),
        )
        db.connection.commit()
