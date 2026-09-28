from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.experiment_epoch import ExperimentEpochStore, activation_receipt
from ibkr_paper_30d.owner_authorization import OWNER_PHRASE
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.successor_authorization import create_successor_authorization
from ibkr_paper_30d.successor_epoch import SuccessorEpochStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

UTC = timezone.utc
ROOT_START = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
SUCCESSOR_START = datetime(2026, 9, 28, 16, 30, tzinfo=UTC)
OWNER_SID = "S-1-5-21-test-owner"
HEAD_1 = "1" * 40
HEAD_2 = "2" * 40
ACCOUNT_HASH = "8" * 64


def build_authorized_successor(
    db_path: Path,
    receipt_path: Path,
    *,
    epoch_id: str = "AUTONOMY_EPOCH_2",
) -> tuple[dict[str, object], dict[str, object]]:
    with Database.open(db_path) as db:
        ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=ROOT_START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        epoch_store = ExperimentEpochStore(db)
        root = epoch_store.define(
            epoch_store.preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=ROOT_START,
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head=HEAD_1,
                owner_authorization_event_id="owner-v1",
                owner_authorization_receipt_sha256="a" * 64,
                objective_sha256="b" * 64,
                configuration_sha256="c" * 64,
            )
        )
        v1_payload = {"actor": "owner", "state": "AUTHORIZED"}
        db.execute(
            "INSERT INTO experiment_authorization_events(event_id,experiment_id,state,"
            "clock_event_sha256,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                "owner-v1",
                "ibkr-paper-30d",
                "AUTHORIZED",
                "d" * 64,
                canonical_bytes(v1_payload).decode(),
                sha256_json(v1_payload),
                "2026-09-23T13:25:00Z",
            ),
        )
        root_receipt = activation_receipt(
            epoch_id=root.epoch_id,
            definition_sha256=root.definition_sha256,
            owner_authorization_event_id="owner-v1",
            approved_git_head=HEAD_1,
            owner_authorization_receipt_sha256="a" * 64,
            issued_at_utc=ROOT_START - timedelta(minutes=1),
        )
        epoch_store.activate(root.epoch_id, root_receipt)
        EventRepository(db).append(
            "EPOCH_MANIFEST_CREATED",
            {"epoch_id": root.epoch_id, "manifest_sha256": "e" * 64},
        )
        install_successor_schema_v2(db)
        successor_store = SuccessorEpochStore(db)
        definition = successor_store.define(
            successor_store.preview(
                epoch_id=epoch_id,
                predecessor_epoch_id=root.epoch_id,
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head=HEAD_2,
                objective_sha256="b" * 64,
                configuration_sha256="c" * 64,
                reason="PRE_START_RUNTIME_FAILURE",
            )
        )
        definition_payload = successor_store.definition(definition.epoch_id)
    owner_receipt = create_successor_authorization(
        db_path=db_path,
        receipt_path=receipt_path,
        epoch_id=definition.epoch_id,
        definition_sha256=definition.definition_sha256,
        phrase=OWNER_PHRASE,
        actor_sid=OWNER_SID,
        elevated=True,
    )
    return definition_payload, owner_receipt
