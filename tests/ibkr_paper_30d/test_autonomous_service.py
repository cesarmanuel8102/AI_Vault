from __future__ import annotations

import json
import inspect
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import ibkr_paper_30d.autonomous_service as service_module
from ibkr_paper_30d.autonomous_service import (
    AutonomousExperimentService,
    AutonomousServiceError,
)
from ibkr_paper_30d.autonomous_state import AutonomousStateBuildError
from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_watchdog import ContinuityWatchdog
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.research_sandbox import WSLResearchSandbox
from ibkr_paper_30d.successor_clock import BrokerTimeObservation, clock_for_epoch
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    commit_successor_transition,
)
from successor_test_support import (
    ACCOUNT_HASH,
    OWNER_SID,
    SUCCESSOR_START,
    build_authorized_successor,
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
        return {
            "schema": "TEST",
            "outcome": {"decision": "NO_TRADE"},
            "execution": None,
        }


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


def test_service_wires_the_os_enforced_research_sandbox_by_default(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    clock = Clock()
    with Database.open(tmp_path / "service.sqlite3") as db:
        subject = make_service(db, clock)

    assert isinstance(subject.workspace.sandbox, WSLResearchSandbox)
    assert subject.epoch_state["state"] == "PRE_EPOCH_HISTORY"
    assert subject.epoch_state["activation_required"] is True


def test_no_positions_scans_every_five_minutes(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "service.sqlite3") as db:
        subject = make_service(db, clock, stop_after=2)
        subject.run_forever()

    assert subject.triggers == [("SCHEDULED_SCAN", None), ("SCHEDULED_SCAN", None)]
    assert clock.sleeps == [300.0]


def test_open_position_adds_one_minute_monitoring_without_replacing_scan(
    tmp_path, monkeypatch
):
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


def test_successful_order_management_triggers_one_observation_only_refresh(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    results = [
        {
            "status": "PASS",
            "outcome": {"decision": "CANCEL_ORDER"},
            "execution": {
                "success": True,
                "order": {"order_management": "CANCEL_ORDER", "fills": []},
            },
        },
        {"status": "PASS", "outcome": {"decision": "NO_TRADE"}},
    ]
    with Database.open(tmp_path / "service.sqlite3") as db:
        service = make_service(db, clock, stop_after=2, results=results)
        service.run_forever()

    assert service.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]


def test_uncertain_order_management_triggers_one_observation_only_refresh(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    results = [
        {
            "status": "PASS",
            "outcome": {"decision": "MODIFY_ORDER"},
            "execution": {
                "success": False,
                "status": "UNCERTAIN",
                "order": {"order_management": "MODIFY_ORDER", "fills": []},
            },
        },
        {"status": "PASS", "outcome": {"decision": "NO_TRADE"}},
    ]
    with Database.open(tmp_path / "service.sqlite3") as db:
        service = make_service(db, clock, stop_after=2, results=results)
        service.run_forever()

    assert service.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]


def test_filled_during_cancel_triggers_one_observation_only_refresh(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    results = [
        {
            "status": "PASS",
            "outcome": {"decision": "CANCEL_ORDER"},
            "execution": {
                "success": False,
                "status": "FILLED",
                "reason_codes": ["ORDER_FILLED_DURING_CANCELLATION"],
                "order": {"order_management": "CANCEL_ORDER", "fills": []},
            },
        },
        {"status": "PASS", "outcome": {"decision": "NO_TRADE"}},
    ]
    with Database.open(tmp_path / "service.sqlite3") as db:
        service = make_service(db, clock, stop_after=2, results=results)
        service.run_forever()

    assert service.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]


@pytest.mark.parametrize(
    "execution",
    [
        {
            "success": True,
            "status": "MODIFIED",
            "order": {"order_management": "MODIFY_ORDER", "fills": []},
        },
        {
            "success": False,
            "status": "UNCERTAIN",
            "order": {"order_management": "MODIFY_ORDER", "fills": []},
        },
        {
            "success": False,
            "status": "FILLED",
            "reason_codes": ["ORDER_FILLED_DURING_CANCELLATION"],
            "order": {"order_management": "CANCEL_ORDER", "fills": []},
        },
    ],
)
def test_run_once_order_management_includes_observation_only_refresh(
    tmp_path, execution
):
    clock = Clock()
    follow_up = {"status": "PASS", "outcome": {"decision": "NO_TRADE"}}
    results = [
        {
            "status": "PASS",
            "outcome": {"decision": execution["order"]["order_management"]},
            "execution": execution,
        },
        follow_up,
    ]
    with Database.open(tmp_path / "service.sqlite3") as db:
        service = make_service(db, clock, stop_after=3, results=results)
        result = service.run_once()

    assert service.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]
    assert result["observation_only_follow_up"] == follow_up


class FakeContinuityWatchdog:
    def __init__(self, *, healthy=True):
        self.healthy = healthy
        self.started = threading.Event()
        self.stops = []

    def start(self):
        self.started.set()

    def stop(self, timeout_seconds):
        self.stops.append(timeout_seconds)
        return type("Shutdown", (), {"stopped": True, "timed_out": False})()

    def is_healthy(self, broker_time_utc):
        return self.healthy


def test_run_once_watchdog_progresses_while_provider_cycle_is_blocked(tmp_path):
    path = tmp_path / "blocked-provider.sqlite3"
    with Database.open(path) as setup_db:
        install_successor_schema_v2(setup_db)
        install_continuity_schema_v3(setup_db)

    provider_entered = threading.Event()
    provider_release = threading.Event()
    command_executed = threading.Event()
    commands = []

    class ReadOnlyBroker:
        read_only = True
        client_id = 19762

        def disconnect(self):
            pass

    class WriterCommandInterface:
        def submit(self, command):
            commands.append(command)
            command_executed.set()

    def poll_once(db, broker, coordinator):
        if not commands:
            coordinator.submit(
                {
                    "command_type": "CANCEL",
                    "order_ref": "order-78",
                    "order_id": 78,
                    "perm_id": 225256222,
                }
            )

    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path),
        broker_factory=ReadOnlyBroker,
        poll_once=poll_once,
        coordinator=WriterCommandInterface(),
        broker_time_reader=lambda broker: datetime.now(timezone.utc),
        poll_interval_seconds=0.01,
        heartbeat_max_age_seconds=1,
    )
    with Database.open(path) as db:
        service = RecordingService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            allocation=Decimal("500.00"),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            continuity_watchdog=watchdog,
        )

        def blocked_cycle(trigger, *, allow_execution=None):
            provider_entered.set()
            provider_release.wait(2)
            return {"status": "PASS", "outcome": {"decision": "NO_TRADE"}}

        service._run_cycle = blocked_cycle
        observer_result = {}

        def observe_parallel_progress():
            observer_result["provider_entered"] = provider_entered.wait(2)
            observer_result["command_executed"] = command_executed.wait(2)
            provider_release.set()

        observer = threading.Thread(target=observe_parallel_progress)
        observer.start()
        service.run_once()
        observer.join(2)

    assert observer_result == {
        "provider_entered": True,
        "command_executed": True,
    }
    assert commands == [
        {
            "command_type": "CANCEL",
            "order_ref": "order-78",
            "order_id": 78,
            "perm_id": 225256222,
        }
    ]


def test_watchdog_health_blocks_only_new_exposure_and_alerts_transitions(tmp_path):
    watchdog = FakeContinuityWatchdog(healthy=False)
    critical_alert_reporter = Mock()
    with Database.open(tmp_path / "watchdog-health.sqlite3") as db:
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            allocation=Decimal("500.00"),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
            broker_now=lambda: datetime.now(timezone.utc),
            continuity_watchdog=watchdog,
            critical_alert_reporter=critical_alert_reporter,
        )
        service._watchdog_started = True

        first = service._fresh_execution_safety("NEW_TRADE")
        second = service._fresh_execution_safety("NEW_TRADE")
        management = service._fresh_execution_safety("POSITION_MANAGEMENT")
        watchdog.healthy = True
        recovered = service._fresh_execution_safety("NEW_TRADE")
        alerts = db.execute(
            "SELECT event_type FROM alerts WHERE event_type LIKE "
            "'CONTINUITY_WATCHDOG_HEALTH_%' ORDER BY created_at_utc"
        ).fetchall()

    assert "CONTINUITY_WATCHDOG_UNHEALTHY" in first
    assert "CONTINUITY_WATCHDOG_UNHEALTHY" in second
    assert "CONTINUITY_WATCHDOG_UNHEALTHY" not in management
    assert "CONTINUITY_WATCHDOG_UNHEALTHY" not in recovered
    assert [row[0] for row in alerts] == [
        "CONTINUITY_WATCHDOG_HEALTH_FAILURE",
        "CONTINUITY_WATCHDOG_HEALTH_RECOVERED",
    ]
    critical_alert_reporter.assert_called_once_with("CONTINUITY_WATCHDOG_STALE")


def test_run_once_stops_watchdog_when_cycle_raises(tmp_path):
    watchdog = FakeContinuityWatchdog()
    with Database.open(tmp_path / "watchdog-finally.sqlite3") as db:
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            allocation=Decimal("500.00"),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            continuity_watchdog=watchdog,
        )
        service._run_cycle = Mock(side_effect=RuntimeError("provider blocked"))

        with pytest.raises(RuntimeError, match="provider blocked"):
            service.run_once()

    assert watchdog.started.is_set()
    assert watchdog.stops == [5.0]


class PassGate:
    def evaluate(self, *args, **kwargs):
        return {"gate_status": "PASS", "reason_codes": []}


class ArmedExecutor:
    armed = True
    is_coordinated_model_executor = True


class DirectShapedExecutor:
    armed = True


class ProductionBrokerToolbox:
    def manifest(self):
        return []

    def _account_state(self, _arguments):
        return {
            "server_time_utc": "2026-09-28T14:43:04Z",
            "net_liquidation": "DO_NOT_LEAK",
        }


class BlockGate:
    def __init__(self, code):
        self.code = code

    def evaluate(self, *args, **kwargs):
        return {"gate_status": "BLOCK", "reason_codes": [self.code]}


def _authorized_production_topology(db, *, market_gate=None, auditor_gate=None):
    start = datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc)
    clock = ExperimentClockStore(db).initialize_or_load(
        requested_start_utc=start,
        duration_days=30,
        initial_allocation=Decimal("500.00"),
    )
    KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="test", actor="test")
    OwnerAuthorizationStore(db).set(
        "AUTHORIZED",
        clock_event_sha256=clock.event_sha256,
        reason="owner authorized test",
        actor="owner",
    )
    return AutonomousExperimentService(
        db,
        experiment_start_utc=start,
        execute_paper=True,
        toolbox=AutonomyToolbox(ProductionBrokerToolbox(), None),
        provider=StubProvider(),
        executor=ArmedExecutor(),
        runtime_market_gate=market_gate or PassGate(),
        runtime_auditor_gate=auditor_gate or PassGate(),
    )


@pytest.mark.parametrize("executor", [None, DirectShapedExecutor()])
def test_paper_service_rejects_missing_or_noncoordinated_executor(
    tmp_path, executor
):
    with Database.open(tmp_path / "executor-contract.sqlite3") as db:
        with pytest.raises(
            AutonomousServiceError, match="COORDINATED_MODEL_EXECUTOR_REQUIRED"
        ):
            AutonomousExperimentService(
                db,
                experiment_start_utc=datetime(
                    2026, 9, 28, 13, 30, tzinfo=timezone.utc
                ),
                execute_paper=True,
                toolbox=StubToolbox(),
                provider=StubProvider(),
                executor=executor,
            )


def test_observation_service_allows_no_executor(tmp_path):
    with Database.open(tmp_path / "observation.sqlite3") as db:
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=None,
        )

    assert service.executor is None


def test_production_shaped_toolbox_supplies_authoritative_broker_time(tmp_path):
    with Database.open(tmp_path / "production-toolbox.sqlite3") as db:
        service = _authorized_production_topology(db)

        assert service._read_broker_time() == datetime(
            2026, 9, 28, 14, 43, 4, tzinfo=timezone.utc
        )
        reasons = service._fresh_execution_safety("NEW_TRADE")

    assert not any(
        reason.startswith("BROKER_TIME_UNAVAILABLE_FRESH") for reason in reasons
    )
    assert "EXPERIMENT_NOT_STARTED_FRESH" not in reasons
    assert "EXPERIMENT_EXPIRED_FRESH" not in reasons


@pytest.mark.parametrize(
    ("market_gate", "auditor_gate", "expected"),
    [
        (BlockGate("NO_MARKET"), PassGate(), "MARKET_DATA_GATE_BLOCK_FRESH"),
        (PassGate(), BlockGate("NO_AUDITOR"), "AUDITOR_GATE_BLOCK_FRESH"),
    ],
)
def test_production_shaped_toolbox_does_not_bypass_runtime_gates(
    tmp_path, market_gate, auditor_gate, expected
):
    with Database.open(tmp_path / f"{expected}.sqlite3") as db:
        with pytest.raises(AutonomousServiceError) as caught:
            _authorized_production_topology(
                db,
                market_gate=market_gate,
                auditor_gate=auditor_gate,
            )

    assert expected in getattr(caught.value, "reason_codes", ())


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
                broker_now=lambda: datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc),
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
            broker_now=lambda: datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc),
        )
        assert service.execute_paper is True


def test_fresh_safety_fails_closed_when_broker_time_unavailable(tmp_path):
    start = datetime(2026, 9, 20, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "broker-time.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=start,
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
            broker_now=lambda: (_ for _ in ()).throw(RuntimeError("clock unavailable")),
        )
        reasons = subject._fresh_execution_safety("NEW_TRADE")
        assert any(
            reason.startswith("BROKER_TIME_UNAVAILABLE_FRESH") for reason in reasons
        )
        assert "EXPERIMENT_NOT_STARTED_FRESH" in reasons
        assert "EXPERIMENT_EXPIRED_FRESH" in reasons


def test_default_runtime_auditor_uses_broker_time_authority(tmp_path):
    fixed = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
    start = datetime(2026, 9, 20, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "broker-auditor-time.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=start,
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            broker_now=lambda: fixed,
        )
        assert subject.runtime_auditor_gate.now_utc() == fixed


class FailingProvider:
    last_failure_code = "RETURN_CODE_1"
    last_failure_detail = "schema path: semantic validation failed"


class _ReadyBundle:
    experiment_clock = {"not_started": False, "expired": False}
    reconciliation_receipt = {"status": "PASS"}
    kill_switch_state = "KILL_SWITCH_CLEAR"
    market_data_snapshot = {"gate_status": "PASS"}

    def model_dump(self, mode=None):
        return {
            "experiment_clock": self.experiment_clock,
            "reconciliation_receipt": self.reconciliation_receipt,
            "kill_switch_state": self.kill_switch_state,
            "market_data_snapshot": self.market_data_snapshot,
        }


class _ReadyBuilder:
    def build(self, trigger):
        return _ReadyBundle()


class _ContinuousReadyBundle(_ReadyBundle):
    market_data_snapshot = {
        "gate_status": "BLOCK",
        "reason_codes": ["REGULAR_MARKET_CLOSED"],
    }
    multi_sleeve_portfolio = {
        "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
        "entry_eligibility": {
            "REGULAR_SLEEVE": {"status": "BLOCK"},
            "CONTINUOUS_SLEEVE": {
                "status": "PASS",
                "eligible_family_sha256": ["f" * 64],
            },
        },
        "management_eligibility": {},
    }
    multi_sleeve_v4_active = True

    def model_dump(self, mode=None):
        return {
            **super().model_dump(mode=mode),
            "multi_sleeve_portfolio": self.multi_sleeve_portfolio,
        }


class _ContinuousReadyBuilder:
    def build(self, trigger):
        return _ContinuousReadyBundle()


def test_regular_market_gate_block_does_not_hide_eligible_continuous_family(
    tmp_path, monkeypatch
) -> None:
    with Database.open(tmp_path / "continuous-open.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
        )
        monkeypatch.setattr(subject, "_builder", lambda: _ContinuousReadyBuilder())
        monkeypatch.setattr(
            service_module,
            "run_autonomous_cycle",
            lambda *args, **kwargs: {
                "status": "PASS",
                "outcome": {"validation": "PASS", "decision": "NO_TRADE"},
            },
        )

        result = subject._run_cycle("SCHEDULED_SCAN")

    assert result["status"] == "PASS"


def test_provider_failure_is_observed_without_claiming_policy_attribution(
    tmp_path, monkeypatch
):
    with Database.open(tmp_path / "provider-failure.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=FailingProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
        )
        monkeypatch.setattr(subject, "_builder", lambda: _ReadyBuilder())

        def fail_cycle(*args, **kwargs):
            subject.provider.last_failure_code = "RETURN_CODE_1"
            subject.provider.last_failure_detail = (
                "schema path: semantic validation failed"
            )
            raise RuntimeError("AUTONOMOUS_CODEX_PROVIDER_FAILED")

        monkeypatch.setattr(service_module, "run_autonomous_cycle", fail_cycle)

        with pytest.raises(
            service_module.RecoverableProviderInvocationError,
            match="AUTONOMOUS_CODEX_PROVIDER_FAILED",
        ):
            subject._run_cycle("SCHEDULED_SCAN")

        row = db.execute(
            "SELECT payload_json FROM alerts WHERE event_type='AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION'"
        ).fetchone()
        assert row is not None
        assert '"provider_failure_code":"RETURN_CODE_1"' in row[0]
        assert (
            '"provider_failure_detail":"schema path: semantic validation failed"'
            in row[0]
        )
        assert '"provider_policy_attribution":"UNDETERMINED"' in row[0]


def test_fresh_provider_code_cannot_reclassify_structural_persistence_error(
    tmp_path, monkeypatch
):
    with Database.open(tmp_path / "provider-then-database-error.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=FailingProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
        )
        monkeypatch.setattr(subject, "_builder", lambda: _ReadyBuilder())

        def fail_after_provider_signal(*args, **kwargs):
            subject.provider.last_failure_code = "RETURN_CODE_1"
            raise sqlite3.DatabaseError("structural persistence failure")

        monkeypatch.setattr(
            service_module,
            "run_autonomous_cycle",
            fail_after_provider_signal,
        )

        with pytest.raises(
            sqlite3.DatabaseError,
            match="structural persistence failure",
        ):
            subject._run_cycle("SCHEDULED_SCAN")


def test_execution_block_is_not_reported_as_pass(tmp_path, monkeypatch):
    with Database.open(tmp_path / "execution-block.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
        )
        monkeypatch.setattr(subject, "_builder", lambda: _ReadyBuilder())
        monkeypatch.setattr(
            service_module,
            "run_autonomous_cycle",
            lambda *args, **kwargs: {
                "outcome": {
                    "validation": "PASS",
                    "decision": "MODIFY_ORDER",
                },
                "execution": {
                    "success": False,
                    "status": "BLOCKED",
                    "reason_codes": ["OPEN_ORDER_CONTRACT_IDENTITY_MISMATCH"],
                    "order": {},
                },
            },
        )

        result = subject._run_cycle_with_lifecycle("SCHEDULED_SCAN")
        completed = latest_state_event(db, "AUTONOMOUS_CYCLE_COMPLETED")

    assert result["status"] == "EXECUTION_BLOCKED"
    assert result["gate"] == "EXECUTION"
    assert result["reason_codes"] == ["OPEN_ORDER_CONTRACT_IDENTITY_MISMATCH"]
    assert completed["status"] == "EXECUTION_BLOCKED"
    assert completed["gate"] == "EXECUTION"
    assert completed["gate_status"] == "BLOCK"
    assert completed["reason_codes"] == [
        "OPEN_ORDER_CONTRACT_IDENTITY_MISMATCH"
    ]


def test_service_passes_provider_lifecycle_and_bound_broker_time_to_runtime(
    tmp_path, monkeypatch
):
    captured = {}
    provider_lifecycle = object()
    with Database.open(tmp_path / "provider-lifecycle.sqlite3") as db:
        subject = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
            broker_now=lambda: datetime(2026, 10, 1, 14, tzinfo=timezone.utc),
            provider_lifecycle=provider_lifecycle,
            provider_account_identity_sha256="a" * 64,
        )
        monkeypatch.setattr(subject, "_builder", lambda: _ReadyBuilder())

        def record(*args, **kwargs):
            captured.update(kwargs)
            return {
                "status": "PASS",
                "outcome": {"validation": "PASS", "decision": "NO_TRADE"},
                "execution": None,
            }

        monkeypatch.setattr(service_module, "run_autonomous_cycle", record)
        subject._run_cycle("SCHEDULED_SCAN")

    evidence = captured["broker_time_reader"]()
    assert captured["provider_lifecycle"] is provider_lifecycle
    assert evidence.authenticated is True
    assert evidence.account_identity_sha256 == "a" * 64


def state_event_types(db):
    return [
        str(row[0])
        for row in db.execute(
            "SELECT event_type FROM state_events ORDER BY sequence"
        ).fetchall()
    ]


def latest_state_event(db, event_type):
    row = db.execute(
        "SELECT payload_json FROM state_events WHERE event_type=? "
        "ORDER BY sequence DESC LIMIT 1",
        (event_type,),
    ).fetchone()
    assert row is not None
    return json.loads(str(row[0]))


def test_gate_block_completion_is_observable_and_alert_is_transition_deduplicated(
    tmp_path,
):
    clock = Clock()
    block_a = {
        "status": "STATE_GATE_BLOCK",
        "gate": "AUDITOR",
        "auditor": {
            "gate_status": "BLOCK",
            "reason_codes": ["PAPER_IDENTITY_RECEIPT_MISMATCH"],
        },
    }
    block_b = {
        "status": "STATE_GATE_BLOCK",
        "gate": "AUDITOR",
        "auditor": {
            "gate_status": "BLOCK",
            "reason_codes": ["PAPER_ENVIRONMENT_MISMATCH"],
        },
    }
    passed = {
        "status": "PASS",
        "outcome": {"decision": "NO_TRADE"},
        "auditor_gate": {"gate_status": "PASS", "reason_codes": []},
    }
    with Database.open(tmp_path / "gate-observability.sqlite3") as db:
        service = make_service(
            db,
            clock,
            stop_after=10,
            results=[block_a, block_a, block_b, passed, block_b],
        )

        for _ in range(5):
            service._run_cycle_with_lifecycle("SCHEDULED_SCAN")

        completions = [
            json.loads(str(row[0]))
            for row in db.execute(
                "SELECT payload_json FROM state_events "
                "WHERE event_type='AUTONOMOUS_CYCLE_COMPLETED' ORDER BY sequence"
            ).fetchall()
        ]
        alerts = [
            json.loads(str(row[0]))
            for row in db.execute(
                "SELECT payload_json FROM alerts "
                "WHERE event_type='RECOVERY_GATE_FAILURE' ORDER BY created_at_utc"
            ).fetchall()
        ]

    assert completions[0]["gate"] == "AUDITOR"
    assert completions[0]["gate_status"] == "BLOCK"
    assert completions[0]["reason_codes"] == [
        "PAPER_IDENTITY_RECEIPT_MISMATCH"
    ]
    assert completions[3]["gate_status"] == "PASS"
    assert completions[3]["reason_codes"] == []
    assert len(alerts) == 3
    assert [item["reason_codes"] for item in alerts] == [
        ["PAPER_IDENTITY_RECEIPT_MISMATCH"],
        ["PAPER_ENVIRONMENT_MISMATCH"],
        ["PAPER_ENVIRONMENT_MISMATCH"],
    ]


def test_run_forever_records_first_operational_cycle_lifecycle(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    result = {
        "status": "PASS",
        "outcome": {"decision": "NO_TRADE"},
        "request": {"decision_cycle_id": "cycle-1"},
        "execution": None,
    }
    with Database.open(tmp_path / "lifecycle.sqlite3") as db:
        service = make_service(db, clock, stop_after=1, results=[result])
        service.launch_attempt_id = "11111111-1111-4111-8111-111111111111"

        service.run_forever()

        event_types = state_event_types(db)
        running = latest_state_event(db, "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING")
    assert "AUTONOMOUS_SERVICE_STARTED" in event_types
    assert "AUTONOMOUS_CYCLE_STARTED" in event_types
    assert "AUTONOMOUS_CYCLE_COMPLETED" in event_types
    assert running["decision"] == "NO_TRADE"
    assert running["decision_cycle_id"] == "cycle-1"
    assert running["launch_attempt_id"] == service.launch_attempt_id


def test_successor_service_events_bind_exact_epoch_definition_and_clock(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "successor-service.sqlite3"
    receipt_path = tmp_path / "owner-successor-v2.json"
    definition, receipt = build_authorized_successor(db_path, receipt_path)
    collected_at = SUCCESSOR_START + timedelta(seconds=1)
    evidence = BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=collected_at,
        observation=BrokerTimeObservation(
            server_time_utc=SUCCESSOR_START,
            observed_at_utc=collected_at,
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=0,
    )
    result_payload = {
        "status": "PASS",
        "outcome": {"decision": "NO_TRADE"},
        "request": {"decision_cycle_id": "cycle-successor"},
        "execution": None,
    }
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)

    with Database.open(db_path) as db:
        transition = commit_successor_transition(
            db=db,
            launch_attempt_id="launch-successor-service",
            target_successor_epoch_id=str(definition["epoch_id"]),
            target_successor_definition_sha256=str(definition["definition_sha256"]),
            expected_account_identity_sha256=ACCOUNT_HASH,
            expected_owner_sid=OWNER_SID,
            owner_authorization_receipt=receipt,
            execution_lock_verifier=lambda: True,
            broker_evidence_collector=lambda: evidence,
            now_utc=lambda: SUCCESSOR_START + timedelta(seconds=2),
        )
        successor_clock = clock_for_epoch(db, str(definition["epoch_id"]))
        service = RecordingService(
            db,
            experiment_start_utc=successor_clock.start_utc,
            experiment_clock=successor_clock,
            successor_owner_authorization_receipt=receipt,
            successor_owner_sid=OWNER_SID,
            allocation=Decimal("500.00"),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=StubExecutor(),
            stop_after=1,
            results=[result_payload],
        )
        service.launch_attempt_id = "launch-successor-service"

        builder = service._builder()
        assert builder.experiment_clock.event_sha256 == transition.clock_event_sha256
        assert builder.experiment_clock.epoch_id == definition["epoch_id"]

        service.run_forever()

        started = latest_state_event(db, "AUTONOMOUS_SERVICE_STARTED")
        running = latest_state_event(db, "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING")

    expected = {
        "epoch_id": definition["epoch_id"],
        "definition_sha256": definition["definition_sha256"],
        "clock_event_sha256": transition.clock_event_sha256,
    }
    assert {key: started[key] for key in expected} == expected
    assert {key: running[key] for key in expected} == expected


@pytest.mark.parametrize("status", ["UNKNOWN", "PARTIAL", "RECOVERING", "BLOCK"])
def test_nonoperational_status_never_declares_running(tmp_path, monkeypatch, status):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    result = {
        "status": status,
        "outcome": {"decision": "NO_TRADE"},
        "request": {"decision_cycle_id": "cycle-1"},
        "execution": None,
    }
    with Database.open(tmp_path / f"nonoperational-{status}.sqlite3") as db:
        service = make_service(db, clock, stop_after=1, results=[result])
        service.run_forever()
        assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" not in state_event_types(db)


def test_cycle_exception_records_sanitized_failure_and_reraises(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "failed-cycle.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        service._run_cycle = Mock(side_effect=RuntimeError("secret-token-value"))
        service.sleep = lambda _: service.stop()

        with pytest.raises(RuntimeError, match="secret-token-value"):
            service.run_forever()

        failure = latest_state_event(db, "AUTONOMOUS_CYCLE_FAILED")
        assert failure["error_type"] == "RuntimeError"
        assert "secret-token-value" not in json.dumps(failure)
        assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" not in state_event_types(db)


def test_provider_failure_is_retried_without_terminating_service(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "provider-retry.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        service.provider = FailingProvider()
        calls = []

        def cycle(_trigger, *, allow_execution=None):
            calls.append(allow_execution)
            if len(calls) == 1:
                raise service_module.RecoverableProviderInvocationError(
                    "AUTONOMOUS_CODEX_PROVIDER_FAILED"
                )
            service.stop()
            return {
                "status": "PASS",
                "outcome": {"decision": "NO_TRADE"},
                "request": {"decision_cycle_id": "cycle-recovered"},
                "execution": None,
            }

        service._run_cycle = cycle

        service.run_forever()

        assert calls == [None, None]
        assert clock.sleeps == [60.0]
        assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" in state_event_types(db)


def test_transient_broker_state_failure_is_retried_without_terminating_service(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "broker-state-retry.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        calls = []

        def cycle(_trigger, *, allow_execution=None):
            calls.append(allow_execution)
            if len(calls) == 1:
                raise service_module.TransientBrokerStateBuildError(
                    "POSITIONS_FAILED:TimeoutError:tool_failed"
                )
            service.stop()
            return {
                "status": "PASS",
                "outcome": {"decision": "NO_TRADE"},
                "request": {"decision_cycle_id": "cycle-broker-recovered"},
                "execution": None,
            }

        service._run_cycle = cycle

        service.run_forever()

        alerts = [
            json.loads(str(row[0]))
            for row in db.execute(
                "SELECT payload_json FROM alerts "
                "WHERE event_type='RECOVERABLE_RUNTIME_ERROR'"
            ).fetchall()
        ]
        event_types = state_event_types(db)

    assert calls == [None, None]
    assert clock.sleeps == [60.0]
    assert alerts[-1]["error_type"] == "TransientBrokerStateBuildError"
    assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" in event_types


def test_non_transient_state_build_failure_still_terminates_service(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "broker-state-fatal.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        service._run_cycle = Mock(
            side_effect=AutonomousStateBuildError("SUCCESSOR_CLOCK_BINDING_MISMATCH")
        )

        with pytest.raises(
            AutonomousStateBuildError,
            match="SUCCESSOR_CLOCK_BINDING_MISMATCH",
        ):
            service.run_forever()


def test_stale_provider_failure_code_cannot_make_structural_error_recoverable(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "stale-provider-code.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        service.provider = FailingProvider()
        service._run_cycle = Mock(
            side_effect=AutonomousStateBuildError(
                "SUCCESSOR_CLOCK_BINDING_MISMATCH"
            )
        )
        service.sleep = Mock(side_effect=AssertionError("unexpected retry"))

        with pytest.raises(
            AutonomousStateBuildError,
            match="SUCCESSOR_CLOCK_BINDING_MISMATCH",
        ):
            service.run_forever()

    service.sleep.assert_not_called()


def test_transient_failure_does_not_hide_alert_persistence_error(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "alert-persistence.sqlite3") as db:
        service = make_service(db, clock, stop_after=2)
        service._run_cycle = Mock(
            side_effect=service_module.TransientBrokerStateBuildError(
                "POSITIONS_FAILED:TimeoutError:tool_failed"
            )
        )

        def fail_alert(*_args, **_kwargs):
            raise sqlite3.DatabaseError("alert write failed")

        monkeypatch.setattr(service_module, "_append_alert", fail_alert)

        with pytest.raises(sqlite3.DatabaseError, match="alert write failed"):
            service.run_forever()

    assert clock.sleeps == []


def test_model_substitution_fails_first_cycle_before_executor(tmp_path, monkeypatch):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()

    class ExecutorTripwire:
        def __init__(self):
            self.calls = []

        def execute(self, *args, **kwargs):
            self.calls.append("execute")
            raise AssertionError("executor reached")

        def execute_position_action(self, *args, **kwargs):
            self.calls.append("execute_position_action")
            raise AssertionError("executor reached")

        def execute_open_order_action(self, *args, **kwargs):
            self.calls.append("execute_open_order_action")
            raise AssertionError("executor reached")

    executor = ExecutorTripwire()
    with Database.open(tmp_path / "model-substitution.sqlite3") as db:
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            allocation=Decimal("500.00"),
            execute_paper=False,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=executor,
            runtime_market_gate=PassGate(),
            runtime_auditor_gate=PassGate(),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        monkeypatch.setattr(service, "_builder", lambda: _ReadyBuilder())

        def reject_substitution(*args, **kwargs):
            raise ValueError("MODEL_ATTESTATION_MISMATCH:secret-model-value")

        monkeypatch.setattr(service_module, "run_autonomous_cycle", reject_substitution)

        with pytest.raises(ValueError, match="MODEL_ATTESTATION_MISMATCH"):
            service.run_forever()

        failure = latest_state_event(db, "AUTONOMOUS_CYCLE_FAILED")
        assert failure["error_type"] == "ValueError"
        assert "secret-model-value" not in json.dumps(failure)
        assert executor.calls == []


# ---------------------------------------------------------------------------
# Post-market orchestration (2026-10-02 remediation)
# ---------------------------------------------------------------------------

_REGULAR_DAY_LIQUID_HOURS = "20261002:0930-20261002:1600"
_CLOSED_DAY_LIQUID_HOURS = "20261004:CLOSED"


def test_service_uses_family_sessions_without_idling_an_open_extended_market():
    service = object.__new__(AutonomousExperimentService)
    service.session_evidence_reader = lambda: {
        "broker_time_utc": "2026-10-09T20:05:00Z",
        "family_sessions": {
            "regular": {"authenticated": True, "session": "CLOSED"},
            "extended": {"authenticated": True, "session": "REGULAR"},
        },
        "open_orders": [],
        "continuity_deadlines": [],
    }
    service.broker_now = Mock(side_effect=AssertionError("unexpected broker read"))

    decision = service._session_orchestration_decision(False)

    assert decision is not None
    assert decision.should_run_cycle is True
    service.broker_now.assert_not_called()


def test_successor_service_never_invokes_legacy_three_window_collector():
    source = inspect.getsource(AutonomousExperimentService)
    assert "market_observation_collector" not in source
    assert "FORCE_FRESH" not in source


def test_v4_service_can_arm_with_legacy_regular_market_gate_closed(
    tmp_path, monkeypatch
):
    class ClosedRegularGate:
        def evaluate(self, *_args, **_kwargs):
            return {
                "gate_status": "BLOCK",
                "reason_codes": ["REGULAR_SESSION_CLOSED"],
            }

    class ArmedExecutor:
        armed = True
        is_coordinated_model_executor = True

    authority = SimpleNamespace(
        schema="MULTI_UNIVERSE_RUNTIME_AUTHORITY_V1",
        transition_phase="SUPERVISION_BOUND",
        entry_authority_mode="FROZEN",
        writer_start_allowed=True,
        management_actions_allowed=True,
        new_regular_entries_allowed=False,
        new_continuous_entries_allowed=False,
        legacy_predecessor_allowed=False,
    )
    monkeypatch.setattr(
        AutonomousExperimentService,
        "_owner_authorization_is_current",
        lambda self: True,
    )
    with Database.open(tmp_path / "v4-supervision.sqlite3") as db:
        KillSwitchStore(db).set(
            "KILL_SWITCH_CLEAR", reason="test successor supervision startup"
        )
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=datetime.now(timezone.utc),
            allocation=Decimal("500.00"),
            execute_paper=True,
            toolbox=StubToolbox(),
            provider=StubProvider(),
            executor=ArmedExecutor(),
            runtime_market_gate=ClosedRegularGate(),
            runtime_auditor_gate=PassGate(),
            broker_now=lambda: datetime.now(timezone.utc),
            multi_universe_runtime_authority=authority,
        )

    assert service.multi_universe_runtime_authority is authority


class _IdleStoppingClock(Clock):
    """Stops the service after a bounded number of idle sleeps."""

    def __init__(self, stop_after_sleeps=4):
        super().__init__()
        self.service = None
        self.stop_after_sleeps = stop_after_sleeps

    def sleep(self, seconds):
        super().sleep(seconds)
        if self.service is not None and len(self.sleeps) >= self.stop_after_sleeps:
            self.service.stop()


def _idle_events(db):
    return [
        row[0]
        for row in db.execute(
            "SELECT event_type FROM state_events WHERE event_type=?",
            ("MARKET_CLOSED_IDLE",),
        ).fetchall()
    ]


def _closed_session_service(db, clock, *, positions=(), open_orders=False):
    service = RecordingService(
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
        stop_after=2,
        broker_now=lambda: datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc),
        session_evidence_reader=lambda: {
            "liquid_hours": _REGULAR_DAY_LIQUID_HOURS,
            "timezone_id": "US/Eastern",
            "has_open_orders": open_orders,
        },
    )
    clock.service = service
    return service


def test_closed_session_flat_idles_without_running_trader_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock()
    with Database.open(tmp_path / "idle.sqlite3") as db:
        service = _closed_session_service(db, clock)
        service.run_forever()
        idle = _idle_events(db)

    assert service.triggers == []
    assert len(idle) == 1


def test_closed_session_idle_does_not_create_repeated_records(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock(stop_after_sleeps=12)
    with Database.open(tmp_path / "idle-storm.sqlite3") as db:
        service = _closed_session_service(db, clock)
        service.run_forever()
        idle = _idle_events(db)
        alerts = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE event_type LIKE '%MARKET_DATA%'"
        ).fetchone()[0]

    assert len(clock.sleeps) >= 12
    assert len(idle) == 1
    assert alerts == 0


def test_closed_session_with_open_order_still_runs_continuity_cycle(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock()
    with Database.open(tmp_path / "idle-order.sqlite3") as db:
        service = _closed_session_service(db, clock, open_orders=True)
        service.run_forever()

    assert service.triggers != []


def test_closed_session_with_open_position_still_runs_continuity_cycle(
    tmp_path, monkeypatch
):
    class PositionLedger(FakeLedger):
        positions = ("OPEN",)

    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", PositionLedger)
    clock = _IdleStoppingClock()
    with Database.open(tmp_path / "idle-position.sqlite3") as db:
        service = _closed_session_service(db, clock)
        service.run_forever()

    assert service.triggers != []


def test_service_without_session_evidence_preserves_existing_behaviour(
    tmp_path, monkeypatch
):
    """No calendar evidence must not change the baseline cycle behaviour."""
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    with Database.open(tmp_path / "no-evidence.sqlite3") as db:
        service = make_service(db, clock)
        service.run_forever()
        idle = _idle_events(db)

    assert service.triggers == [("SCHEDULED_SCAN", None), ("SCHEDULED_SCAN", None)]
    assert idle == []


def test_market_closed_idle_event_carries_no_gate_or_authority_fields(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock()
    with Database.open(tmp_path / "idle-payload.sqlite3") as db:
        service = _closed_session_service(db, clock)
        service.run_forever()
        payload = json.loads(
            db.execute(
                "SELECT payload_json FROM state_events WHERE event_type=?",
                ("MARKET_CLOSED_IDLE",),
            ).fetchone()[0]
        )

    assert payload["action"] == "MARKET_CLOSED_IDLE"
    assert payload["market_session"] == "AFTER_HOURS"
    for forbidden in ("gate_status", "receipt_sha256", "order_authority", "authorized"):
        assert forbidden not in payload


def test_orchestration_uses_broker_time_from_evidence_not_second_connection(
    tmp_path, monkeypatch
):
    """When session evidence carries broker_time_utc, the orchestration
    decision must reuse it and must NOT open a second broker connection."""
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock()

    broker_now_calls = []

    def capture_broker_now():
        broker_now_calls.append("called")
        return datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)

    with Database.open(tmp_path / "single-conn.sqlite3") as db:
        service = RecordingService(
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
            stop_after=2,
            broker_now=capture_broker_now,
            session_evidence_reader=lambda: {
                "broker_time_utc": "2026-10-02T21:00:00Z",
                "liquid_hours": _REGULAR_DAY_LIQUID_HOURS,
                "timezone_id": "US/Eastern",
                "has_open_orders": False,
            },
        )
        clock.service = service
        service.run_forever()
        idle = _idle_events(db)

    assert len(idle) == 1
    assert len(broker_now_calls) == 0, "broker_now must not be called when evidence has broker_time_utc"


def test_orchestration_falls_back_to_broker_now_when_evidence_lacks_time(
    tmp_path, monkeypatch
):
    """Legacy evidence without broker_time_utc must safely fall back."""
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = _IdleStoppingClock()

    broker_now_calls = []

    def capture_broker_now():
        broker_now_calls.append("called")
        return datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)

    with Database.open(tmp_path / "fallback.sqlite3") as db:
        service = RecordingService(
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
            stop_after=2,
            broker_now=capture_broker_now,
            session_evidence_reader=lambda: {
                "liquid_hours": _REGULAR_DAY_LIQUID_HOURS,
                "timezone_id": "US/Eastern",
                "has_open_orders": False,
            },
        )
        clock.service = service
        service.run_forever()
        idle = _idle_events(db)

    assert len(idle) == 1
    assert len(broker_now_calls) >= 1
