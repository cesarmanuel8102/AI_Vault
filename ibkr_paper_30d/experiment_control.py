from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

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
    epoch_id: str | None = None

    def snapshot(self, now: datetime) -> dict[str, Any]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)
        not_started = now < self.start_utc
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
            "not_started": not_started,
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

    def load_legacy(self) -> ExperimentClock | None:
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

    def load(self) -> ExperimentClock | None:
        v2_table = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='experiment_epoch_clock_events_v2'"
        ).fetchone()
        if v2_table is not None:
            v2_count = int(
                self.db.execute(
                    "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
                ).fetchone()[0]
            )
            if v2_count:
                raise ExperimentControlError("EXPERIMENT_CLOCK_EPOCH_REQUIRED")
        return self.load_legacy()

    def clock_for_epoch(self, epoch_id: str) -> ExperimentClock:
        from .successor_clock import clock_for_epoch

        return clock_for_epoch(self.db, epoch_id, experiment_id=self.experiment_id)

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
        if (
            requested_start_utc.tzinfo is None
            or requested_start_utc.utcoffset() is None
        ):
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
        event_sha = sha256_json({"previous_event_sha256": None, "payload": payload})
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
    RECOVERY_RECEIPT_SCHEMA = "KILL_SWITCH_RECOVERY_RECEIPT_V1"
    RECOVERY_EVENT_SCHEMA = "KILL_SWITCH_RECOVERY_EVENT_V1"
    _SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
    _HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
    _REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")

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
        if state == "KILL_SWITCH_CLEAR":
            existing = self.db.execute(
                "SELECT 1 FROM kill_switch_events LIMIT 1"
            ).fetchone()
            if existing is not None:
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_REQUIRED")
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

    @staticmethod
    def _parse_utc(value: object, code: str) -> datetime:
        if not isinstance(value, str):
            raise ExperimentControlError(code)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExperimentControlError(code) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ExperimentControlError(code)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _validate_recovery_receipt(
        cls,
        receipt: object,
        *,
        trigger_event_id: str,
        trigger_payload_sha256: str,
        expected_owner_sid: str,
        expected_account_identity_sha256: str,
        expected_approved_head: str | None,
        expected_authorization_event_id: str,
        expected_clock_event_sha256: str,
        now_utc: datetime | None,
    ) -> dict[str, object]:
        if not isinstance(receipt, dict):
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_INVALID")
        if receipt.get("schema") != cls.RECOVERY_RECEIPT_SCHEMA:
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_INVALID")
        bindings = (
            ("trigger_event_id", trigger_event_id, "KILL_SWITCH_RECOVERY_TRIGGER_MISMATCH"),
            (
                "trigger_payload_sha256",
                trigger_payload_sha256,
                "KILL_SWITCH_RECOVERY_TRIGGER_MISMATCH",
            ),
            ("owner_sid", expected_owner_sid, "KILL_SWITCH_RECOVERY_OWNER_MISMATCH"),
            (
                "account_identity_sha256",
                expected_account_identity_sha256,
                "KILL_SWITCH_RECOVERY_ACCOUNT_MISMATCH",
            ),
            (
                "authorization_event_id",
                expected_authorization_event_id,
                "KILL_SWITCH_RECOVERY_AUTHORIZATION_MISMATCH",
            ),
            (
                "clock_event_sha256",
                expected_clock_event_sha256,
                "KILL_SWITCH_RECOVERY_CLOCK_MISMATCH",
            ),
        )
        for field, expected, code in bindings:
            if receipt.get(field) != expected:
                raise ExperimentControlError(code)
        receipt_head = str(receipt.get("approved_head", ""))
        if not cls._HEAD_RE.fullmatch(receipt_head):
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_HEAD_MISMATCH")
        if expected_approved_head is not None and receipt_head != expected_approved_head:
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_HEAD_MISMATCH")
        for field in (
            "trigger_payload_sha256",
            "account_identity_sha256",
            "clock_event_sha256",
            "broker_evidence_sha256",
        ):
            if not cls._SHA256_RE.fullmatch(str(receipt.get(field, ""))):
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_INVALID")
        reason = receipt.get("recovery_reason_code")
        if not isinstance(reason, str) or not cls._REASON_RE.fullmatch(reason):
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_REASON_INVALID")
        for field in ("positions_count", "open_orders_count", "executions_count", "broker_write_count"):
            value = receipt.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_INVALID")
        if receipt["open_orders_count"] != 0:
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_OPEN_ORDERS_PRESENT")
        if receipt["broker_write_count"] != 0:
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_BROKER_WRITE_DETECTED")
        completeness = receipt.get("query_completeness")
        required_queries = {
            "managed_accounts",
            "positions",
            "open_orders",
            "executions",
            "current_time",
        }
        if not isinstance(completeness, dict) or any(
            completeness.get(name) is not True for name in required_queries
        ):
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECONCILIATION_INCOMPLETE")
        server_time = cls._parse_utc(
            receipt.get("broker_server_time_utc"),
            "KILL_SWITCH_RECOVERY_BROKER_TIME_INVALID",
        )
        collected = cls._parse_utc(
            receipt.get("collected_at_utc"),
            "KILL_SWITCH_RECOVERY_TIMESTAMP_INVALID",
        )
        expires = cls._parse_utc(
            receipt.get("expires_at_utc"),
            "KILL_SWITCH_RECOVERY_TIMESTAMP_INVALID",
        )
        if expires <= collected or abs((collected - server_time).total_seconds()) > 30:
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_TIMESTAMP_INVALID")
        if now_utc is not None:
            if now_utc.tzinfo is None or now_utc.utcoffset() is None:
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_TIMESTAMP_INVALID")
            normalized_now = now_utc.astimezone(timezone.utc)
            if collected > normalized_now + timedelta(seconds=5):
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_TIMESTAMP_INVALID")
            if expires < normalized_now:
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_EVIDENCE_STALE")
        return dict(receipt)

    def recover(
        self,
        receipt: object,
        *,
        now_utc: datetime,
        expected_owner_sid: str,
        expected_account_identity_sha256: str,
        expected_approved_head: str,
        expected_authorization_event_id: str,
        expected_clock_event_sha256: str,
        precommit_verifier: Callable[[Database], None] | None = None,
    ) -> str:
        with self.db.transaction():
            if precommit_verifier is not None:
                precommit_verifier(self.db)
            from .successor_epoch import current_epoch_authority_bindings

            successor = current_epoch_authority_bindings(self.db)
            if successor is not None:
                if (
                    successor["authorization_event_id"]
                    != expected_authorization_event_id
                ):
                    raise ExperimentControlError(
                        "KILL_SWITCH_RECOVERY_AUTHORIZATION_CHANGED"
                    )
                if successor["clock_event_sha256"] != expected_clock_event_sha256:
                    raise ExperimentControlError("KILL_SWITCH_RECOVERY_CLOCK_CHANGED")
            else:
                authorization = self.db.execute(
                    "SELECT event_id,state,clock_event_sha256 "
                    "FROM experiment_authorization_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if authorization is not None:
                    if str(authorization[0]) != expected_authorization_event_id:
                        raise ExperimentControlError(
                            "KILL_SWITCH_RECOVERY_AUTHORIZATION_CHANGED"
                        )
                    if (
                        str(authorization[1]) != "AUTHORIZED"
                        or str(authorization[2]) != expected_clock_event_sha256
                    ):
                        raise ExperimentControlError(
                            "KILL_SWITCH_RECOVERY_AUTHORIZATION_INVALID"
                        )
                    clock = ExperimentClockStore(self.db).load()
                    if (
                        clock is None
                        or clock.event_sha256 != expected_clock_event_sha256
                    ):
                        raise ExperimentControlError(
                            "KILL_SWITCH_RECOVERY_CLOCK_CHANGED"
                        )
            row = self.db.execute(
                "SELECT event_id,state,payload_sha256 FROM kill_switch_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row is None or str(row[1]) != "KILL_SWITCH_TRIGGERED":
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_TRIGGER_REQUIRED")
            trigger_event_id, _, trigger_payload_sha256 = map(str, row)
            normalized = self._validate_recovery_receipt(
                receipt,
                trigger_event_id=trigger_event_id,
                trigger_payload_sha256=trigger_payload_sha256,
                expected_owner_sid=expected_owner_sid,
                expected_account_identity_sha256=expected_account_identity_sha256,
                expected_approved_head=expected_approved_head,
                expected_authorization_event_id=expected_authorization_event_id,
                expected_clock_event_sha256=expected_clock_event_sha256,
                now_utc=now_utc,
            )
            payload = {
                "schema": self.RECOVERY_EVENT_SCHEMA,
                "state": "KILL_SWITCH_CLEAR",
                "reason": normalized["recovery_reason_code"],
                "actor": expected_owner_sid,
                "recovery_receipt": normalized,
                "recovery_receipt_sha256": sha256_json(normalized),
                "created_at_utc": utc_now(),
            }
            event_id = str(new_uuid7())
            self.db.execute(
                "INSERT INTO kill_switch_events("
                "event_id,state,payload_json,payload_sha256,created_at_utc"
                ") VALUES(?,?,?,?,?)",
                (
                    event_id,
                    "KILL_SWITCH_CLEAR",
                    canonical_bytes(payload).decode("utf-8"),
                    sha256_json(payload),
                    utc_now(),
                ),
            )
            return event_id

    def validate_history(
        self,
        *,
        expected_owner_sid: str,
        expected_account_identity_sha256: str,
        expected_approved_head: str,
        expected_authorization_event_id: str,
        expected_clock_event_sha256: str,
    ) -> str:
        if not self._HEAD_RE.fullmatch(expected_approved_head):
            raise ExperimentControlError("KILL_SWITCH_RECOVERY_HEAD_MISMATCH")
        rows = self.db.execute(
            "SELECT event_id,state,payload_json,payload_sha256 "
            "FROM kill_switch_events ORDER BY sequence"
        ).fetchall()
        if not rows:
            raise ExperimentControlError("KILL_SWITCH_TRIGGERED")
        pending_trigger: tuple[str, str] | None = None
        for index, row in enumerate(rows):
            event_id, state, payload_json, payload_sha256 = map(str, row)
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                raise ExperimentControlError("KILL_SWITCH_EVENT_INVALID") from exc
            if not isinstance(payload, dict) or sha256_json(payload) != payload_sha256:
                raise ExperimentControlError("KILL_SWITCH_EVENT_HASH_MISMATCH")
            if payload.get("state") != state:
                raise ExperimentControlError("KILL_SWITCH_EVENT_INVALID")
            if index == 0:
                if state != "KILL_SWITCH_CLEAR" or payload.get("schema") != "KILL_SWITCH_EVENT_V1":
                    raise ExperimentControlError("KILL_SWITCH_HISTORY_INVALID")
                continue
            if state == "KILL_SWITCH_TRIGGERED":
                if pending_trigger is not None or payload.get("schema") != "KILL_SWITCH_EVENT_V1":
                    raise ExperimentControlError("KILL_SWITCH_HISTORY_INVALID")
                pending_trigger = (event_id, payload_sha256)
                continue
            if state != "KILL_SWITCH_CLEAR" or pending_trigger is None:
                raise ExperimentControlError("KILL_SWITCH_HISTORY_INVALID")
            if payload.get("schema") != self.RECOVERY_EVENT_SCHEMA:
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_REQUIRED")
            # A recovery receipt is immutable evidence for the deployment that
            # performed the recovery. Later approved deployments must not
            # rewrite that historical authority decision.
            receipt = self._validate_recovery_receipt(
                payload.get("recovery_receipt"),
                trigger_event_id=pending_trigger[0],
                trigger_payload_sha256=pending_trigger[1],
                expected_owner_sid=expected_owner_sid,
                expected_account_identity_sha256=expected_account_identity_sha256,
                expected_approved_head=None,
                expected_authorization_event_id=expected_authorization_event_id,
                expected_clock_event_sha256=expected_clock_event_sha256,
                now_utc=None,
            )
            if payload.get("recovery_receipt_sha256") != sha256_json(receipt):
                raise ExperimentControlError("KILL_SWITCH_RECOVERY_RECEIPT_HASH_MISMATCH")
            pending_trigger = None
        if pending_trigger is not None:
            raise ExperimentControlError("KILL_SWITCH_TRIGGERED")
        return "KILL_SWITCH_CLEAR"


@dataclass(frozen=True)
class RuntimeGateState:
    auditor_gate: str
    auditor_reason_codes: tuple[str, ...]
    market_data_gate: str
    market_reason_codes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.auditor_gate == "PASS" and self.market_data_gate == "PASS"


class OwnerAuthorizationStore:
    """Append-only owner authorization bound to the persisted experiment clock."""

    SCHEMA = "EXPERIMENT_OWNER_AUTHORIZATION_V1"

    def __init__(self, db: Database, experiment_id: str = "ibkr-paper-30d"):
        self.db = db
        self.experiment_id = experiment_id

    def current(self, *, clock_event_sha256: str) -> str:
        row = self.db.execute(
            "SELECT state,clock_event_sha256 FROM experiment_authorization_events "
            "WHERE experiment_id=? ORDER BY sequence DESC LIMIT 1",
            (self.experiment_id,),
        ).fetchone()
        if row is None:
            return "NOT_AUTHORIZED"
        state, bound_clock = map(str, row)
        if bound_clock != clock_event_sha256:
            return "NOT_AUTHORIZED"
        return state

    def set(
        self,
        state: str,
        *,
        clock_event_sha256: str,
        reason: str,
        actor: str = "owner",
    ) -> str:
        if state not in {"AUTHORIZED", "REVOKED"}:
            raise ValueError("invalid owner authorization state")
        if len(clock_event_sha256) != 64:
            raise ValueError("clock_event_sha256 must be a SHA-256 hex digest")
        payload = {
            "schema": self.SCHEMA,
            "experiment_id": self.experiment_id,
            "state": state,
            "clock_event_sha256": clock_event_sha256,
            "reason": reason,
            "actor": actor,
            "created_at_utc": utc_now(),
        }
        event_id = str(new_uuid7())
        self.db.execute(
            "INSERT INTO experiment_authorization_events("
            "event_id,experiment_id,state,clock_event_sha256,payload_json,"
            "payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?)",
            (
                event_id,
                self.experiment_id,
                state,
                clock_event_sha256,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                utc_now(),
            ),
        )
        return event_id
