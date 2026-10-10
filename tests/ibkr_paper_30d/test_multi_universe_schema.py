from __future__ import annotations

import hashlib
import sqlite3

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_schema import (
    MULTI_UNIVERSE_TABLES,
    MultiUniverseSchemaError,
    install_multi_universe_schema_v4,
    verify_multi_universe_schema_v4,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _tables(db: Database) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _install_v3(db: Database) -> None:
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)


def test_database_open_does_not_install_multi_universe_schema_v4(tmp_path) -> None:
    path = tmp_path / "production-v3.sqlite3"
    with Database.open(path) as db:
        _install_v3(db)

    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with Database.open(path) as db:
        assert MULTI_UNIVERSE_TABLES.isdisjoint(_tables(db))
        versions = [
            int(row[0])
            for row in db.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            )
        ]
    after = hashlib.sha256(path.read_bytes()).hexdigest()

    assert versions == [1, 2, 3]
    assert after == before


def test_install_requires_verified_schema_versions_2_and_3(tmp_path) -> None:
    with Database.open(tmp_path / "v1.sqlite3") as db:
        with pytest.raises(MultiUniverseSchemaError, match="V2_V3_REQUIRED"):
            install_multi_universe_schema_v4(db)

    with Database.open(tmp_path / "v2.sqlite3") as db:
        install_successor_schema_v2(db)
        with pytest.raises(MultiUniverseSchemaError, match="V2_V3_REQUIRED"):
            install_multi_universe_schema_v4(db)


def test_explicit_install_is_idempotent_and_verified(tmp_path) -> None:
    with Database.open(tmp_path / "v4.sqlite3") as db:
        _install_v3(db)
        first = install_multi_universe_schema_v4(db)
        second = install_multi_universe_schema_v4(db)
        verification = verify_multi_universe_schema_v4(db)
        versions = [
            int(row[0])
            for row in db.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            )
        ]

    assert first["installed"] is True
    assert second["installed"] is False
    assert verification == {
        "schema": "MULTI_UNIVERSE_SCHEMA_V4_VERIFICATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "schema_version": 4,
    }
    assert versions == [1, 2, 3, 4]


@pytest.mark.parametrize("table", sorted([
    "sleeve_authority_events",
    "sleeve_ledger_events",
    "contract_ownership_events",
    "product_family_certification_events",
    "owner_economic_risk_authorization_events",
    "canary_authorization_events",
    "successor_transition_events",
]))
def test_every_v4_table_rejects_update_and_delete(tmp_path, table: str) -> None:
    with Database.open(tmp_path / f"{table}.sqlite3") as db:
        _install_v3(db)
        install_multi_universe_schema_v4(db)
        columns = {
            str(row[1])
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        required = {
            "event_id": "event-1",
            "event_type": "TEST",
            "payload_json": "{}",
            "payload_sha256": "a" * 64,
            "previous_event_sha256": None,
            "event_sha256": "b" * 64,
            "created_at_utc": "2026-10-09T18:00:00Z",
        }
        optional = {
            "sleeve": "REGULAR_SLEEVE",
            "currency": "USD",
            "ownership_group_id": "group-1",
            "contract_identity_sha256": "c" * 64,
            "product_family_sha256": "d" * 64,
            "authorization_id": "authorization-1",
            "transition_id": "transition-1",
            "phase": "PREPARED",
        }
        row = {**required, **{k: v for k, v in optional.items() if k in columns}}
        names = ",".join(row)
        placeholders = ",".join("?" for _ in row)
        db.execute(
            f"INSERT INTO {table}({names}) VALUES({placeholders})",
            tuple(row.values()),
        )

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                f"UPDATE {table} SET event_type='CHANGED' WHERE event_id='event-1'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(f"DELETE FROM {table} WHERE event_id='event-1'")


def test_partial_v4_schema_blocks_without_marking_version(tmp_path) -> None:
    with Database.open(tmp_path / "partial.sqlite3") as db:
        _install_v3(db)
        db.execute("CREATE TABLE sleeve_authority_events(sequence INTEGER)")

        with pytest.raises(MultiUniverseSchemaError, match="V4_INVALID"):
            install_multi_universe_schema_v4(db)

        assert db.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=4"
        ).fetchone()[0] == 0


def test_verify_rejects_missing_or_malformed_v4_read_only(tmp_path) -> None:
    with Database.open(tmp_path / "missing.sqlite3") as db:
        _install_v3(db)
        before = db.connection.total_changes
        with pytest.raises(MultiUniverseSchemaError, match="V4_MISSING"):
            verify_multi_universe_schema_v4(db)
        assert db.connection.total_changes == before
