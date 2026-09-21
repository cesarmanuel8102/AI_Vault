from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class ExperimentControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExperimentClock:
    experiment_id: str
    start_utc: datetime
    end_utc: datetime
    duration_days: int
    initial_allocation: Decimal
    event_sha256: str

    def snapshot(self, now: datetime) -> dict[str, Any]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)
        elapsed = max((now - self.start_utc).total_seconds(), 0.0)
        remaining = max((self.end_utc - now).total_seconds(), 0.0)
        return {
            "experiment_id": self.experiment_id,
            "start_utc": self.start_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": self.end_utc.isoformat().replace("+00:00", "Z"),
            "now_utc": now.isoformat().replace("+00:00", "Z"),
            "duration_days": self.duration_days,
            "elapsed_days": elapsed / 86400.0,
            "remaining_days": remaining / 86400.0,
            "remaining_seconds": remaining,
            "expired": remaining <= 0,
            "clock_event_sha256": self.event_sha256,
        }


class ExperimentClockStore:
    SCHEMA = "EXPERIMENT_CLOCK_START_V1"

    def __init__(self, db: Database, experiment_id: str = "ibkr-paper-30d"):
        self.db = db
        self.experiment_id = experiment_id

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ExperimentControlError("EXPERIMENT_CLOCK_TIMESTAMP_INVALID")
        return parsed.astimezone(timezone.utc)

    def load(self) -> ExperimentClock | None:
        row = self.db.execute(
            "SELECT payload_json,event_sha256 FROM experiment_clock_events "
            "WHERE experiment_id=? ORDER BY sequence ASC LIMIT 1",
            (self.experiment_id,),
        ).fetchone()
        if row is None:
            return None
        payload_json, stored_event_sha = map(str, row)
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise ExperimentControlError("EXPERIMENT_CLOCK_CORRUPT") from exc
        if payload.get("schema") != self.SCHEMA:
            raise ExperimentControlError("EXPERIMENT_CLOCK_SCHEMA_INVALID")
        expected_event_sha = sha256_json(
            {"previous_event_sha256": None, "payload": payload}
        )
        if expected_event_sha != stored_event_sha:
            raise ExperimentControlError("EXPERIMENT_CLOCK_HASH_MISMATCH")
        return ExperimentClock(
            experiment_id=str(payload["experiment_id"]),
            start_utc=self._parse_utc(str(payload["start_utc"])),
            end_utc=self._parse_utc(str(payload["end_utc"])),
            duration_days=int(payload["duration_days"]),
            initial_allocation=Decimal(str(payload["initial_allocation"])),
            event_sha256=stored_event_sha,
        )

    def initialize_or_load(
        self,
        *,
        requested_start_utc: datetime | None,
        duration_days: int,
        initial_allocation: Decimal,
    ) -> ExperimentClock:
        existing = self.load()
        if existing is not None:
            if duration_days != existing.duration_days:
                raise ExperimentControlError("EXPERIMENT_DURATION_IMMUTABLE")
            if initial_allocation != existing.initial_allocation:
                raise ExperimentControlError("EXPERIMENT_ALLOCATION_IMMUTABLE")
            if requested_start_utc is not None:
                normalized = requested_start_utc.astimezone(timezone.utc)
                if normalized != existing.start_utc:
                    raise ExperimentControlError("EXPERIMENT_START_IMMUTABLE")
            return existing

        if requested_start_utc is None:
            raise ExperimentControlError("EXPERIMENT_START_REQUIRED_FOR_FIRST_RUN")
        if requested_start_utc.tzinfo is None or requested_start_utc.utcoffset() is None:
            raise ExperimentControlError("EXPERIMENT_START_MUST_BE_TIMEZONE_AWARE")
        if duration_days <= 0:
            raise ExperimentControlError("EXPERIMENT_DURATION_INVALID")
        if initial_allocation <= 0:
            raise ExperimentControlError("EXPERIMENT_ALLOCATION_INVALID")

        start = requested_start_utc.astimezone(timezone.utc)
        end = start + timedelta(days=duration_days)
        payload = {
            "schema": self.SCHEMA,
            "experiment_id": self.experiment_id,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_utc": end.isoformat().replace("+00:00", "Z"),
            "duration_days": duration_days,
            "initial_allocation": str(initial_allocation),
            "created_at_utc": utc_now(),
        }
        payload_json = canonical_bytes(payload).decode("utf-8")
        event_sha = sha256_json(
            {"previous_event_sha256": None, "payload": payload}
        )
        self.db.execute(
            "INSERT INTO experiment_clock_events("
            "event_id,experiment_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                self.experiment_id,
                "START",
                payload_json,
                sha256_json(payload),
                None,
                event_sha,
                utc_now(),
            ),
        )
        return ExperimentClock(
            experiment_id=self.experiment_id,
            start_utc=start,
            end_utc=end,
            duration_days=duration_days,
            initial_allocation=initial_allocation,
            event_sha256=event_sha,
        )


class KillSwitchStore:
    VALID_STATES = frozenset({"KILL_SWITCH_CLEAR", "KILL_SWITCH_TRIGGERED"})

    def __init__(self, db: Database):
        self.db = db

    def current(self) -> str:
        row = self.db.execute(
            "SELECT state FROM kill_switch_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return "KILL_SWITCH_TRIGGERED"
        state = str(row[0])
        return state if state in self.VALID_STATES else "KILL_SWITCH_TRIGGERED"

    def set(self, state: str, *, reason: str, actor: str = "operator") -> str:
        if state not in self.VALID_STATES:
            raise ValueError("invalid kill-switch state")
        payload = {
            "schema": "KILL_SWITCH_EVENT_V1",
            "state": state,
            "reason": reason,
            "actor": actor,
            "created_at_utc": utc_now(),
        }
        event_id = str(new_uuid7())
        self.db.execute(
            "INSERT INTO kill_switch_events("
            "event_id,state,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?)",
            (
                event_id,
                state,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                utc_now(),
            ),
        )
        return event_id


@dataclass(frozen=True)
class RuntimeGateState:
    auditor_gate: str
    auditor_reason_codes: tuple[str, ...]
    market_data_gate: str
    market_reason_codes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.auditor_gate == "PASS" and self.market_data_gate == "PASS"
