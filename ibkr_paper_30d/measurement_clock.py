"""Owner-authorized economic horizon layered over immutable epoch authority."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from .canonical import sha256_json
from .experiment_control import ExperimentClock
from .persistence import Database
from .repositories import EventRepository
from .successor_clock import (
    BrokerTimeObservation,
    SuccessorClockError,
    validate_broker_time_observation,
)


SCHEMA = "EXPERIMENT_MEASUREMENT_CLOCK_STARTED_V1"
EVENT_TYPE = "EXPERIMENT_MEASUREMENT_CLOCK_STARTED"
EXPERIMENT_ID = "ibkr-paper-30d"
_GIT_HEAD = re.compile(r"^[0-9a-f]{40}$")


class MeasurementClockError(RuntimeError):
    pass


def _format(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise MeasurementClockError("MEASUREMENT_CLOCK_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MeasurementClockError("MEASUREMENT_CLOCK_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


class MeasurementClockStore:
    def __init__(self, db: Database, experiment_id: str = EXPERIMENT_ID) -> None:
        self.db = db
        self.experiment_id = experiment_id

    def _payload(self) -> dict[str, Any] | None:
        rows = self.db.execute(
            "SELECT payload_json,payload_sha256 FROM state_events "
            "WHERE event_type=? ORDER BY sequence",
            (EVENT_TYPE,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise MeasurementClockError("MEASUREMENT_CLOCK_CARDINALITY_INVALID")
        try:
            payload = json.loads(str(rows[0][0]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MeasurementClockError("MEASUREMENT_CLOCK_CORRUPT") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != SCHEMA
            or sha256_json(payload) != str(rows[0][1])
        ):
            raise MeasurementClockError("MEASUREMENT_CLOCK_HASH_MISMATCH")
        return payload

    def load(self, base_clock: ExperimentClock) -> ExperimentClock | None:
        payload = self._payload()
        if payload is None:
            return None
        if (
            payload.get("experiment_id") != self.experiment_id
            or payload.get("epoch_id") != base_clock.epoch_id
            or payload.get("base_clock_event_sha256") != base_clock.event_sha256
            or int(payload.get("duration_days", 0)) != 30
            or payload.get("owner_authorized") is not True
            or payload.get("paper_session") is not True
            or payload.get("broker_time_authenticated") is not True
        ):
            raise MeasurementClockError("MEASUREMENT_CLOCK_BINDING_MISMATCH")
        start = _parse(payload.get("start_utc"))
        end = _parse(payload.get("end_utc"))
        if end - start != timedelta(days=30):
            raise MeasurementClockError("MEASUREMENT_CLOCK_DURATION_INVALID")
        return replace(base_clock, start_utc=start, end_utc=end, duration_days=30)

    def present(self) -> bool:
        return self._payload() is not None

    def effective(self, base_clock: ExperimentClock) -> ExperimentClock:
        return self.load(base_clock) or base_clock

    def start(
        self,
        *,
        base_clock: ExperimentClock,
        observation: BrokerTimeObservation,
        approved_git_head: str,
        actor_sid: str,
        owner_authorized: bool,
    ) -> ExperimentClock:
        if owner_authorized is not True:
            raise MeasurementClockError(
                "MEASUREMENT_CLOCK_OWNER_AUTHORIZATION_REQUIRED"
            )
        if not actor_sid.strip():
            raise MeasurementClockError("MEASUREMENT_CLOCK_OWNER_INVALID")
        if not _GIT_HEAD.fullmatch(approved_git_head):
            raise MeasurementClockError("MEASUREMENT_CLOCK_GIT_HEAD_INVALID")
        if (
            base_clock.experiment_id != self.experiment_id
            or not base_clock.epoch_id
            or not re.fullmatch(r"[0-9a-f]{64}", base_clock.event_sha256)
        ):
            raise MeasurementClockError("MEASUREMENT_CLOCK_BASE_AUTHORITY_INVALID")
        try:
            start = validate_broker_time_observation(
                self.db, observation, require_prior=False
            )
        except SuccessorClockError as exc:
            raise MeasurementClockError(str(exc)) from exc
        payload = {
            "schema": SCHEMA,
            "experiment_id": self.experiment_id,
            "epoch_id": base_clock.epoch_id,
            "base_clock_event_sha256": base_clock.event_sha256,
            "start_utc": _format(start),
            "end_utc": _format(start + timedelta(days=30)),
            "duration_days": 30,
            "initial_allocation": str(base_clock.initial_allocation),
            "approved_git_head": approved_git_head,
            "actor_sid": actor_sid,
            "owner_authorized": True,
            "start_authority": "BROKER_SERVER_TIME",
            "broker_time_authenticated": observation.authenticated,
            "paper_session": observation.paper_session,
            "observed_at_utc": _format(observation.observed_at_utc),
            "economic_state_policy": "CARRY_FORWARD_WITHOUT_RESET",
        }
        existing = self._payload()
        if existing is not None:
            if existing != payload:
                raise MeasurementClockError("MEASUREMENT_CLOCK_CONFLICT")
            loaded = self.load(base_clock)
            assert loaded is not None
            return loaded
        with self.db.transaction():
            EventRepository(self.db).append(EVENT_TYPE, payload)
        loaded = self.load(base_clock)
        if loaded is None:
            raise MeasurementClockError("MEASUREMENT_CLOCK_PERSISTENCE_FAILED")
        return loaded
