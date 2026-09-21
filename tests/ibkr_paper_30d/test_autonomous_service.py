from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import ibkr_paper_30d.autonomous_service as service_module
from ibkr_paper_30d.autonomous_service import AutonomousExperimentService, AutonomousServiceError
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)


@dataclass
class FakeProjected:
    equity: Decimal = Decimal("500.00")
    positions: tuple = ()
    valid: bool = True
    reason_codes: tuple = ()


class FakeLedger:
    positions = ()

    def __init__(self, db, allocation):
        self.db = db
        self.allocation = allocation

    def project(self):
        return FakeProjected(positions=self.positions)


class Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class StubToolbox:
    pass


class StubProvider:
    pass


class StubExecutor:
    pass


class RecordingService(AutonomousExperimentService):
    def __init__(self, *args, stop_after=2, results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.triggers = []
        self.stop_after = stop_after
        self.results = list(results or [])

    def _run_cycle(self, trigger, *, allow_execution=None):
        self.triggers.append((trigger, allow_execution))
        if len(self.triggers) >= self.stop_after:
            self.stop()
        if self.results:
            return self.results.pop(0)
        return {"schema": "TEST", "outcome": {"decision": "NO_TRADE"}, "execution": None}


def make_service(db, clock, *, stop_after=2, results=None):
    return RecordingService(
        db,
        experiment_start_utc=datetime.now(timezone.utc),
        allocation=Decimal("500.00"),
        scan_interval_seconds=300,
        position_interval_seconds=60,
        execute_paper=False,
        toolbox=StubToolbox(),
        provider=StubProvider(),
        executor=StubExecutor(),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        stop_after=stop_after,
        results=results,
    )


def test_no_positions_scans_every_five_minutes(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "service.sqlite3") as db:
        subject = make_service(db, clock, stop_after=2)
        subject.run_forever()

    assert subject.triggers == [("SCHEDULED_SCAN", None), ("SCHEDULED_SCAN", None)]
    assert clock.sleeps == [300.0]


def test_open_position_adds_one_minute_monitoring_without_replacing_scan(tmp_path, monkeypatch):
    FakeLedger.positions = (object(),)
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "service.sqlite3") as db:
        subject = make_service(db, clock, stop_after=3)
        subject.run_forever()

    assert subject.triggers == [
        ("POSITION_EVENT", None),
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", None),
    ]
    assert clock.sleeps == [60.0]


def test_fill_causes_immediate_position_event_reassessment(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    results = [
        {
            "schema": "TEST",
            "execution": {"order": {"fills": [{"execution_id_hash": "x"}]}},
        },
        {"schema": "TEST", "execution": None},
    ]
    with Database.open(tmp_path / "service.sqlite3") as db:
        subject = make_service(db, clock, stop_after=2, results=results)
        subject.run_forever()

    assert subject.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]



class PassGate:
    def evaluate(self, *args, **kwargs):
        return {"gate_status": "PASS", "reason_codes": []}


class ArmedExecutor:
    armed = True


def test_paper_execution_requires_explicit_clock_bound_owner_authorization(tmp_path):
    start = datetime(2026, 9, 20, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "armed.sqlite3") as db:
        KillSwitchStore(db).set(
            "KILL_SWITCH_CLEAR",
            reason="test precondition",
            actor="test",
        )
        try:
            AutonomousExperimentService(
                db,
                experiment_start_utc=start,
                execute_paper=True,
                toolbox=StubToolbox(),
                provider=StubProvider(),
                executor=ArmedExecutor(),
                runtime_market_gate=PassGate(),
                runtime_auditor_gate=PassGate(),
            )
        except AutonomousServiceError as exc:
            assert "explicit owner authorization" in str(exc)
        else:
            raise AssertionError("armed service accepted missing owner authorization")

        clock = ExperimentClockStore(db).load()
        assert clock is not None
        OwnerAuthorizationStore(db).set(
            "AUTHORIZED",
            clock_event_sha256=clock.event_sha256,
            reason="owner authorized test",
            actor="owner",
        )
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=start,
            execute_paper=True,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=ArmedExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
        )
        assert service.execute_paper is True
