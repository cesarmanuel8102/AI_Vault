"""Independent liveness loop for model-authored order continuity authority."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .continuity_store import ContinuityStore


_WATCHDOG_STREAM = "__continuity_watchdog__"


@dataclass(frozen=True)
class WatchdogShutdownResult:
    stopped: bool
    timed_out: bool


class ContinuityWatchdog:
    """Poll continuity authority without depending on the model-provider thread."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Any],
        broker_factory: Callable[[], Any],
        poll_once: Callable[[Any, Any, Any], Any],
        coordinator: Any,
        broker_time_reader: Callable[[Any], datetime],
        poll_interval_seconds: float,
        heartbeat_max_age_seconds: float,
        uncertainty_reporter: Callable[[str], None] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if heartbeat_max_age_seconds <= 0:
            raise ValueError("heartbeat_max_age_seconds must be positive")
        self.db_factory = db_factory
        self.broker_factory = broker_factory
        self.poll_once = poll_once
        self.coordinator = coordinator
        self.broker_time_reader = broker_time_reader
        self.poll_interval_seconds = poll_interval_seconds
        self.heartbeat_max_age_seconds = heartbeat_max_age_seconds
        self.uncertainty_reporter = uncertainty_reporter or (lambda code: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._state_lock = threading.Lock()
        self._last_heartbeat_utc: datetime | None = None
        self._failure: BaseException | None = None
        self._reported: set[str] = set()

    def _report_once(self, code: str) -> bool:
        with self._state_lock:
            if code in self._reported:
                return False
            self._reported.add(code)
        self.uncertainty_reporter(code)
        return True

    def _observe_poll_result(self, store: ContinuityStore, result: Any) -> None:
        if result is None or not hasattr(result, "selected_action"):
            return
        reasons = tuple(str(code) for code in getattr(result, "reason_codes", ()))
        if getattr(result, "selected_action") is not None or not reasons:
            return
        alert_code = "CONTINUITY_AUTHORITY_FROZEN:" + "|".join(reasons)
        if self._report_once(alert_code):
            self._append(
                store,
                "AUTHORITY_FROZEN",
                {"reason_codes": list(reasons)},
            )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("broker time must be timezone-aware")
        return value.astimezone(timezone.utc)

    def start(self, timeout_seconds: float = 5.0) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("CONTINUITY_WATCHDOG_ALREADY_RUNNING")
        self._stop.clear()
        self._ready.clear()
        with self._state_lock:
            self._last_heartbeat_utc = None
            self._failure = None
            self._reported.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ibkr-continuity-watchdog",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout_seconds):
            self._report_once("CONTINUITY_WATCHDOG_START_TIMEOUT")
            raise RuntimeError("CONTINUITY_WATCHDOG_START_TIMEOUT")
        with self._state_lock:
            failure = self._failure
        if failure is not None:
            raise RuntimeError("CONTINUITY_WATCHDOG_START_FAILED") from failure

    def stop(self, timeout_seconds: float) -> WatchdogShutdownResult:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, timeout_seconds))
        stopped = thread is None or not thread.is_alive()
        if not stopped:
            self._report_once("CONTINUITY_WATCHDOG_SHUTDOWN_TIMEOUT")
        return WatchdogShutdownResult(stopped=stopped, timed_out=not stopped)

    def is_healthy(self, broker_time_utc: datetime) -> bool:
        with self._state_lock:
            heartbeat = self._last_heartbeat_utc
            failure = self._failure
        thread = self._thread
        if (
            heartbeat is None
            or failure is not None
            or thread is None
            or not thread.is_alive()
        ):
            return False
        now = self._as_utc(broker_time_utc)
        age = (now - heartbeat).total_seconds()
        return 0 <= age <= self.heartbeat_max_age_seconds

    def _append(
        self, store: ContinuityStore, event_type: str, payload: dict[str, Any]
    ) -> None:
        store.append_watchdog_event(_WATCHDOG_STREAM, event_type, payload)

    def _run(self) -> None:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        db = None
        broker = None
        store = None
        started = False
        try:
            db = self.db_factory()
            broker = self.broker_factory()
            if getattr(broker, "read_only", None) is not True:
                raise PermissionError("WATCHDOG_BROKER_MUST_BE_READ_ONLY")
            store = ContinuityStore(db)
            self._append(
                store,
                "STARTED",
                {
                    "thread_id": threading.get_ident(),
                    "broker_client_id": getattr(broker, "client_id", None),
                },
            )
            started = True
            self._ready.set()
            while not self._stop.is_set():
                broker_now = self._as_utc(self.broker_time_reader(broker))
                with self._state_lock:
                    self._last_heartbeat_utc = broker_now
                self._append(
                    store,
                    "HEARTBEAT",
                    {"broker_time_utc": broker_now.isoformat()},
                )
                poll_result = self.poll_once(db, broker, self.coordinator)
                self._observe_poll_result(store, poll_result)
                self._stop.wait(self.poll_interval_seconds)
        except BaseException as exc:
            with self._state_lock:
                self._failure = exc
            if store is not None:
                try:
                    self._append(
                        store,
                        "FAILED",
                        {"error_type": type(exc).__name__},
                    )
                except Exception:
                    pass
            self._report_once("CONTINUITY_WATCHDOG_FAILED")
            self._ready.set()
        finally:
            if store is not None and started:
                try:
                    self._append(store, "STOPPING", {})
                    self._append(store, "STOPPED", {})
                except Exception:
                    self._report_once("CONTINUITY_WATCHDOG_FAILED")
            if broker is not None:
                try:
                    broker.disconnect()
                except Exception:
                    pass
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
            asyncio.set_event_loop(None)
            event_loop.close()
            self._ready.set()
