from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.experiment_epoch import ExperimentEpochStore, activation_receipt
from ibkr_paper_30d.owner_authorization import OWNER_PHRASE
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.successor_authorization import (
    SuccessorAuthorizationError,
    create_successor_authorization,
    revoke_successor_authorization,
    validate_successor_authorization,
)
from ibkr_paper_30d.successor_epoch import SuccessorEpochStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

UTC = timezone.utc
START = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
OWNER_SID = "S-1-5-21-test-owner"
HEAD_1 = "1" * 40
HEAD_2 = "2" * 40


def _fixture(tmp_path):
    db_path = tmp_path / "successor-auth.sqlite3"
    receipt_path = tmp_path / "successor-auth-v2.json"
    with Database.open(db_path) as db:
        ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=START,
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        epoch_store = ExperimentEpochStore(db)
        root = epoch_store.define(
            epoch_store.preview(
                epoch_id="AUTONOMY_EPOCH_1",
                start_utc=START,
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
        receipt = activation_receipt(
            epoch_id=root.epoch_id,
            definition_sha256=root.definition_sha256,
            owner_authorization_event_id="owner-v1",
            approved_git_head=HEAD_1,
            owner_authorization_receipt_sha256="a" * 64,
            issued_at_utc=START - timedelta(minutes=1),
        )
        epoch_store.activate(root.epoch_id, receipt)
        EventRepository(db).append(
            "EPOCH_MANIFEST_CREATED",
            {"epoch_id": root.epoch_id, "manifest_sha256": "e" * 64},
        )
        install_successor_schema_v2(db)
        successor_store = SuccessorEpochStore(db)
        successor = successor_store.define(
            successor_store.preview(
                epoch_id="AUTONOMY_EPOCH_2",
                predecessor_epoch_id=root.epoch_id,
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head=HEAD_2,
                objective_sha256="b" * 64,
                configuration_sha256="c" * 64,
                reason="PRE_START_RUNTIME_FAILURE",
            )
        )
    return db_path, receipt_path, successor.definition_sha256


def _create(tmp_path, **overrides):
    db_path, receipt_path, definition_sha = _fixture(tmp_path)
    values = {
        "db_path": db_path,
        "receipt_path": receipt_path,
        "epoch_id": "AUTONOMY_EPOCH_2",
        "definition_sha256": definition_sha,
        "phrase": OWNER_PHRASE,
        "actor_sid": OWNER_SID,
        "elevated": True,
    }
    values.update(overrides)
    return (
        create_successor_authorization(**values),
        db_path,
        receipt_path,
        definition_sha,
    )


def test_create_binds_exact_successor_without_consuming_clock_or_activation(
    tmp_path,
) -> None:
    receipt, db_path, receipt_path, definition_sha = _create(tmp_path)

    assert receipt["schema"] == "OWNER_SUCCESSOR_AUTHORIZATION_V2"
    assert receipt["epoch_id"] == "AUTONOMY_EPOCH_2"
    assert receipt["definition_sha256"] == definition_sha
    assert receipt["predecessor_epoch_id"] == "AUTONOMY_EPOCH_1"
    assert receipt["approved_git_head"] == HEAD_2
    assert receipt["duration_days"] == 30
    assert receipt["initial_allocation"] == "500"
    assert receipt["supersession_reason"] == "PRE_START_RUNTIME_FAILURE"
    assert receipt["clock_start_policy"] == "BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH"
    assert receipt["actor_sid"] == OWNER_SID
    assert "start_utc" not in receipt and "end_utc" not in receipt
    assert not ({"account", "password", "credential", "token"} & set(receipt))
    assert json.loads(receipt_path.read_bytes()) == receipt
    with Database.open(db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_authorization_events_v2"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EPOCH_STARTED'"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"phrase": "almost"}, "SUCCESSOR_AUTHORIZATION_PHRASE_INVALID"),
        ({"elevated": False}, "SUCCESSOR_AUTHORIZATION_REQUIRES_ELEVATION"),
        ({"actor_sid": ""}, "SUCCESSOR_AUTHORIZATION_OWNER_INVALID"),
        (
            {"definition_sha256": "0" * 64},
            "SUCCESSOR_AUTHORIZATION_DEFINITION_MISMATCH",
        ),
        ({"epoch_id": "AUTONOMY_EPOCH_3"}, "SUCCESSOR_DEFINITION_MISSING"),
    ],
)
def test_create_rejects_invalid_owner_or_target(tmp_path, overrides, reason) -> None:
    with pytest.raises(SuccessorAuthorizationError, match=reason):
        _create(tmp_path, **overrides)


def test_exact_retry_is_idempotent_and_validation_is_read_only(tmp_path) -> None:
    first, db_path, receipt_path, definition_sha = _create(tmp_path)
    second = create_successor_authorization(
        db_path=db_path,
        receipt_path=receipt_path,
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256=definition_sha,
        phrase=OWNER_PHRASE,
        actor_sid=OWNER_SID,
        elevated=True,
    )
    with Database.open(db_path) as db:
        before = db.execute(
            "SELECT COUNT(*) FROM experiment_epoch_authorization_events_v2"
        ).fetchone()[0]
    validated = validate_successor_authorization(
        db_path=db_path,
        receipt_path=receipt_path,
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256=definition_sha,
        expected_actor_sid=OWNER_SID,
    )
    with Database.open(db_path) as db:
        after = db.execute(
            "SELECT COUNT(*) FROM experiment_epoch_authorization_events_v2"
        ).fetchone()[0]

    assert first == second == validated
    assert before == after == 1


def test_v1_receipt_cannot_authorize_successor(tmp_path) -> None:
    receipt, db_path, receipt_path, definition_sha = _create(tmp_path)
    receipt_path.write_text(json.dumps({"schema": "DAY1_OWNER_AUTHORIZATION_V1"}))

    with pytest.raises(
        SuccessorAuthorizationError, match="SUCCESSOR_AUTHORIZATION_RECEIPT_MISMATCH"
    ):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_2",
            definition_sha256=definition_sha,
            expected_actor_sid=OWNER_SID,
        )
    assert receipt["schema"] == "OWNER_SUCCESSOR_AUTHORIZATION_V2"


def test_receipt_for_another_epoch_or_owner_is_rejected(tmp_path) -> None:
    _, db_path, receipt_path, definition_sha = _create(tmp_path)
    with pytest.raises(SuccessorAuthorizationError):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_3",
            definition_sha256=definition_sha,
            expected_actor_sid=OWNER_SID,
        )
    with pytest.raises(
        SuccessorAuthorizationError, match="SUCCESSOR_AUTHORIZATION_OWNER_MISMATCH"
    ):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_2",
            definition_sha256=definition_sha,
            expected_actor_sid="S-1-5-21-other",
        )


def test_latest_revocation_blocks_authorization(tmp_path) -> None:
    _, db_path, receipt_path, definition_sha = _create(tmp_path)
    revoke_successor_authorization(
        db_path=db_path,
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256=definition_sha,
        actor_sid=OWNER_SID,
    )

    with pytest.raises(
        SuccessorAuthorizationError, match="SUCCESSOR_AUTHORIZATION_REVOKED"
    ):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_2",
            definition_sha256=definition_sha,
            expected_actor_sid=OWNER_SID,
        )


def test_modified_authorization_head_and_malformed_hash_are_rejected(tmp_path) -> None:
    _, db_path, receipt_path, definition_sha = _create(tmp_path)
    with Database.open(db_path) as db:
        db.execute("DROP TRIGGER experiment_epoch_authorization_events_v2_no_update")
        db.execute(
            "UPDATE experiment_epoch_authorization_events_v2 SET approved_git_head=?",
            ("9" * 40,),
        )
    with pytest.raises(
        SuccessorAuthorizationError, match="SUCCESSOR_AUTHORIZATION_BINDING_MISMATCH"
    ):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_2",
            definition_sha256=definition_sha,
            expected_actor_sid=OWNER_SID,
        )

    with Database.open(db_path) as db:
        db.execute(
            "UPDATE experiment_epoch_authorization_events_v2 SET payload_sha256='bad'"
        )
    with pytest.raises(
        SuccessorAuthorizationError, match="SUCCESSOR_AUTHORIZATION_HASH_MISMATCH"
    ):
        validate_successor_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            epoch_id="AUTONOMY_EPOCH_2",
            definition_sha256=definition_sha,
            expected_actor_sid=OWNER_SID,
        )
