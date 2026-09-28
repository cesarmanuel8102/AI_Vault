"""Explicit append-only schema for successor epoch authority."""

from __future__ import annotations

from typing import Any

from .persistence import Database

CLOCK_TABLE = "experiment_epoch_clock_events_v2"
AUTHORIZATION_TABLE = "experiment_epoch_authorization_events_v2"
SUCCESSOR_SCHEMA_VERSION = 2


class SuccessorSchemaError(RuntimeError):
    pass


_CLOCK_COLUMNS = (
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
)

_AUTHORIZATION_COLUMNS = (
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
)

_DDL = (
    f"""
    CREATE TABLE {CLOCK_TABLE}(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        experiment_id TEXT NOT NULL,
        epoch_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type='START'),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )
    """,
    f"""
    CREATE UNIQUE INDEX successor_clock_v2_one_start
    ON {CLOCK_TABLE}(experiment_id, epoch_id, event_type)
    """,
    f"""
    CREATE TABLE {AUTHORIZATION_TABLE}(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        experiment_id TEXT NOT NULL,
        epoch_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('AUTHORIZED','REVOKED')),
        definition_sha256 TEXT NOT NULL,
        approved_git_head TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """,
    f"""
    CREATE INDEX successor_authorization_v2_epoch
    ON {AUTHORIZATION_TABLE}(experiment_id, epoch_id, sequence)
    """,
)


def _table_names(db: Database) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(db: Database, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in db.execute(f"PRAGMA table_info({table})"))


def _named_objects(db: Database, object_type: str, table: str) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type=? AND tbl_name=?",
            (object_type, table),
        ).fetchall()
    }


def _version_count(db: Database) -> int:
    return int(
        db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=?",
            (SUCCESSOR_SCHEMA_VERSION,),
        ).fetchone()[0]
    )


def verify_successor_schema_v2(db: Database) -> dict[str, Any]:
    tables = _table_names(db)
    present = {CLOCK_TABLE, AUTHORIZATION_TABLE} & tables
    if not present and _version_count(db) == 0:
        raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_MISSING")
    if present != {CLOCK_TABLE, AUTHORIZATION_TABLE} or _version_count(db) != 1:
        raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INVALID")
    if (
        _columns(db, CLOCK_TABLE) != _CLOCK_COLUMNS
        or _columns(db, AUTHORIZATION_TABLE) != _AUTHORIZATION_COLUMNS
    ):
        raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INVALID")

    clock_indexes = _named_objects(db, "index", CLOCK_TABLE)
    authorization_indexes = _named_objects(db, "index", AUTHORIZATION_TABLE)
    if "successor_clock_v2_one_start" not in clock_indexes or (
        "successor_authorization_v2_epoch" not in authorization_indexes
    ):
        raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INVALID")
    for table in (CLOCK_TABLE, AUTHORIZATION_TABLE):
        if _named_objects(db, "trigger", table) != {
            f"{table}_no_update",
            f"{table}_no_delete",
        }:
            raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INVALID")

    return {
        "schema": "SUCCESSOR_SCHEMA_V2_VERIFICATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "schema_version": SUCCESSOR_SCHEMA_VERSION,
    }


def install_successor_schema_v2(db: Database) -> dict[str, Any]:
    try:
        integrity = [str(row[0]) for row in db.execute("PRAGMA integrity_check")]
    except Exception as exc:
        raise SuccessorSchemaError("DATABASE_INTEGRITY_BLOCK") from exc
    if integrity != ["ok"]:
        raise SuccessorSchemaError("DATABASE_INTEGRITY_BLOCK")

    tables = _table_names(db)
    present = {CLOCK_TABLE, AUTHORIZATION_TABLE} & tables
    version_count = _version_count(db)
    if present or version_count:
        if present != {CLOCK_TABLE, AUTHORIZATION_TABLE} or version_count != 1:
            raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INVALID")
        verify_successor_schema_v2(db)
        return {
            "schema": "SUCCESSOR_SCHEMA_V2_INSTALLATION_V1",
            "status": "PASS",
            "installed": False,
        }

    try:
        with db.transaction():
            for statement in _DDL:
                db.execute(statement)
            for table in (CLOCK_TABLE, AUTHORIZATION_TABLE):
                db.execute(
                    f"CREATE TRIGGER {table}_no_update "
                    f"BEFORE UPDATE ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
                )
                db.execute(
                    f"CREATE TRIGGER {table}_no_delete "
                    f"BEFORE DELETE ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
                )
            db.execute(
                "INSERT INTO schema_versions(version,applied_at_utc) "
                "VALUES(2,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            )
    except SuccessorSchemaError:
        raise
    except Exception as exc:
        raise SuccessorSchemaError("SUCCESSOR_SCHEMA_V2_INSTALL_FAILED") from exc

    verify_successor_schema_v2(db)
    return {
        "schema": "SUCCESSOR_SCHEMA_V2_INSTALLATION_V1",
        "status": "PASS",
        "installed": True,
    }
