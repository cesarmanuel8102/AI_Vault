from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
import ibkr_paper_30d.autonomous_service as service_module
from ibkr_paper_30d.autonomous_service import (
    AutonomousExperimentService,
    AutonomousServiceError,
)
from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.research_sandbox import WSLResearchSandbox
from ibkr_paper_30d.successor_clock import BrokerTimeObservation, clock_for_epoch
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


class PassGate:
    def evaluate(self, *args, **kwargs):
        return {"gate_status": "PASS", "reason_codes": []}


class ArmedExecutor:
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
            raise RuntimeError("AUTONOMOUS_CODEX_PROVIDER_FAILED")

        monkeypatch.setattr(service_module, "run_autonomous_cycle", fail_cycle)

        with pytest.raises(RuntimeError, match="AUTONOMOUS_CODEX_PROVIDER_FAILED"):
            subject._run_cycle("SCHEDULED_SCAN")

        row = db.execute(
            "SELECT payload_json FROM alerts WHERE event_type='AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION'"
        ).fetchone()
        assert row is not None
        assert '"provider_failure_code":"RETURN_CODE_1"' in row[0]
        assert '"provider_policy_attribution":"UNDETERMINED"' in row[0]


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
                raise RuntimeError("AUTONOMOUS_CODEX_PROVIDER_FAILED")
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
