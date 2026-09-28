"""Owner authorization bound to one late-start successor definition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .owner_authorization import (
    OWNER_PHRASE,
    atomic_authorization_receipt,
    owner_phrase_sha256,
)
from .persistence import Database
from .repositories import utc_now
from .successor_epoch import SuccessorEpochError, SuccessorEpochStore
from .successor_schema import AUTHORIZATION_TABLE, verify_successor_schema_v2
from .types import new_uuid7

AUTHORIZATION_SCHEMA_V2 = "OWNER_SUCCESSOR_AUTHORIZATION_V2"
REVOCATION_SCHEMA_V2 = "OWNER_SUCCESSOR_AUTHORIZATION_REVOCATION_V2"
EXPERIMENT_ID = "ibkr-paper-30d"


class SuccessorAuthorizationError(RuntimeError):
    pass


def _definition(db: Database, epoch_id: str) -> dict[str, Any]:
    try:
        return SuccessorEpochStore(db).definition(epoch_id)
    except SuccessorEpochError as exc:
        raise SuccessorAuthorizationError(str(exc)) from exc


def _latest_row(db: Database, epoch_id: str):
    return db.execute(
        f"SELECT event_id,state,definition_sha256,approved_git_head,"
        f"payload_json,payload_sha256 FROM {AUTHORIZATION_TABLE} "
        "WHERE experiment_id=? AND epoch_id=? ORDER BY sequence DESC LIMIT 1",
        (EXPERIMENT_ID, epoch_id),
    ).fetchone()


def _parse_row(row) -> tuple[str, str, str, str, dict[str, Any]]:
    event_id, state, definition_sha, approved_head, payload_json, payload_sha = row
    try:
        payload = json.loads(str(payload_json))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_CORRUPT") from exc
    if not isinstance(payload, dict) or sha256_json(payload) != str(payload_sha):
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_HASH_MISMATCH")
    return (
        str(event_id),
        str(state),
        str(definition_sha),
        str(approved_head),
        payload,
    )


def _expected_bindings(definition: dict[str, Any], actor_sid: str) -> dict[str, Any]:
    return {
        "schema": AUTHORIZATION_SCHEMA_V2,
        "experiment_id": EXPERIMENT_ID,
        "authorization_state": "AUTHORIZED",
        "actor_sid": actor_sid,
        "epoch_id": definition["epoch_id"],
        "definition_sha256": definition["definition_sha256"],
        "predecessor_epoch_id": definition["predecessor_epoch_id"],
        "supersession_reason": definition["supersession_reason"],
        "approved_git_head": definition["approved_git_head"],
        "duration_days": definition["duration_days"],
        "initial_allocation": definition["initial_allocation"],
        "clock_start_policy": definition["clock_start_policy"],
        "owner_phrase_sha256": owner_phrase_sha256(),
    }


def _validate_authorized_payload(
    *,
    row,
    definition: dict[str, Any],
    expected_actor_sid: str,
) -> dict[str, Any]:
    event_id, state, definition_sha, approved_head, payload = _parse_row(row)
    if state == "REVOKED":
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_REVOKED")
    if state != "AUTHORIZED":
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_INVALID")
    if payload.get("actor_sid") != expected_actor_sid:
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_OWNER_MISMATCH")
    expected = _expected_bindings(definition, expected_actor_sid)
    if (
        definition_sha != definition["definition_sha256"]
        or approved_head != definition["approved_git_head"]
        or payload.get("authorization_event_id") != event_id
        or any(payload.get(key) != value for key, value in expected.items())
    ):
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_BINDING_MISMATCH")
    unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    if payload.get("receipt_sha256") != sha256_json(unsigned):
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_HASH_MISMATCH")
    return payload


def create_successor_authorization(
    *,
    db_path: Path,
    receipt_path: Path,
    epoch_id: str,
    definition_sha256: str,
    phrase: str,
    actor_sid: str,
    elevated: bool,
) -> dict[str, Any]:
    if phrase != OWNER_PHRASE:
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_PHRASE_INVALID")
    if not elevated:
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_REQUIRES_ELEVATION")
    if not actor_sid.strip():
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_OWNER_INVALID")

    with Database.open(db_path) as db:
        verify_successor_schema_v2(db)
        definition = _definition(db, epoch_id)
        if definition.get("definition_sha256") != definition_sha256:
            raise SuccessorAuthorizationError(
                "SUCCESSOR_AUTHORIZATION_DEFINITION_MISMATCH"
            )
        existing = _latest_row(db, epoch_id)
        if existing is not None:
            payload = _validate_authorized_payload(
                row=existing,
                definition=definition,
                expected_actor_sid=actor_sid,
            )
        else:
            event_id = str(new_uuid7())
            unsigned = {
                **_expected_bindings(definition, actor_sid),
                "authorization_event_id": event_id,
                "issued_at_utc": utc_now(),
            }
            payload = {**unsigned, "receipt_sha256": sha256_json(unsigned)}
            with db.transaction():
                db.execute(
                    f"INSERT INTO {AUTHORIZATION_TABLE}("
                    "event_id,experiment_id,epoch_id,state,definition_sha256,"
                    "approved_git_head,payload_json,payload_sha256,created_at_utc"
                    ") VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        event_id,
                        EXPERIMENT_ID,
                        epoch_id,
                        "AUTHORIZED",
                        definition_sha256,
                        definition["approved_git_head"],
                        canonical_bytes(payload).decode("utf-8"),
                        sha256_json(payload),
                        utc_now(),
                    ),
                )
    atomic_authorization_receipt(receipt_path, payload)
    return payload


def validate_successor_authorization(
    *,
    db_path: Path,
    receipt_path: Path,
    epoch_id: str,
    definition_sha256: str,
    expected_actor_sid: str,
) -> dict[str, Any]:
    if not db_path.is_file():
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_MISSING")
    with Database.open(db_path) as db:
        definition = _definition(db, epoch_id)
        if definition.get("definition_sha256") != definition_sha256:
            raise SuccessorAuthorizationError(
                "SUCCESSOR_AUTHORIZATION_DEFINITION_MISMATCH"
            )
        row = _latest_row(db, epoch_id)
        if row is None:
            raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_MISSING")
        payload = _validate_authorized_payload(
            row=row,
            definition=definition,
            expected_actor_sid=expected_actor_sid,
        )
    try:
        receipt = json.loads(receipt_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SuccessorAuthorizationError(
            "SUCCESSOR_AUTHORIZATION_RECEIPT_MISSING"
        ) from exc
    if receipt != payload:
        raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_RECEIPT_MISMATCH")
    return payload


def revoke_successor_authorization(
    *,
    db_path: Path,
    epoch_id: str,
    definition_sha256: str,
    actor_sid: str,
) -> dict[str, Any]:
    with Database.open(db_path) as db:
        verify_successor_schema_v2(db)
        definition = _definition(db, epoch_id)
        if definition.get("definition_sha256") != definition_sha256:
            raise SuccessorAuthorizationError(
                "SUCCESSOR_AUTHORIZATION_DEFINITION_MISMATCH"
            )
        latest = _latest_row(db, epoch_id)
        if latest is None:
            raise SuccessorAuthorizationError("SUCCESSOR_AUTHORIZATION_MISSING")
        authorized = _validate_authorized_payload(
            row=latest,
            definition=definition,
            expected_actor_sid=actor_sid,
        )
        payload = {
            "schema": REVOCATION_SCHEMA_V2,
            "experiment_id": EXPERIMENT_ID,
            "authorization_state": "REVOKED",
            "actor_sid": actor_sid,
            "epoch_id": epoch_id,
            "definition_sha256": definition_sha256,
            "revoked_authorization_event_id": authorized["authorization_event_id"],
            "revoked_receipt_sha256": authorized["receipt_sha256"],
            "revoked_at_utc": utc_now(),
        }
        event_id = str(new_uuid7())
        with db.transaction():
            db.execute(
                f"INSERT INTO {AUTHORIZATION_TABLE}("
                "event_id,experiment_id,epoch_id,state,definition_sha256,"
                "approved_git_head,payload_json,payload_sha256,created_at_utc"
                ") VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    EXPERIMENT_ID,
                    epoch_id,
                    "REVOKED",
                    definition_sha256,
                    definition["approved_git_head"],
                    canonical_bytes(payload).decode("utf-8"),
                    sha256_json(payload),
                    utc_now(),
                ),
            )
    return payload
