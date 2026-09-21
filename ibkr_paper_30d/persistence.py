from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence


# Canonical persistence surfaces for the autonomous IBKR experiment.
# These are the tables new autonomous runtime code is expected to write.
AUTONOMOUS_CANONICAL_TABLES = frozenset({
    "state_events",
    "autonomous_ledger_events",
    "experiment_clock_events",
    "experiment_authorization_events",
    "experiment_order_registry",
    "kill_switch_events",
    "alerts",
    "trader_input_bundles",
    "trader_invocations",
    "trader_results",
    "autonomous_research_events",
})

# Retained for backwards compatibility with the earlier Phase-1 architecture.
# New autonomous runtime code MUST NOT depend on these tables as authoritative
# state unless they are explicitly promoted into AUTONOMOUS_CANONICAL_TABLES.
LEGACY_COMPATIBILITY_TABLES = frozenset({
    "decision_records",
    "orders",
    "order_events",
    "fills",
    "positions_snapshots",
    "subledger_events",
    "risk_snapshots",
    "broker_reconciliations",
    "heartbeats",
    "alert_deliveries",
    "auditor_results",
    "process_changes",
    "benchmarks",
    "execution_lock_events",
    "market_data_snapshots",
    "market_data_gate_results",
})

APPEND_ONLY_TABLES = (
    "state_events",
    "decision_records",
    "order_events",
    "fills",
    "positions_snapshots",
    "subledger_events",
    "autonomous_ledger_events",
    "experiment_clock_events",
    "experiment_authorization_events",
    "experiment_order_registry",
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
    "autonomous_research_events",
    "market_data_snapshots",
    "market_data_gate_results",
)


def configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions(
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_state(
    experiment_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_events(
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_records(
    decision_id TEXT PRIMARY KEY,
    predecessor_id TEXT REFERENCES decision_records(decision_id),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders(
    order_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decision_records(decision_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    client_order_id TEXT NOT NULL UNIQUE,
    order_ref TEXT NOT NULL UNIQUE,
    session_fingerprint TEXT,
    ibkr_order_id INTEGER,
    perm_id INTEGER UNIQUE,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(session_fingerprint, ibkr_order_id)
);
CREATE TABLE IF NOT EXISTS order_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills(
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    execution_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions_snapshots(
    snapshot_id TEXT PRIMARY KEY,
    reconciliation_id TEXT,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subledger_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS autonomous_ledger_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_clock_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    experiment_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_experiment_start
ON experiment_clock_events(experiment_id, event_type);
CREATE TABLE IF NOT EXISTS experiment_authorization_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    experiment_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('AUTHORIZED','REVOKED')),
    clock_event_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS experiment_authorization_events_experiment
ON experiment_authorization_events(experiment_id, sequence);
CREATE TABLE IF NOT EXISTS experiment_order_registry(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    registry_id TEXT NOT NULL UNIQUE,
    order_ref TEXT NOT NULL,
    client_order_id INTEGER,
    perm_id INTEGER,
    ibkr_order_id INTEGER,
    contract_id INTEGER,
    action TEXT NOT NULL,
    quantity TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS experiment_order_registry_order_ref
ON experiment_order_registry(order_ref);
CREATE INDEX IF NOT EXISTS experiment_order_registry_client_order_id
ON experiment_order_registry(client_order_id);
CREATE INDEX IF NOT EXISTS experiment_order_registry_perm_id
ON experiment_order_registry(perm_id);
CREATE TABLE IF NOT EXISTS risk_snapshots(
    snapshot_id TEXT PRIMARY KEY,
    decision_id TEXT REFERENCES decision_records(decision_id),
    policy_version TEXT NOT NULL,
    result TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS broker_reconciliations(
    reconciliation_id TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS heartbeats(
    heartbeat_id TEXT PRIMARY KEY,
    heartbeat_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts(
    alert_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_deliveries(
    delivery_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auditor_results(
    result_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS process_changes(
    change_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benchmarks(
    observation_id TEXT PRIMARY KEY,
    benchmark_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kill_switch_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_lock_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    generation INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trader_input_bundles(
    bundle_id TEXT PRIMARY KEY,
    decision_cycle_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trader_invocations(
    invocation_id TEXT PRIMARY KEY,
    decision_cycle_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL REFERENCES trader_input_bundles(bundle_id),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trader_results(
    result_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL REFERENCES trader_invocations(invocation_id),
    decision_cycle_id TEXT NOT NULL,
    accepted INTEGER NOT NULL CHECK(accepted IN (0,1)),
    accepted_cycle_key TEXT UNIQUE,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK((accepted=1 AND accepted_cycle_key=decision_cycle_id) OR
          (accepted=0 AND accepted_cycle_key IS NULL))
);
CREATE TABLE IF NOT EXISTS autonomous_research_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    decision_cycle_id TEXT NOT NULL,
    invocation_id TEXT NOT NULL,
    round_index INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_data_snapshots(
    snapshot_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_data_gate_results(
    result_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES market_data_snapshots(snapshot_id),
    status TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
"""


class Database:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    @classmethod
    def open(cls, path: str | Path) -> "Database":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target, isolation_level=None)
        configure_connection(conn)
        conn.executescript(SCHEMA)
        cls._install_immutable_triggers(conn)
        conn.execute(
            "INSERT OR IGNORE INTO schema_versions(version, applied_at_utc) "
            "VALUES(1, strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
        )
        return cls(conn)

    @staticmethod
    def _install_immutable_triggers(conn: sqlite3.Connection) -> None:
        for table in APPEND_ONLY_TABLES:
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_no_update "
                f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable'); END"
            )
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete "
                f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable'); END"
            )

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, parameters)

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator["Database"]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
