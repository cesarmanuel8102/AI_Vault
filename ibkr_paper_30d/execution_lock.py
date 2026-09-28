from __future__ import annotations

import json
import os
import hashlib
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

import win32api
import win32event
from pydantic import BaseModel, ConfigDict

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .types import new_uuid7


MUTEX_NAME = r"Local\CodexIbkrPaper30DExecutionLockV1"
LOCK_PROJECTION_ID = "EXECUTION_LOCK_V1"
DEFAULT_STALE_AFTER = timedelta(minutes=2)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LockOwner(BaseModel, frozen=True):
    owner_id: str
    pid: int
    process_start: str
    host_fingerprint: str
    boot_session_id: str


class ObservedProcess(BaseModel, frozen=True):
    pid: int
    process_start: str
    host_fingerprint: str
    boot_session_id: str


class ProcessObserver(Protocol):
    def observe(self, pid: int) -> ObservedProcess | None: ...

    def has_other_execution_authority(self, *, excluding_pid: int) -> bool | None: ...

    def current_boot_session_id(self) -> str: ...


class LockInspection(BaseModel, frozen=True):
    state: str
    reason: str
    generation: int
    heartbeat_stale: bool | None
    process_state: str
    order_authority_clear: bool


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


class LockIntegrityError(RuntimeError):
    pass


def _timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _host_fingerprint() -> str:
    return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()


def _boot_session_id() -> str:
    import psutil

    return hashlib.sha256(str(int(psutil.boot_time())).encode("ascii")).hexdigest()


class WindowsProcessObserver:
    """Read-only liveness observer. Incomplete access is reported as ambiguous."""

    def observe(self, pid: int) -> ObservedProcess | None:
        import psutil

        try:
            process = psutil.Process(pid)
            created = process.create_time()
        except psutil.NoSuchProcess:
            return None
        except (psutil.AccessDenied, OSError) as exc:
            raise RuntimeError("PROCESS_LIVENESS_AMBIGUOUS") from exc
        return ObservedProcess(
            pid=pid,
            process_start=_timestamp(created),
            host_fingerprint=_host_fingerprint(),
            boot_session_id=_boot_session_id(),
        )

    def has_other_execution_authority(self, *, excluding_pid: int) -> bool | None:
        import psutil

        markers = (
            "ibkr_paper_30d.day1_launch",
            "run_ibkr_day1_service.ps1",
        )
        excluded = {excluding_pid}
        try:
            excluded.update(parent.pid for parent in psutil.Process(excluding_pid).parents())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return None
        for process in psutil.process_iter(("pid", "name", "cmdline")):
            if process.info["pid"] in excluded:
                continue
            try:
                command = " ".join(process.info.get("cmdline") or ()).lower()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                name = str(process.info.get("name") or "").lower()
                if name in {"python.exe", "python", "powershell.exe", "pwsh.exe"}:
                    return None
                continue
            if any(marker in command for marker in markers):
                return True
        return False

    def current_boot_session_id(self) -> str:
        return _boot_session_id()


class ExecutionLock:
    def __init__(
        self,
        db: Database,
        mutex_name: str = MUTEX_NAME,
        *,
        process_observer: ProcessObserver | None = None,
        now_utc: Callable[[], datetime] | None = None,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ):
        self.db = db
        self.mutex_name = mutex_name
        self.process_observer = process_observer or WindowsProcessObserver()
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.stale_after = stale_after

    def _projection(self) -> tuple[int, dict[str, object]] | None:
        row = self.db.execute(
            "SELECT version,payload_json,payload_sha256 FROM experiment_state WHERE experiment_id=?",
            (LOCK_PROJECTION_ID,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row[1]))
        except json.JSONDecodeError as exc:
            raise LockIntegrityError("execution lock projection JSON is invalid") from exc
        if not isinstance(payload, dict) or str(row[2]) != sha256_json(payload):
            raise LockIntegrityError("execution lock projection hash is invalid")
        return int(row[0]), payload

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
        abandoned = wait == win32event.WAIT_ABANDONED
        if wait not in {win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED}:
            win32api.CloseHandle(handle)
            return LockReceipt(
                acquired=False,
                reason="OS_MUTEX_ERROR",
                owner_id=owner.owner_id,
                generation=0,
                recovery_required=True,
            )

        try:
            blocked_receipt: LockReceipt | None = None
            with self.db.transaction():
                projection = self._projection()
                previous_version = 0 if projection is None else projection[0]
                previous_payload = {} if projection is None else projection[1]
                recovered = False
                if previous_payload.get("state") == "ACTIVE":
                    inspection = self._inspect_active(previous_payload, owner)
                    generation = inspection.generation
                    if inspection.state != "STALE":
                        self._append_event(
                            generation,
                            "LOCK_RECOVERY_BLOCKED",
                            {
                                "attempted_owner_id": owner.owner_id,
                                "inspection": inspection.model_dump(),
                                "order_authority": False,
                            },
                        )
                        blocked_receipt = LockReceipt(
                            acquired=False,
                            reason="LOCK_STATE_AMBIGUOUS",
                            owner_id=owner.owner_id,
                            generation=generation,
                            recovery_required=True,
                            abandoned=abandoned,
                        )
                    else:
                        self._append_event(
                            generation,
                            "STALE_OWNER_RECOVERED",
                            {
                                "stale_owner_id": previous_payload.get("owner_id"),
                                "attempted_owner_id": owner.owner_id,
                                "inspection": inspection.model_dump(),
                                "order_authority": False,
                            },
                        )
                        recovered = True
                elif previous_payload.get("state") not in {None, "RELEASED"}:
                    generation = int(previous_payload.get("generation", 0))
                    self._append_event(
                        generation,
                        "LOCK_RECOVERY_BLOCKED",
                        {
                            "attempted_owner_id": owner.owner_id,
                            "inspection": {
                                "state": "AMBIGUOUS",
                                "reason": "NONTERMINAL_LOCK_STATE",
                                "generation": generation,
                            },
                            "order_authority": False,
                        },
                    )
                    blocked_receipt = LockReceipt(
                        acquired=False,
                        reason="LOCK_STATE_AMBIGUOUS",
                        owner_id=owner.owner_id,
                        generation=generation,
                        recovery_required=True,
                        abandoned=abandoned,
                    )
                if blocked_receipt is None:
                    generation = int(previous_payload.get("generation", 0)) + 1
                    timestamp = self.now_utc().astimezone(timezone.utc).isoformat().replace(
                        "+00:00", "Z"
                    )
                    payload = {
                        "state": "ACTIVE",
                        **owner.model_dump(),
                        "generation": generation,
                        "acquired_at_utc": timestamp,
                        "heartbeat_at_utc": timestamp,
                        "order_authority": False,
                    }
                    self._write_projection(previous_version + 1, payload)
                    self._append_event(generation, "ACQUIRED", payload)
        except BaseException:
            self._close_unowned_handle(handle, owns_mutex=True)
            raise
        if blocked_receipt is not None:
            self._close_unowned_handle(handle, owns_mutex=True)
            return blocked_receipt
        return LockReceipt(
            acquired=True,
            reason="RECOVERED_AND_ACQUIRED" if recovered else "ACQUIRED",
            owner_id=owner.owner_id,
            generation=generation,
            abandoned=abandoned,
            handle=handle,
        )

    def _inspect_active(
        self, payload: dict[str, object], contender: LockOwner
    ) -> LockInspection:
        generation = int(payload.get("generation", 0))
        required = (
            "owner_id",
            "pid",
            "process_start",
            "host_fingerprint",
            "boot_session_id",
            "heartbeat_at_utc",
            "order_authority",
        )
        if any(key not in payload for key in required):
            return LockInspection(
                state="AMBIGUOUS",
                reason="LOCK_EVIDENCE_INCOMPLETE",
                generation=generation,
                heartbeat_stale=None,
                process_state="UNKNOWN",
                order_authority_clear=False,
            )
        if payload.get("order_authority") is not False:
            return LockInspection(
                state="AMBIGUOUS",
                reason="ORDER_AUTHORITY_NOT_PROVEN_CLEAR",
                generation=generation,
                heartbeat_stale=None,
                process_state="UNKNOWN",
                order_authority_clear=False,
            )
        try:
            heartbeat = datetime.fromisoformat(
                str(payload["heartbeat_at_utc"]).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            age = self.now_utc().astimezone(timezone.utc) - heartbeat
        except (TypeError, ValueError, OverflowError):
            return LockInspection(
                state="AMBIGUOUS",
                reason="HEARTBEAT_INVALID",
                generation=generation,
                heartbeat_stale=None,
                process_state="UNKNOWN",
                order_authority_clear=True,
            )
        heartbeat_stale = age > self.stale_after and age >= timedelta(0)
        if not heartbeat_stale:
            return LockInspection(
                state="AMBIGUOUS",
                reason="HEARTBEAT_NOT_STALE",
                generation=generation,
                heartbeat_stale=False,
                process_state="UNKNOWN",
                order_authority_clear=True,
            )
        if payload.get("host_fingerprint") != contender.host_fingerprint:
            return LockInspection(
                state="AMBIGUOUS",
                reason="HOST_IDENTITY_MISMATCH",
                generation=generation,
                heartbeat_stale=True,
                process_state="UNKNOWN",
                order_authority_clear=True,
            )
        try:
            authority = self.process_observer.has_other_execution_authority(
                excluding_pid=contender.pid
            )
            current_boot = self.process_observer.current_boot_session_id()
        except Exception:
            authority = None
            current_boot = ""
        if authority is not False:
            return LockInspection(
                state="AMBIGUOUS",
                reason="EXECUTION_AUTHORITY_LIVENESS_AMBIGUOUS"
                if authority is None
                else "OTHER_EXECUTION_AUTHORITY_ACTIVE",
                generation=generation,
                heartbeat_stale=True,
                process_state="UNKNOWN",
                order_authority_clear=True,
            )
        if str(payload.get("boot_session_id")) != current_boot:
            return LockInspection(
                state="STALE",
                reason="PREVIOUS_BOOT_OWNER_STALE",
                generation=generation,
                heartbeat_stale=True,
                process_state="PREVIOUS_BOOT",
                order_authority_clear=True,
            )
        try:
            observed = self.process_observer.observe(int(payload["pid"]))
        except Exception:
            observed = "AMBIGUOUS"
        if observed == "AMBIGUOUS":
            return LockInspection(
                state="AMBIGUOUS",
                reason="PROCESS_LIVENESS_AMBIGUOUS",
                generation=generation,
                heartbeat_stale=True,
                process_state="UNKNOWN",
                order_authority_clear=True,
            )
        if observed is None:
            return LockInspection(
                state="STALE",
                reason="RECORDED_PROCESS_DEAD",
                generation=generation,
                heartbeat_stale=True,
                process_state="DEAD",
                order_authority_clear=True,
            )
        assert isinstance(observed, ObservedProcess)
        same_owner = (
            observed.pid == int(payload["pid"])
            and observed.process_start == str(payload["process_start"])
            and observed.host_fingerprint == str(payload["host_fingerprint"])
            and observed.boot_session_id == str(payload["boot_session_id"])
        )
        return LockInspection(
            state="AMBIGUOUS" if same_owner else "STALE",
            reason="LIVE_OWNER_WITH_FREE_MUTEX" if same_owner else "PID_REUSED_BY_OTHER_PROCESS",
            generation=generation,
            heartbeat_stale=True,
            process_state="LIVE_OWNER" if same_owner else "PID_REUSED",
            order_authority_clear=True,
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
        return RecoveryReceipt(
            recovered=False,
            state="EXECUTION_LOCK_AMBIGUOUS",
            order_authority=False,
            reason="LEGACY_RECOVERY_API_DISABLED",
        )
