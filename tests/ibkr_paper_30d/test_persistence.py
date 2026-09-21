from __future__ import annotations

import sqlite3

import pytest

from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "experiment.sqlite3"


def test_committed_event_survives_reopen_and_hash_chain_verifies(db_path) -> None:
    with Database.open(db_path) as db:
        EventRepository(db).append("SYSTEM_BOOTING", {"boot": 1})
        EventRepository(db).append("SYSTEM_PREFLIGHT", {"boot": 1})

    with Database.open(db_path) as db:
        verification = EventRepository(db).verify_chain()

    assert verification.valid is True
    assert verification.count == 2


def test_incomplete_transaction_rolls_back(db_path) -> None:
    with Database.open(db_path) as db:
        with pytest.raises(RuntimeError, match="crash"):
            with db.transaction() as tx:
                EventRepository(tx).append("X", {"n": 1})
                raise RuntimeError("crash")

    with Database.open(db_path) as db:
        assert EventRepository(db).count() == 0


def test_immutable_event_rejects_update_and_delete(db_path) -> None:
    with Database.open(db_path) as db:
        event_id = EventRepository(db).append("X", {"n": 1})

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE state_events SET event_type='Y' WHERE event_id=?",
                (event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM state_events WHERE event_id=?", (event_id,))


def test_foreign_keys_are_enforced(db_path) -> None:
    with Database.open(db_path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO order_events(event_id, order_id, event_type, payload_json, payload_sha256, created_at_utc) "
                "VALUES('e1', 'missing', 'X', '{}', 'hash', '2026-09-20T00:00:00Z')"
            )


def test_required_v2_tables_exist(db_path) -> None:
    expected = {
        "schema_versions",
        "experiment_state",
        "state_events",
        "decision_records",
        "orders",
        "order_events",
        "fills",
        "positions_snapshots",
        "subledger_events",
        "risk_snapshots",
        "broker_reconciliations",
        "heartbeats",
        "alerts",
        "alert_deliveries",
        "auditor_results",
        "process_changes",
        "benchmarks",
        "kill_switch_events",
        "execution_lock_events",
        "trader_input_bundles",
        "trader_invocations",
        "trader_results",
        "market_data_snapshots",
        "market_data_gate_results",
    }
    with Database.open(db_path) as db:
        actual = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert expected <= actual


def test_tampered_hash_chain_is_detected(db_path) -> None:
    with Database.open(db_path) as db:
        EventRepository(db).append("X", {"n": 1})
        db.execute("DROP TRIGGER state_events_no_update")
        db.execute("UPDATE state_events SET payload_json='{}'")
        db.commit()

        verification = EventRepository(db).verify_chain()

    assert verification.valid is False
    assert verification.first_invalid_sequence == 1


def test_database_lock_fails_closed(db_path) -> None:
    first = Database.open(db_path)
    second = Database.open(db_path)
    try:
        first.execute("BEGIN IMMEDIATE")
        second.execute("PRAGMA busy_timeout=25")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            second.execute(
                "INSERT INTO schema_versions(version, applied_at_utc) "
                "VALUES(99, '2026-09-21T00:00:00Z')"
            )
    finally:
        try:
            first.connection.rollback()
        except sqlite3.Error:
            pass
        first.close()
        second.close()


def test_autonomous_persistence_contract_distinguishes_legacy_tables() -> None:
    from ibkr_paper_30d.persistence import (
        AUTONOMOUS_CANONICAL_TABLES,
        LEGACY_COMPATIBILITY_TABLES,
    )

    assert {
        "autonomous_ledger_events",
        "experiment_clock_events",
        "experiment_authorization_events",
        "experiment_order_registry",
        "kill_switch_events",
        "trader_input_bundles",
        "trader_invocations",
        "trader_results",
        "autonomous_research_events",
    } <= AUTONOMOUS_CANONICAL_TABLES
    assert {
        "fills",
        "orders",
        "subledger_events",
        "broker_reconciliations",
        "market_data_snapshots",
        "market_data_gate_results",
    } <= LEGACY_COMPATIBILITY_TABLES
    assert AUTONOMOUS_CANONICAL_TABLES.isdisjoint(LEGACY_COMPATIBILITY_TABLES)
