"""Explicit, append-only schema for model-authored continuity authority."""

from __future__ import annotations

from typing import Any

from .persistence import (
    CONTINUITY_APPEND_ONLY_TABLES,
    CONTINUITY_CANONICAL_TABLES,
    Database,
)
from .successor_schema import SuccessorSchemaError, verify_successor_schema_v2


CONTINUITY_SCHEMA_VERSION = 3
CONTINUITY_TABLES = CONTINUITY_CANONICAL_TABLES


class ContinuitySchemaError(RuntimeError):
    pass


_TABLE_COLUMNS = {
    "continuity_plan_events": (
        "sequence", "event_id", "plan_id", "order_ref", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "provider_invocation_events": (
        "sequence", "event_id", "invocation_id", "event_type", "payload_json",
        "payload_sha256", "previous_event_sha256", "event_sha256", "created_at_utc",
    ),
    "continuity_watchdog_events": (
        "sequence", "event_id", "order_ref", "event_type", "payload_json",
        "payload_sha256", "previous_event_sha256", "event_sha256", "created_at_utc",
    ),
    "continuity_evaluation_events": (
        "sequence", "event_id", "evaluation_id", "plan_id", "order_ref",
        "event_type", "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "continuity_execution_events": (
        "sequence", "event_id", "execution_id", "evaluation_id", "plan_id",
        "order_ref", "execution_ordinal", "event_type", "payload_json",
        "payload_sha256", "previous_event_sha256", "event_sha256", "created_at_utc",
    ),
    "continuity_report_events": (
        "sequence", "event_id", "report_id", "outage_id", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "continuity_review_events": (
        "sequence", "event_id", "review_id", "report_id", "report_sha256",
        "invocation_id", "event_type", "payload_json", "payload_sha256",
        "previous_event_sha256", "event_sha256", "created_at_utc",
    ),
    "continuity_reflection_events": (
        "sequence", "event_id", "reflection_id", "review_id", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
}


_DDL = (
    """CREATE TABLE continuity_plan_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        plan_id TEXT NOT NULL,
        order_ref TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('DRAFTED','ACTIVATED','SUPERSEDED','TERMINAL')),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_plan_events_plan ON continuity_plan_events(plan_id,sequence)",
    "CREATE INDEX continuity_plan_events_order ON continuity_plan_events(order_ref,sequence)",
    """CREATE TABLE provider_invocation_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        invocation_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX provider_invocation_events_invocation ON provider_invocation_events(invocation_id,sequence)",
    """CREATE TABLE continuity_watchdog_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        order_ref TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_watchdog_events_order ON continuity_watchdog_events(order_ref,sequence)",
    """CREATE TABLE continuity_evaluation_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        evaluation_id TEXT NOT NULL UNIQUE,
        plan_id TEXT NOT NULL,
        order_ref TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_evaluation_events_plan ON continuity_evaluation_events(plan_id,sequence)",
    "CREATE INDEX continuity_evaluation_events_order ON continuity_evaluation_events(order_ref,sequence)",
    """CREATE TABLE continuity_execution_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        execution_id TEXT NOT NULL UNIQUE,
        evaluation_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        order_ref TEXT NOT NULL,
        execution_ordinal INTEGER NOT NULL CHECK(execution_ordinal > 0),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL,
        UNIQUE(plan_id,order_ref,execution_ordinal)
    )""",
    "CREATE INDEX continuity_execution_events_evaluation ON continuity_execution_events(evaluation_id,sequence)",
    "CREATE INDEX continuity_execution_events_order ON continuity_execution_events(order_ref,sequence)",
    """CREATE TABLE continuity_report_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        report_id TEXT NOT NULL UNIQUE,
        outage_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_report_events_outage ON continuity_report_events(outage_id,sequence)",
    """CREATE TABLE continuity_review_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        review_id TEXT NOT NULL UNIQUE,
        report_id TEXT NOT NULL,
        report_sha256 TEXT NOT NULL,
        invocation_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_review_events_report ON continuity_review_events(report_id,sequence)",
    "CREATE INDEX continuity_review_events_invocation ON continuity_review_events(invocation_id,sequence)",
    """CREATE TABLE continuity_reflection_events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        reflection_id TEXT NOT NULL UNIQUE,
        review_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL
    )""",
    "CREATE INDEX continuity_reflection_events_review ON continuity_reflection_events(review_id,sequence)",
)


_REQUIRED_INDEXES = {
    "continuity_plan_events": {
        "continuity_plan_events_plan", "continuity_plan_events_order"
    },
    "provider_invocation_events": {"provider_invocation_events_invocation"},
    "continuity_watchdog_events": {"continuity_watchdog_events_order"},
    "continuity_evaluation_events": {
        "continuity_evaluation_events_plan", "continuity_evaluation_events_order"
    },
    "continuity_execution_events": {
        "continuity_execution_events_evaluation", "continuity_execution_events_order"
    },
    "continuity_report_events": {"continuity_report_events_outage"},
    "continuity_review_events": {
        "continuity_review_events_report", "continuity_review_events_invocation"
    },
    "continuity_reflection_events": {"continuity_reflection_events_review"},
}


def _names(db: Database, object_type: str, table: str | None = None) -> set[str]:
    query = "SELECT name FROM sqlite_master WHERE type=?"
    args: tuple[object, ...] = (object_type,)
    if table is not None:
        query += " AND tbl_name=?"
        args += (table,)
    return {str(row[0]) for row in db.execute(query, args).fetchall()}


def _version_count(db: Database) -> int:
    return int(db.execute(
        "SELECT COUNT(*) FROM schema_versions WHERE version=?",
        (CONTINUITY_SCHEMA_VERSION,),
    ).fetchone()[0])


def verify_continuity_schema_v3(db: Database) -> dict[str, Any]:
    present = CONTINUITY_TABLES & _names(db, "table")
    if present != CONTINUITY_TABLES or _version_count(db) != 1:
        raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INVALID")
    for table, columns in _TABLE_COLUMNS.items():
        actual = tuple(str(row[1]) for row in db.execute(f"PRAGMA table_info({table})"))
        if actual != columns:
            raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INVALID")
        if not _REQUIRED_INDEXES[table] <= _names(db, "index", table):
            raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INVALID")
        if _names(db, "trigger", table) != {
            f"{table}_no_update", f"{table}_no_delete"
        }:
            raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INVALID")
    return {
        "schema": "CONTINUITY_SCHEMA_V3_VERIFICATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "schema_version": CONTINUITY_SCHEMA_VERSION,
    }


def install_continuity_schema_v3(db: Database) -> dict[str, Any]:
    try:
        verify_successor_schema_v2(db)
    except SuccessorSchemaError as exc:
        raise ContinuitySchemaError("CONTINUITY_SCHEMA_V2_REQUIRED") from exc
    integrity = [str(row[0]) for row in db.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise ContinuitySchemaError("DATABASE_INTEGRITY_BLOCK")

    present = CONTINUITY_TABLES & _names(db, "table")
    if present or _version_count(db):
        try:
            verify_continuity_schema_v3(db)
        except ContinuitySchemaError as exc:
            raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INVALID") from exc
        return {
            "schema": "CONTINUITY_SCHEMA_V3_INSTALLATION_V1",
            "status": "PASS",
            "installed": False,
        }

    try:
        with db.transaction():
            for statement in _DDL:
                db.execute(statement)
            for table in CONTINUITY_APPEND_ONLY_TABLES:
                db.execute(
                    f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
                )
                db.execute(
                    f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable'); END"
                )
            db.execute(
                "INSERT INTO schema_versions(version,applied_at_utc) "
                "VALUES(3,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            )
    except Exception as exc:
        raise ContinuitySchemaError("CONTINUITY_SCHEMA_V3_INSTALL_FAILED") from exc
    verify_continuity_schema_v3(db)
    return {
        "schema": "CONTINUITY_SCHEMA_V3_INSTALLATION_V1",
        "status": "PASS",
        "installed": True,
    }
