from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from .canonical import canonical_bytes, sha256_json
from .experiment_control import (
    ExperimentClock,
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from .persistence import Database

OWNER_PHRASE = "AUTHORIZE 30-DAY PAPER EXPERIMENT"
START_UTC = datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
DURATION_DAYS = 30
INITIAL_ALLOCATION = Decimal("500")
EXPERIMENT_ID = "ibkr-paper-30d"
RECEIPT_SCHEMA = "DAY1_OWNER_AUTHORIZATION_V1"


class OwnerAuthorizationError(RuntimeError):
    pass


def atomic_authorization_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def owner_phrase_sha256() -> str:
    return hashlib.sha256(OWNER_PHRASE.encode("utf-8")).hexdigest()


def _authorization_rows(db: Database) -> list[tuple[str, str, str, str, str]]:
    return [
        tuple(map(str, row))
        for row in db.execute(
            "SELECT event_id,state,clock_event_sha256,payload_json,payload_sha256 "
            "FROM experiment_authorization_events WHERE experiment_id=? "
            "ORDER BY sequence ASC",
            (EXPERIMENT_ID,),
        ).fetchall()
    ]


def _kill_history(db: Database) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in db.execute(
            "SELECT state FROM kill_switch_events ORDER BY sequence ASC"
        ).fetchall()
    )


def _validate_clock(clock: ExperimentClock | None) -> ExperimentClock:
    if clock is None:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_MISSING")
    if (
        clock.experiment_id != EXPERIMENT_ID
        or clock.start_utc != START_UTC
        or clock.end_utc != START_UTC + timedelta(days=DURATION_DAYS)
        or clock.duration_days != DURATION_DAYS
        or clock.initial_allocation != INITIAL_ALLOCATION
    ):
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_CLOCK_MISMATCH")
    return clock


def _validate_authorization_event(
    db: Database,
    clock: ExperimentClock,
    actor_sid: str,
) -> str:
    rows = _authorization_rows(db)
    if len(rows) != 1:
        raise OwnerAuthorizationError(
            "OWNER_AUTHORIZATION_MISSING"
            if not rows
            else "OWNER_AUTHORIZATION_HISTORY_INVALID"
        )
    event_id, state, bound_clock, payload_json, payload_sha256 = rows[0]
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_CORRUPT") from exc
    if sha256_json(payload) != payload_sha256:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_HASH_MISMATCH")
    if str(payload.get("actor")) != actor_sid:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_OWNER_MISMATCH")
    if (
        state != "AUTHORIZED"
        or str(payload.get("state")) != "AUTHORIZED"
        or bound_clock != clock.event_sha256
        or str(payload.get("clock_event_sha256")) != clock.event_sha256
        or str(payload.get("reason")) != OWNER_PHRASE
    ):
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_INVALID")
    return event_id


def _receipt(
    clock: ExperimentClock, event_id: str, actor_sid: str
) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "authorization_event_id": event_id,
        "authorization_state": "AUTHORIZED",
        "actor_sid": actor_sid,
        "clock_event_sha256": clock.event_sha256,
        "start_utc": clock.start_utc.isoformat().replace("+00:00", "Z"),
        "end_utc": clock.end_utc.isoformat().replace("+00:00", "Z"),
        "duration_days": clock.duration_days,
        "initial_allocation": str(clock.initial_allocation),
        "owner_phrase_sha256": owner_phrase_sha256(),
    }


def _validate_receipt(
    path: Path,
    expected: dict[str, object],
) -> None:
    if not path.is_file():
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_RECEIPT_MISSING")
    try:
        actual = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_RECEIPT_INVALID") from exc
    if actual != expected:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_RECEIPT_MISMATCH")


def create_owner_authorization(
    *,
    db_path: Path,
    phrase: str,
    actor_sid: str,
    elevated: bool,
    receipt_path: Path,
) -> dict[str, object]:
    if phrase != OWNER_PHRASE:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_PHRASE_INVALID")
    if not elevated:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_REQUIRES_ELEVATION")
    if not actor_sid.strip():
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_OWNER_INVALID")

    with Database.open(db_path) as db, db.transaction():
        clock = ExperimentClockStore(db, EXPERIMENT_ID).initialize_or_load(
            requested_start_utc=START_UTC,
            duration_days=DURATION_DAYS,
            initial_allocation=INITIAL_ALLOCATION,
        )
        rows = _authorization_rows(db)
        if not rows:
            event_id = OwnerAuthorizationStore(db, EXPERIMENT_ID).set(
                "AUTHORIZED",
                clock_event_sha256=clock.event_sha256,
                reason=OWNER_PHRASE,
                actor=actor_sid,
            )
        else:
            event_id = _validate_authorization_event(db, clock, actor_sid)

        history = _kill_history(db)
        if not history:
            KillSwitchStore(db).set(
                "KILL_SWITCH_CLEAR",
                reason="explicit Owner authorization for initial launch",
                actor=actor_sid,
            )
        elif history != ("KILL_SWITCH_CLEAR",):
            raise OwnerAuthorizationError("KILL_SWITCH_HISTORY_INVALID")

    payload = _receipt(clock, event_id, actor_sid)
    atomic_authorization_receipt(receipt_path, payload)
    return payload


def validate_owner_authorization(
    *,
    db_path: Path,
    receipt_path: Path,
    expected_actor_sid: str,
) -> dict[str, object]:
    if not db_path.is_file():
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_MISSING")
    with Database.open(db_path) as db:
        clock = _validate_clock(ExperimentClockStore(db, EXPERIMENT_ID).load())
        event_id = _validate_authorization_event(db, clock, expected_actor_sid)
        payload = _receipt(clock, event_id, expected_actor_sid)
    _validate_receipt(receipt_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ibkr_paper_30d.owner_authorization"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--db", type=Path, required=True)
    create_parser.add_argument("--receipt", type=Path, required=True)
    create_parser.add_argument("--phrase", required=True)
    create_parser.add_argument("--actor-sid", required=True)
    create_parser.add_argument("--elevated", action="store_true")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--db", type=Path, required=True)
    validate_parser.add_argument("--receipt", type=Path, required=True)
    validate_parser.add_argument("--actor-sid", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_owner_authorization(
                db_path=args.db,
                receipt_path=args.receipt,
                phrase=args.phrase,
                actor_sid=args.actor_sid,
                elevated=bool(args.elevated),
            )
        else:
            result = validate_owner_authorization(
                db_path=args.db,
                receipt_path=args.receipt,
                expected_actor_sid=args.actor_sid,
            )
    except OwnerAuthorizationError as exc:
        print(
            json.dumps({"status": "BLOCK", "reason": str(exc)}, separators=(",", ":"))
        )
        return 2
    print(
        json.dumps(
            {"status": "PASS", "receipt": result}, sort_keys=True, separators=(",", ":")
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
