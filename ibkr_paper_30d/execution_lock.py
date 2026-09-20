from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import win32api
import win32event
from pydantic import BaseModel, ConfigDict

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .types import new_uuid7


MUTEX_NAME = r"Local\CodexIbkrPaper30DExecutionLockV1"
LOCK_PROJECTION_ID = "EXECUTION_LOCK_V1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LockOwner(BaseModel, frozen=True):
    owner_id: str
    pid: int
    process_start: str
    host_fingerprint: str
    boot_session_id: str


class LockReceipt(BaseModel, frozen=True):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    acquired: bool
    reason: str
    owner_id: str
    generation: int
    recovery_required: bool = False
    abandoned: bool = False
    handle: Any = None


class HeartbeatReceipt(BaseModel, frozen=True):
    accepted: bool
    reason: str


class ReleaseReceipt(BaseModel, frozen=True):
    released: bool
    reason: str


class RecoveryReceipt(BaseModel, frozen=True):
    recovered: bool
    state: str
    order_authority: bool = False
    reason: str


class ExecutionLock:
    def __init__(self, db: Database, mutex_name: str = MUTEX_NAME):
        self.db = db
        self.mutex_name = mutex_name

    def _projection(self) -> tuple[int, dict[str, object]] | None:
        row = self.db.execute(
            "SELECT version,payload_json FROM experiment_state WHERE experiment_id=?",
            (LOCK_PROJECTION_ID,),
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), json.loads(str(row[1]))

    def _write_projection(self, version: int, payload: dict[str, object]) -> None:
        encoded = canonical_bytes(payload).decode("utf-8")
        digest = sha256_json(payload)
        self.db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES(?,?,?,?,?) ON CONFLICT(experiment_id) DO UPDATE SET "
            "version=excluded.version,payload_json=excluded.payload_json,"
            "payload_sha256=excluded.payload_sha256,updated_at_utc=excluded.updated_at_utc",
            (LOCK_PROJECTION_ID, version, encoded, digest, utc_now()),
        )

    def _append_event(
        self, generation: int, event_type: str, payload: dict[str, object]
    ) -> None:
        event_id = str(new_uuid7())
        encoded = canonical_bytes(payload).decode("utf-8")
        self.db.execute(
            "INSERT INTO execution_lock_events(event_id,generation,event_type,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?)",
            (event_id, generation, event_type, encoded, sha256_json(payload), utc_now()),
        )

    @staticmethod
    def _close_unowned_handle(handle: Any, owns_mutex: bool) -> None:
        if owns_mutex:
            try:
                win32event.ReleaseMutex(handle)
            except Exception:
                pass
        win32api.CloseHandle(handle)

    def acquire(self, owner: LockOwner) -> LockReceipt:
        handle = win32event.CreateMutex(None, False, self.mutex_name)
        wait = win32event.WaitForSingleObject(handle, 0)
        if wait == win32event.WAIT_TIMEOUT:
            win32api.CloseHandle(handle)
            return LockReceipt(
                acquired=False,
                reason="OS_MUTEX_HELD",
                owner_id=owner.owner_id,
                generation=0,
            )
        if wait == win32event.WAIT_ABANDONED:
            projection = self._projection()
            generation = 0 if projection is None else int(projection[1].get("generation", 0))
            self._append_event(
                generation,
                "ABANDONED_MUTEX_DETECTED",
                {"owner_id": owner.owner_id, "order_authority": False},
            )
            self._close_unowned_handle(handle, owns_mutex=True)
            return LockReceipt(
                acquired=False,
                reason="ABANDONED_MUTEX",
                owner_id=owner.owner_id,
                generation=generation,
                recovery_required=True,
                abandoned=True,
            )
        if wait != win32event.WAIT_OBJECT_0:
            win32api.CloseHandle(handle)
            return LockReceipt(
                acquired=False,
                reason="OS_MUTEX_ERROR",
                owner_id=owner.owner_id,
                generation=0,
                recovery_required=True,
            )

        with self.db.transaction():
            projection = self._projection()
            previous_version = 0 if projection is None else projection[0]
            previous_payload = {} if projection is None else projection[1]
            if previous_payload.get("state") == "ACTIVE":
                generation = int(previous_payload.get("generation", 0))
                self._append_event(
                    generation,
                    "ACTIVE_RECORD_CONFLICT",
                    {"attempted_owner_id": owner.owner_id, "order_authority": False},
                )
                self._close_unowned_handle(handle, owns_mutex=True)
                return LockReceipt(
                    acquired=False,
                    reason="LOCK_RECORD_ACTIVE",
                    owner_id=owner.owner_id,
                    generation=generation,
                    recovery_required=True,
                )
            generation = int(previous_payload.get("generation", 0)) + 1
            payload = {
                "state": "ACTIVE",
                **owner.model_dump(),
                "generation": generation,
                "acquired_at_utc": utc_now(),
                "heartbeat_at_utc": utc_now(),
                "order_authority": False,
            }
            self._write_projection(previous_version + 1, payload)
            self._append_event(generation, "ACQUIRED", payload)
        return LockReceipt(
            acquired=True,
            reason="ACQUIRED",
            owner_id=owner.owner_id,
            generation=generation,
            handle=handle,
        )

    def heartbeat(self, receipt: LockReceipt) -> HeartbeatReceipt:
        projection = self._projection()
        if projection is None:
            return HeartbeatReceipt(accepted=False, reason="NO_ACTIVE_OWNER")
        version, payload = projection
        if (
            payload.get("state") != "ACTIVE"
            or payload.get("owner_id") != receipt.owner_id
            or int(payload.get("generation", -1)) != receipt.generation
        ):
            return HeartbeatReceipt(accepted=False, reason="OWNER_MISMATCH")
        payload["heartbeat_at_utc"] = utc_now()
        with self.db.transaction():
            self._write_projection(version + 1, payload)
            self._append_event(receipt.generation, "HEARTBEAT", payload)
        return HeartbeatReceipt(accepted=True, reason="ACCEPTED")

    def release(self, receipt: LockReceipt) -> ReleaseReceipt:
        projection = self._projection()
        if projection is None:
            return ReleaseReceipt(released=False, reason="NO_ACTIVE_OWNER")
        version, payload = projection
        if (
            payload.get("state") != "ACTIVE"
            or payload.get("owner_id") != receipt.owner_id
            or int(payload.get("generation", -1)) != receipt.generation
        ):
            return ReleaseReceipt(released=False, reason="OWNER_MISMATCH")
        payload["state"] = "RELEASED"
        payload["released_at_utc"] = utc_now()
        with self.db.transaction():
            self._write_projection(version + 1, payload)
            self._append_event(receipt.generation, "RELEASED", payload)
        if receipt.handle is not None:
            self._close_unowned_handle(receipt.handle, owns_mutex=True)
        return ReleaseReceipt(released=True, reason="RELEASED")

    def recover_stale(
        self,
        stale: LockOwner,
        observed: LockOwner | None,
        *,
        mutex_is_free: bool,
    ) -> RecoveryReceipt:
        if not mutex_is_free:
            return RecoveryReceipt(
                recovered=False,
                state="EXECUTION_LOCK_AMBIGUOUS",
                reason="MUTEX_STILL_HELD",
            )
        if observed is not None:
            reason = "PID_REUSED" if stale.pid == observed.pid else "OWNER_STILL_OBSERVED"
            return RecoveryReceipt(
                recovered=False,
                state="EXECUTION_LOCK_AMBIGUOUS",
                reason=reason,
            )
        projection = self._projection()
        generation = 0 if projection is None else int(projection[1].get("generation", 0))
        with self.db.transaction():
            current_version = 0 if projection is None else projection[0]
            payload = {
                "state": "RECOVERY_REQUIRED",
                "stale_owner_id": stale.owner_id,
                "generation": generation,
                "order_authority": False,
                "detected_at_utc": utc_now(),
            }
            self._write_projection(current_version + 1, payload)
            self._append_event(generation, "STALE_OWNER_CONFIRMED", payload)
        return RecoveryReceipt(
            recovered=True,
            state="SYSTEM_RECOVERING",
            order_authority=False,
            reason="STALE_OWNER_CONFIRMED",
        )
