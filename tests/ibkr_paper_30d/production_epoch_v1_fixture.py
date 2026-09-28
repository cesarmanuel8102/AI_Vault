from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.experiment_epoch import (
    ExperimentEpochStore,
    activation_receipt,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository

UTC = timezone.utc
ROOT_EPOCH_ID = "AUTONOMY_EPOCH_1"
ROOT_START = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
BASE_HEAD = "81fd236403632b2e2de4e9ebb86e14e02024770f"
OWNER_SID = "S-1-5-21-214160970-1890373857-4055601883-1001"
ACCOUNT_HASH = "8" * 64

SNAPSHOT_TABLES = frozenset(
    {
        "state_events",
        "experiment_clock_events",
        "experiment_authorization_events",
        "autonomous_ledger_events",
        "experiment_order_registry",
        "trader_input_bundles",
        "trader_invocations",
        "trader_results",
    }
)


@dataclass(frozen=True)
class ProductionEpochV1Fixture:
    db_path: Path
    root_definition_sha256: str
    root_clock_sha256: str
    snapshot: dict[str, tuple[tuple[object, ...], ...]]


def snapshot_v1_rows(
    db: Database,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    return {
        table: tuple(tuple(row) for row in db.execute(f"SELECT * FROM {table}"))
        for table in SNAPSHOT_TABLES
    }


def _insert_v1_authorization(db: Database, clock_sha256: str) -> None:
    payload = {
        "actor": "owner",
        "actor_sid": OWNER_SID,
        "state": "AUTHORIZED",
    }
    db.execute(
        "INSERT INTO experiment_authorization_events("
        "event_id,experiment_id,state,clock_event_sha256,payload_json,"
        "payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?)",
        (
            "owner-production-v1",
            "ibkr-paper-30d",
            "AUTHORIZED",
            clock_sha256,
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-23T13:25:00Z",
        ),
    )


def build_production_epoch_v1_fixture(path: Path) -> ProductionEpochV1Fixture:
    with Database.open(path) as db:
        events = EventRepository(db)
        for sequence in range(1, 536):
            events.append(
                "PRODUCTION_HISTORY_ANCHOR",
                {
                    "schema": "PRODUCTION_HISTORY_ANCHOR_V1",
                    "sequence": sequence,
                },
            )

        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=ROOT_START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        epoch_store = ExperimentEpochStore(db)
        preview = epoch_store.preview(
            epoch_id=ROOT_EPOCH_ID,
            start_utc=ROOT_START,
            duration_days=30,
            initial_allocation=Decimal("500"),
            approved_git_head=BASE_HEAD,
            owner_authorization_event_id="owner-production-v1",
            owner_authorization_receipt_sha256="a" * 64,
            objective_sha256="b" * 64,
            configuration_sha256="c" * 64,
        )
        definition = epoch_store.define(preview)
        _insert_v1_authorization(db, clock.event_sha256)
        receipt = activation_receipt(
            epoch_id=ROOT_EPOCH_ID,
            definition_sha256=definition.definition_sha256,
            owner_authorization_event_id="owner-production-v1",
            approved_git_head=BASE_HEAD,
            owner_authorization_receipt_sha256="a" * 64,
            issued_at_utc=ROOT_START - timedelta(minutes=1),
        )
        epoch_store.activate(ROOT_EPOCH_ID, receipt)
        events.append(
            "DAY1_LAUNCH_ATTEMPT_ACCEPTED",
            {
                "schema": "DAY1_LAUNCH_ATTEMPT_ACCEPTED_V1",
                "epoch_id": ROOT_EPOCH_ID,
                "launch_attempt_id": "production-attempt-v1",
            },
        )
        events.append(
            "EPOCH_MANIFEST_CREATED",
            {
                "schema": "EPOCH_MANIFEST_CREATED_V1",
                "epoch_id": ROOT_EPOCH_ID,
                "definition_sha256": definition.definition_sha256,
                "manifest_sha256": "e" * 64,
            },
        )

        tail = [
            (int(row[0]), str(row[1]))
            for row in db.execute(
                "SELECT sequence,event_type FROM state_events "
                "WHERE sequence BETWEEN 536 AND 539 ORDER BY sequence"
            )
        ]
        expected_tail = [
            (536, "EXPERIMENT_EPOCH_DEFINED"),
            (537, "EXPERIMENT_EPOCH_ACTIVATED"),
            (538, "DAY1_LAUNCH_ATTEMPT_ACCEPTED"),
            (539, "EPOCH_MANIFEST_CREATED"),
        ]
        if tail != expected_tail:
            raise AssertionError(f"production-shaped tail mismatch: {tail!r}")
        if not events.verify_chain().valid:
            raise AssertionError("production-shaped state chain is invalid")
        if db.execute(
            "SELECT COUNT(*) FROM state_events WHERE event_type='EPOCH_STARTED'"
        ).fetchone()[0]:
            raise AssertionError("production-shaped fixture unexpectedly started")
        snapshot = snapshot_v1_rows(db)

    return ProductionEpochV1Fixture(
        db_path=path,
        root_definition_sha256=definition.definition_sha256,
        root_clock_sha256=clock.event_sha256,
        snapshot=snapshot,
    )
