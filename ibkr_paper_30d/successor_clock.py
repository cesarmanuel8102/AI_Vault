"""Epoch-scoped clocks and authenticated broker-time validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .experiment_control import ExperimentClock, ExperimentClockStore
from .persistence import Database
from .repositories import utc_now
from .successor_schema import CLOCK_TABLE, verify_successor_schema_v2
from .types import new_uuid7

UTC = timezone.utc
BROKER_TIME_MAX_AGE_SECONDS = 30.0
BROKER_TIME_MAX_FUTURE_SKEW_SECONDS = 5.0
BROKER_TIME_BACKWARD_TOLERANCE_SECONDS = 2.0
CLOCK_SCHEMA_V2 = "EXPERIMENT_EPOCH_CLOCK_START_V2"


class SuccessorClockError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerTimeObservation:
    server_time_utc: datetime | str
    observed_at_utc: datetime
    authenticated: bool
    paper_session: bool
    preceding_server_time_utc: datetime | str | None = None


@dataclass(frozen=True)
class _PriorBrokerTime:
    server_time_utc: datetime
    event_sha256: str


def _parse_utc(value: datetime | str) -> datetime:
    try:
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
    except (TypeError, ValueError) as exc:
        raise SuccessorClockError("BROKER_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SuccessorClockError("BROKER_TIME_INVALID")
    return parsed.astimezone(UTC)


def _table_exists(db: Database, table: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def _verified_v2_rows(db: Database) -> list[tuple[dict[str, Any], str]]:
    if not _table_exists(db, CLOCK_TABLE):
        return []
    verify_successor_schema_v2(db)
    rows = db.execute(
        f"SELECT payload_json,payload_sha256,previous_event_sha256,event_sha256 "
        f"FROM {CLOCK_TABLE} ORDER BY sequence"
    ).fetchall()
    verified: list[tuple[dict[str, Any], str]] = []
    previous_v2: str | None = None
    for index, row in enumerate(rows):
        payload_json, payload_hash, previous, event_hash = map(
            lambda item: None if item is None else str(item), row
        )
        try:
            payload = json.loads(str(payload_json))
        except json.JSONDecodeError as exc:
            raise SuccessorClockError("SUCCESSOR_CLOCK_CHAIN_INVALID") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != CLOCK_SCHEMA_V2
            or sha256_json(payload) != payload_hash
            or sha256_json({"previous_event_sha256": previous, "payload": payload})
            != event_hash
        ):
            raise SuccessorClockError("SUCCESSOR_CLOCK_CHAIN_INVALID")
        if index and previous != previous_v2:
            raise SuccessorClockError("SUCCESSOR_CLOCK_CHAIN_INVALID")
        if not index:
            legacy_hash = payload.get("predecessor_clock_event_sha256")
            if previous != legacy_hash or not isinstance(legacy_hash, str):
                raise SuccessorClockError("SUCCESSOR_CLOCK_CHAIN_INVALID")
            legacy = db.execute(
                "SELECT 1 FROM experiment_clock_events WHERE event_sha256=?",
                (legacy_hash,),
            ).fetchone()
            if legacy is None:
                raise SuccessorClockError("SUCCESSOR_CLOCK_CHAIN_INVALID")
        previous_v2 = event_hash
        verified.append((payload, str(event_hash)))
    return verified


def _authoritative_prior_broker_time(db: Database) -> _PriorBrokerTime | None:
    rows = _verified_v2_rows(db)
    if rows:
        payload, event_sha = rows[-1]
        return _PriorBrokerTime(
            server_time_utc=_parse_utc(str(payload["start_utc"])),
            event_sha256=event_sha,
        )
    legacy = ExperimentClockStore(db).load_legacy()
    if legacy is None:
        return None
    return _PriorBrokerTime(
        server_time_utc=legacy.start_utc,
        event_sha256=legacy.event_sha256,
    )


def validate_broker_time_observation(
    db: Database,
    observation: BrokerTimeObservation,
    *,
    require_prior: bool,
    max_age_seconds: float = BROKER_TIME_MAX_AGE_SECONDS,
    max_future_skew_seconds: float = BROKER_TIME_MAX_FUTURE_SKEW_SECONDS,
    backward_tolerance_seconds: float = BROKER_TIME_BACKWARD_TOLERANCE_SECONDS,
) -> datetime:
    if observation.authenticated is not True:
        raise SuccessorClockError("BROKER_SESSION_NOT_AUTHENTICATED")
    if observation.paper_session is not True:
        raise SuccessorClockError("BROKER_SESSION_NOT_PAPER")
    server_time = _parse_utc(observation.server_time_utc)
    observed_at = _parse_utc(observation.observed_at_utc)
    age_seconds = (observed_at - server_time).total_seconds()
    if age_seconds > max_age_seconds:
        raise SuccessorClockError("BROKER_TIME_STALE")
    if age_seconds < -max_future_skew_seconds:
        raise SuccessorClockError("BROKER_TIME_FUTURE_SKEW")

    # Caller-supplied preceding_server_time_utc is deliberately ignored.
    prior = _authoritative_prior_broker_time(db)
    if prior is None and require_prior:
        raise SuccessorClockError("AUTHORITATIVE_PRIOR_BROKER_TIME_MISSING")
    if prior is not None and server_time < prior.server_time_utc - timedelta(
        seconds=backward_tolerance_seconds
    ):
        raise SuccessorClockError("BROKER_TIME_MOVED_BACKWARD")
    return server_time


def _clock_from_v2_payload(
    payload: dict[str, Any], event_sha256: str
) -> ExperimentClock:
    start = _parse_utc(str(payload["start_utc"]))
    end = _parse_utc(str(payload["end_utc"]))
    duration_days = int(payload["duration_days"])
    if duration_days != 30 or end - start != timedelta(days=duration_days):
        raise SuccessorClockError("SUCCESSOR_CLOCK_DURATION_INVALID")
    return ExperimentClock(
        experiment_id=str(payload["experiment_id"]),
        epoch_id=str(payload["epoch_id"]),
        start_utc=start,
        end_utc=end,
        duration_days=duration_days,
        initial_allocation=Decimal(str(payload["initial_allocation"])),
        event_sha256=event_sha256,
    )


def clock_for_epoch(
    db: Database,
    epoch_id: str,
    *,
    experiment_id: str = "ibkr-paper-30d",
) -> ExperimentClock:
    for payload, event_sha in _verified_v2_rows(db):
        if (
            payload.get("experiment_id") == experiment_id
            and payload.get("epoch_id") == epoch_id
        ):
            return _clock_from_v2_payload(payload, event_sha)

    legacy = ExperimentClockStore(db, experiment_id).load_legacy()
    if legacy is None:
        raise SuccessorClockError("EXPERIMENT_CLOCK_MISSING")
    definitions = db.execute(
        "SELECT payload_json,payload_sha256 FROM state_events "
        "WHERE event_type='EXPERIMENT_EPOCH_DEFINED' ORDER BY sequence"
    ).fetchall()
    for payload_json, payload_hash in definitions:
        try:
            payload = json.loads(str(payload_json))
        except json.JSONDecodeError as exc:
            raise SuccessorClockError("LEGACY_EPOCH_DEFINITION_INVALID") from exc
        if sha256_json(payload) != str(payload_hash):
            raise SuccessorClockError("LEGACY_EPOCH_DEFINITION_INVALID")
        if payload.get("epoch_id") != epoch_id:
            continue
        if (
            _parse_utc(str(payload.get("start_utc"))) != legacy.start_utc
            or _parse_utc(str(payload.get("end_utc"))) != legacy.end_utc
        ):
            raise SuccessorClockError("LEGACY_EPOCH_CLOCK_MISMATCH")
        return ExperimentClock(
            **{
                **legacy.__dict__,
                "epoch_id": epoch_id,
            }
        )
    raise SuccessorClockError("EXPERIMENT_EPOCH_CLOCK_NOT_FOUND")


class SuccessorClockStore:
    def __init__(self, db: Database, experiment_id: str = "ibkr-paper-30d"):
        self.db = db
        self.experiment_id = experiment_id

    def start(
        self,
        *,
        epoch_id: str,
        definition_sha256: str,
        predecessor_epoch_id: str,
        predecessor_clock_event_sha256: str,
        observation: BrokerTimeObservation,
        duration_days: int,
        initial_allocation: Decimal,
        approved_git_head: str,
        owner_authorization_event_id: str,
        owner_authorization_receipt_sha256: str,
    ) -> ExperimentClock:
        verify_successor_schema_v2(self.db)
        if duration_days != 30 or initial_allocation <= 0:
            raise SuccessorClockError("SUCCESSOR_CLOCK_POLICY_INVALID")
        prior = _authoritative_prior_broker_time(self.db)
        if prior is None:
            raise SuccessorClockError("AUTHORITATIVE_PRIOR_BROKER_TIME_MISSING")
        if prior.event_sha256 != predecessor_clock_event_sha256:
            raise SuccessorClockError("PREDECESSOR_CLOCK_HASH_MISMATCH")
        start = validate_broker_time_observation(
            self.db, observation, require_prior=True
        )
        end = start + timedelta(days=duration_days)
        existing = self.db.execute(
            f"SELECT payload_json,event_sha256 FROM {CLOCK_TABLE} "
            "WHERE experiment_id=? AND epoch_id=? AND event_type='START'",
            (self.experiment_id, epoch_id),
        ).fetchone()
        if existing is not None:
            payload = json.loads(str(existing[0]))
            if (
                payload.get("definition_sha256") == definition_sha256
                and payload.get("approved_git_head") == approved_git_head
                and payload.get("owner_authorization_event_id")
                == owner_authorization_event_id
                and payload.get("owner_authorization_receipt_sha256")
                == owner_authorization_receipt_sha256
                and payload.get("predecessor_clock_event_sha256")
                == predecessor_clock_event_sha256
                and _parse_utc(str(payload.get("start_utc"))) == start
            ):
                return _clock_from_v2_payload(payload, str(existing[1]))
            raise SuccessorClockError("SUCCESSOR_CLOCK_CONFLICT")

        payload = {
            "schema": CLOCK_SCHEMA_V2,
            "experiment_id": self.experiment_id,
            "epoch_id": epoch_id,
            "definition_sha256": definition_sha256,
            "predecessor_epoch_id": predecessor_epoch_id,
            "predecessor_clock_event_sha256": predecessor_clock_event_sha256,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_utc": end.isoformat().replace("+00:00", "Z"),
            "duration_days": duration_days,
            "initial_allocation": str(initial_allocation),
            "approved_git_head": approved_git_head,
            "owner_authorization_event_id": owner_authorization_event_id,
            "owner_authorization_receipt_sha256": (owner_authorization_receipt_sha256),
            "start_authority": "BROKER_SERVER_TIME",
            "created_at_utc": utc_now(),
        }
        event_sha = sha256_json(
            {"previous_event_sha256": prior.event_sha256, "payload": payload}
        )
        self.db.execute(
            f"INSERT INTO {CLOCK_TABLE}("
            "event_id,experiment_id,epoch_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                self.experiment_id,
                epoch_id,
                "START",
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                prior.event_sha256,
                event_sha,
                utc_now(),
            ),
        )
        return _clock_from_v2_payload(payload, event_sha)
