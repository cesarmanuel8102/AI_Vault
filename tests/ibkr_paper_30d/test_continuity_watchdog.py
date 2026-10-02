from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_watchdog import ContinuityWatchdog
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def _initialize(path):
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)


class Broker:
    read_only = True
    client_id = 19762

    def __init__(self):
        self.closed = False

    def disconnect(self):
        self.closed = True


def test_watchdog_thread_owns_event_loop_for_real_broker_session(tmp_path):
    path = tmp_path / "watchdog-event-loop.sqlite3"
    _initialize(path)
    observed = {}

    def broker_factory():
        observed["loop"] = asyncio.get_event_loop()
        return Broker()

    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=broker_factory,
        poll_once=lambda db, broker, coordinator: None,
        coordinator=object(),
        broker_time_reader=lambda value: NOW,
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
    )

    watchdog.start()
    result = watchdog.stop(2)

    assert result.stopped is True
    assert observed["loop"].is_closed() is True


def test_watchdog_uses_own_thread_database_and_read_only_broker(tmp_path):
    path = tmp_path / "watchdog.sqlite3"
    _initialize(path)
    main_db = Database.open(path)
    observed = {}
    polled = threading.Event()

    def poll_once(db, broker, coordinator):
        observed["db_connection"] = db.connection
        observed["broker"] = broker
        observed["thread_id"] = threading.get_ident()
        polled.set()

    broker = Broker()
    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=lambda: broker,
        poll_once=poll_once,
        coordinator=object(),
        broker_time_reader=lambda value: NOW,
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
    )
    try:
        watchdog.start()
        assert polled.wait(2)
    finally:
        result = watchdog.stop(2)
        main_db.close()

    assert result.stopped is True
    assert observed["db_connection"] is not main_db.connection
    assert observed["thread_id"] != threading.get_ident()
    assert observed["broker"].read_only is True
    assert observed["broker"].client_id != 19761
    assert broker.closed is True


def test_lifecycle_and_heartbeat_are_durable(tmp_path):
    path = tmp_path / "lifecycle.sqlite3"
    _initialize(path)
    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=Broker,
        poll_once=lambda db, broker, coordinator: None,
        coordinator=object(),
        broker_time_reader=lambda value: NOW,
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
    )
    watchdog.start()
    time.sleep(0.04)
    result = watchdog.stop(2)

    with Database.open(path) as db:
        rows = db.execute(
            "SELECT event_type FROM continuity_watchdog_events ORDER BY sequence"
        ).fetchall()

    events = [row[0] for row in rows]
    assert events[0] == "STARTED"
    assert "HEARTBEAT" in events
    assert events[-2:] == ["STOPPING", "STOPPED"]
    assert result.stopped is True


def test_health_uses_broker_time_and_recovers_on_next_heartbeat(tmp_path):
    path = tmp_path / "health.sqlite3"
    _initialize(path)
    current = {"now": NOW}
    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=Broker,
        poll_once=lambda db, broker, coordinator: None,
        coordinator=object(),
        broker_time_reader=lambda value: current["now"],
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=5,
    )
    try:
        watchdog.start()
        time.sleep(0.03)
        assert watchdog.is_healthy(NOW + timedelta(seconds=4)) is True
        assert watchdog.is_healthy(NOW + timedelta(seconds=6)) is False
        current["now"] = NOW + timedelta(seconds=7)
        time.sleep(0.03)
        assert watchdog.is_healthy(NOW + timedelta(seconds=8)) is True
    finally:
        watchdog.stop(2)


def test_blocked_poll_shutdown_times_out_without_inventing_action(tmp_path):
    path = tmp_path / "shutdown.sqlite3"
    _initialize(path)
    release = threading.Event()
    entered = threading.Event()
    reports = []

    def blocked_poll(db, broker, coordinator):
        entered.set()
        release.wait(2)

    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=Broker,
        poll_once=blocked_poll,
        coordinator=object(),
        broker_time_reader=lambda value: NOW,
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
        uncertainty_reporter=reports.append,
    )
    watchdog.start()
    assert entered.wait(2)
    first = watchdog.stop(0.01)
    release.set()
    second = watchdog.stop(2)

    assert first.timed_out is True
    assert second.stopped is True
    assert reports == ["CONTINUITY_WATCHDOG_SHUTDOWN_TIMEOUT"]


def test_poll_failure_records_failed_and_reports_uncertainty(tmp_path):
    path = tmp_path / "failed.sqlite3"
    _initialize(path)
    reports = []

    def fail(db, broker, coordinator):
        raise RuntimeError("poll failed")

    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=Broker,
        poll_once=fail,
        coordinator=object(),
        broker_time_reader=lambda value: NOW,
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
        uncertainty_reporter=reports.append,
    )
    watchdog.start()
    time.sleep(0.04)
    watchdog.stop(2)

    with Database.open(path) as db:
        rows = db.execute(
            "SELECT event_type,payload_json FROM continuity_watchdog_events "
            "ORDER BY sequence"
        ).fetchall()
    assert any(row[0] == "FAILED" for row in rows)
    failed = next(json.loads(row[1]) for row in rows if row[0] == "FAILED")
    assert failed["error_type"] == "RuntimeError"
    assert reports == ["CONTINUITY_WATCHDOG_FAILED"]
