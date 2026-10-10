"""Explicit append-only schema for multi-universe sleeve authority."""

from __future__ import annotations

from typing import Any

from .continuity_schema import ContinuitySchemaError, verify_continuity_schema_v3
from .persistence import (
    MULTI_UNIVERSE_APPEND_ONLY_TABLES,
    MULTI_UNIVERSE_CANONICAL_TABLES,
    Database,
)
from .successor_schema import SuccessorSchemaError, verify_successor_schema_v2


MULTI_UNIVERSE_SCHEMA_VERSION = 4
MULTI_UNIVERSE_TABLES = MULTI_UNIVERSE_CANONICAL_TABLES


class MultiUniverseSchemaError(RuntimeError):
    pass


_TABLE_COLUMNS = {
    "sleeve_authority_events": (
        "sequence", "event_id", "sleeve", "event_type", "payload_json",
        "payload_sha256", "previous_event_sha256", "event_sha256",
        "created_at_utc",
    ),
    "sleeve_ledger_events": (
        "sequence", "event_id", "sleeve", "currency", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "contract_ownership_events": (
        "sequence", "event_id", "ownership_group_id",
        "contract_identity_sha256", "sleeve", "event_type", "payload_json",
        "payload_sha256", "previous_event_sha256", "event_sha256",
        "created_at_utc",
    ),
    "product_family_certification_events": (
        "sequence", "event_id", "product_family_sha256", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "owner_economic_risk_authorization_events": (
        "sequence", "event_id", "authorization_id", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "canary_authorization_events": (
        "sequence", "event_id", "authorization_id", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
    "successor_transition_events": (
        "sequence", "event_id", "transition_id", "phase", "event_type",
        "payload_json", "payload_sha256", "previous_event_sha256",
        "event_sha256", "created_at_utc",
    ),
}


def _event_columns(*authority: str) -> str:
    authority_sql = ",".join(f"{name} TEXT NOT NULL" for name in authority)
    if authority_sql:
        authority_sql += ","
    return f"""sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        {authority_sql}
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        previous_event_sha256 TEXT,
        event_sha256 TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL"""


_DDL = (
    f"CREATE TABLE sleeve_authority_events({_event_columns('sleeve')})",
    "CREATE INDEX sleeve_authority_events_sleeve ON sleeve_authority_events(sleeve,sequence)",
    f"CREATE TABLE sleeve_ledger_events({_event_columns('sleeve', 'currency')})",
    "CREATE INDEX sleeve_ledger_events_sleeve ON sleeve_ledger_events(sleeve,currency,sequence)",
    f"CREATE TABLE contract_ownership_events({_event_columns('ownership_group_id', 'contract_identity_sha256', 'sleeve')})",
    "CREATE INDEX contract_ownership_events_contract ON contract_ownership_events(contract_identity_sha256,sequence)",
    "CREATE INDEX contract_ownership_events_group ON contract_ownership_events(ownership_group_id,sequence)",
    f"CREATE TABLE product_family_certification_events({_event_columns('product_family_sha256')})",
    "CREATE INDEX product_family_certification_events_family ON product_family_certification_events(product_family_sha256,sequence)",
    f"CREATE TABLE owner_economic_risk_authorization_events({_event_columns('authorization_id')})",
    "CREATE INDEX owner_economic_risk_authorization_events_authorization ON owner_economic_risk_authorization_events(authorization_id,sequence)",
    f"CREATE TABLE canary_authorization_events({_event_columns('authorization_id')})",
    "CREATE INDEX canary_authorization_events_authorization ON canary_authorization_events(authorization_id,sequence)",
    f"CREATE TABLE successor_transition_events({_event_columns('transition_id', 'phase')})",
    "CREATE INDEX successor_transition_events_transition ON successor_transition_events(transition_id,sequence)",
)


_REQUIRED_INDEXES = {
    "sleeve_authority_events": {"sleeve_authority_events_sleeve"},
    "sleeve_ledger_events": {"sleeve_ledger_events_sleeve"},
    "contract_ownership_events": {
        "contract_ownership_events_contract",
        "contract_ownership_events_group",
    },
    "product_family_certification_events": {
        "product_family_certification_events_family"
    },
    "owner_economic_risk_authorization_events": {
        "owner_economic_risk_authorization_events_authorization"
    },
    "canary_authorization_events": {
        "canary_authorization_events_authorization"
    },
    "successor_transition_events": {"successor_transition_events_transition"},
}


def _names(db: Database, object_type: str, table: str | None = None) -> set[str]:
    sql = "SELECT name FROM sqlite_master WHERE type=?"
    parameters: tuple[object, ...] = (object_type,)
    if table is not None:
        sql += " AND tbl_name=?"
        parameters += (table,)
    return {str(row[0]) for row in db.execute(sql, parameters).fetchall()}


def _versions(db: Database) -> list[int]:
    return [
        int(row[0])
        for row in db.execute(
            "SELECT version FROM schema_versions ORDER BY version"
        ).fetchall()
    ]


def _validate_prerequisites(db: Database) -> None:
    try:
        verify_successor_schema_v2(db)
        verify_continuity_schema_v3(db)
    except (SuccessorSchemaError, ContinuitySchemaError) as exc:
        raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V2_V3_REQUIRED") from exc
    if _versions(db) not in ([1, 2, 3], [1, 2, 3, 4]):
        raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V2_V3_REQUIRED")


def verify_multi_universe_schema_v4(db: Database) -> dict[str, Any]:
    _validate_prerequisites(db)
    present = MULTI_UNIVERSE_TABLES & _names(db, "table")
    version_count = int(
        db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=4"
        ).fetchone()[0]
    )
    if not present and version_count == 0:
        raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_MISSING")
    if present != MULTI_UNIVERSE_TABLES or version_count != 1:
        raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INVALID")
    for table, columns in _TABLE_COLUMNS.items():
        actual = tuple(
            str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")
        )
        if actual != columns:
            raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INVALID")
        if not _REQUIRED_INDEXES[table] <= _names(db, "index", table):
            raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INVALID")
        if _names(db, "trigger", table) != {
            f"{table}_no_update",
            f"{table}_no_delete",
        }:
            raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INVALID")
    return {
        "schema": "MULTI_UNIVERSE_SCHEMA_V4_VERIFICATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "schema_version": MULTI_UNIVERSE_SCHEMA_VERSION,
    }


def install_multi_universe_schema_v4(db: Database) -> dict[str, Any]:
    _validate_prerequisites(db)
    integrity = [str(row[0]) for row in db.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise MultiUniverseSchemaError("DATABASE_INTEGRITY_BLOCK")

    present = MULTI_UNIVERSE_TABLES & _names(db, "table")
    version_count = int(
        db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=4"
        ).fetchone()[0]
    )
    if present or version_count:
        try:
            verify_multi_universe_schema_v4(db)
        except MultiUniverseSchemaError as exc:
            raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INVALID") from exc
        return {
            "schema": "MULTI_UNIVERSE_SCHEMA_V4_INSTALLATION_V1",
            "status": "PASS",
            "installed": False,
        }

    try:
        with db.transaction():
            for statement in _DDL:
                db.execute(statement)
            for table in MULTI_UNIVERSE_APPEND_ONLY_TABLES:
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
                "VALUES(4,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            )
    except Exception as exc:
        raise MultiUniverseSchemaError("MULTI_UNIVERSE_SCHEMA_V4_INSTALL_FAILED") from exc

    verify_multi_universe_schema_v4(db)
    return {
        "schema": "MULTI_UNIVERSE_SCHEMA_V4_INSTALLATION_V1",
        "status": "PASS",
        "installed": True,
    }
