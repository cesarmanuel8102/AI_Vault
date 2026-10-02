from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from decimal import Decimal
from concurrent.futures import Future

import pytest

from ibkr_paper_30d.day1_launch import _default_dependencies
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.open_order_management import canonical_contract_identity
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.production_continuity_runtime import (
    OBSERVER_CLIENT_ID,
    WRITER_CLIENT_ID,
    ProductionRuntimeConfigurationError,
    ReadOnlyContinuityBroker,
    ProductionContinuityPoller,
    ProductionCriticalAlertReporter,
    build_ibkr_session_factory,
    validate_production_runtime_configuration,
    _verified_registry_binding,
    validate_production_composition,
)


NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


class FakeIB:
    def __init__(self) -> None:
        self.connect_calls = []
        self.disconnected = False

    def connect(self, host, port, **kwargs):
        self.connect_calls.append((host, port, kwargs))

    def isConnected(self):
        return True

    def managedAccounts(self):
        return ["DU123456"]

    def disconnect(self):
        self.disconnected = True


def test_default_day1_dependencies_have_concrete_continuity_factories() -> None:
    dependencies = _default_dependencies()

    assert callable(dependencies.broker_write_coordinator_factory)
    assert callable(dependencies.model_executor_factory)
    assert callable(dependencies.critical_alert_reporter_factory)
    assert callable(dependencies.authoritative_writer_factory)
    assert callable(dependencies.continuity_watchdog_factory)
    assert callable(dependencies.continuity_store_factory)


@pytest.mark.parametrize(
    ("client_id", "read_only"),
    [(WRITER_CLIENT_ID, False), (OBSERVER_CLIENT_ID, True)],
)
def test_ibkr_session_factory_binds_exact_client_and_readonly_mode(
    client_id, read_only
) -> None:
    created = []
    factory = build_ibkr_session_factory(
        host="127.0.0.1",
        port=4002,
        expected_account_hash=expected_identity_hash("DU123456"),
        client_id=client_id,
        read_only=read_only,
        ib_factory=lambda: created.append(FakeIB()) or created[-1],
    )

    broker = factory()

    assert broker.client_id == client_id
    assert broker.read_only is read_only
    assert broker.all_order_visibility is True
    assert created[0].connect_calls == [
        (
            "127.0.0.1",
            4002,
            {"clientId": client_id, "timeout": 20.0, "readonly": read_only},
        )
    ]


def test_missing_external_alert_configuration_fails_with_exact_reason(tmp_path) -> None:
    config = SimpleNamespace(repo_root=Path(tmp_path))

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="EXTERNAL_ALERT_CONFIGURATION_MISSING",
    ):
        validate_production_runtime_configuration(config)


def test_readonly_observer_returns_only_canonical_facts(continuity_plan_factory) -> None:
    contract = SimpleNamespace(
        conId=756733,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=[],
    )
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": OBSERVER_CLIENT_ID - 1,
            "account_identity_sha256": expected_identity_hash("DU123456"),
            "contract_identity_sha256": sha256_json(
                canonical_contract_identity(contract)
            ),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=plan.order_binding.execution_client_id,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    status = SimpleNamespace(status="PreSubmitted", filled=0, remaining=1)
    trade = SimpleNamespace(contract=contract, order=order, orderStatus=status)
    position = SimpleNamespace(
        account="DU123456", contract=contract, position=Decimal("0"), avgCost=0
    )
    ib = SimpleNamespace(
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [position],
    )
    observer = ReadOnlyContinuityBroker(
        ib,
        account_identity_sha256=expected_identity_hash("DU123456"),
    )

    facts = observer.collect_continuity_facts(plan.order_binding, NOW)

    assert facts["ORDER_STATUS"]["value"] == "UNFILLED"
    assert facts["ORDER_REMAINING_QUANTITY"]["value"] == "1"
    assert facts["POSITION_EXISTS"]["value"] is False
    assert observer.read_only is True
    assert observer.client_id == OBSERVER_CLIENT_ID
    assert not hasattr(observer, "placeOrder")
    assert not hasattr(observer, "cancelOrder")


def test_production_poller_submits_at_most_one_exact_command(
    tmp_path, continuity_plan_factory, monkeypatch
) -> None:
    account_hash = expected_identity_hash("DU123456")
    contract = SimpleNamespace(
        conId=756733,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=[],
    )
    contract_identity = canonical_contract_identity(contract)
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract_identity),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    raw = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [],
        disconnect=lambda: None,
    )
    broker = ReadOnlyContinuityBroker(
        raw, account_identity_sha256=account_hash
    )

    path = tmp_path / "runtime.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        store = ContinuityStore(db)
        store.append_plan_event("ACTIVATED", plan)
        store.append_provider_event(
            plan.invocation_id,
            "TIMEOUT_CONFIRMED",
            {"failure_code": "MODEL_TIMEOUT"},
        )
        registry = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "continuity_state": "ACTIVE",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "order_ref": plan.order_binding.order_ref,
            "ibkr_order_id": plan.order_binding.ibkr_order_id,
            "perm_id": plan.order_binding.perm_id,
            "execution_client_id": WRITER_CLIENT_ID,
            "account": "DU123456",
            "action": "BUY",
            "contract": contract_identity,
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "registry-1",
                plan.order_binding.order_ref,
                plan.order_binding.ibkr_order_id,
                plan.order_binding.perm_id,
                plan.order_binding.ibkr_order_id,
                contract.conId,
                "BUY",
                "1",
                canonical_bytes(registry).decode("utf-8"),
                sha256_json(registry),
                NOW.isoformat(),
            ),
        )

        submitted = []

        class Coordinator:
            def submit(self, command):
                submitted.append(command)
                future = Future()
                future.set_result(
                    SimpleNamespace(
                        success=True,
                        status="RETAINED",
                        reason_codes=(),
                    )
                )
                return future

        coordinator = Coordinator()
        config = SimpleNamespace(
            initial_allocation=Decimal("500"),
            target_successor_epoch_id=None,
        )
        preflight = SimpleNamespace(expected_account_hash=account_hash)
        monkeypatch.setattr(
            "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
            lambda self: "ACTIVE",
        )
        poller = ProductionContinuityPoller(
            coordinator=coordinator,
            config=config,
            preflight=preflight,
        )

        poller(db, broker, coordinator)
        poller(db, broker, coordinator)

        assert len(submitted) == 1
        assert submitted[0].source == "WATCHDOG"
        assert submitted[0].execution_client_id == WRITER_CLIENT_ID
        assert db.execute(
            "SELECT COUNT(*) FROM continuity_execution_events"
        ).fetchone()[0] == 1


def test_production_alert_freezes_first_and_deduplicates_across_time(tmp_path) -> None:
    path = tmp_path / "alerts.sqlite3"
    with Database.open(path) as db:
        KillSwitchStore(db).set(
            "KILL_SWITCH_CLEAR", reason="test setup", actor="TEST"
        )
    trace = []
    times = iter(
        (
            datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 1, 14, 5, tzinfo=timezone.utc),
        )
    )

    class SMTP:
        def send(self, message):
            trace.append("smtp")
            return "smtp-receipt"

    class EventLog:
        def write(self, alert):
            trace.append("eventlog")
            return "eventlog-receipt"

    reporter = ProductionCriticalAlertReporter(
        db_path=path,
        smtp_config_path=tmp_path / "unused.env",
        launch_attempt_id="launch-1",
        smtp_factory=lambda path: SMTP(),
        event_log_factory=EventLog,
        now_utc=lambda: next(times),
    )

    reporter("CONTINUITY_WATCHDOG_FAILED")
    reporter("CONTINUITY_WATCHDOG_FAILED")

    with Database.open(path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"
        assert db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 1
    assert trace == ["eventlog", "smtp"]


def test_superseded_plan_reuses_only_exact_verified_broker_anchor(
    tmp_path, continuity_plan_factory
) -> None:
    account_hash = expected_identity_hash("DU123456")
    contract = {
        "conId": 756733,
        "symbol": "UTHR",
        "localSymbol": "UTHR",
        "secType": "BAG",
        "exchange": "SMART",
        "currency": "USD",
        "expiry": "",
        "strike": "0",
        "right": "",
        "multiplier": "100",
        "comboLegs": [],
        "attributes": {},
    }
    first = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract),
        }
    )
    successor = continuity_plan_factory(
        plan_id="plan-test-2",
        plan_version=2,
        predecessor_plan_sha256=first.sha256,
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract),
        },
    )
    registry = {
        "plan_sha256": first.sha256,
        "order_ref": first.order_binding.order_ref,
        "ibkr_order_id": first.order_binding.ibkr_order_id,
        "perm_id": first.order_binding.perm_id,
        "execution_client_id": WRITER_CLIENT_ID,
        "account": "DU123456",
        "action": "BUY",
        "contract": contract,
    }
    path = tmp_path / "anchor.sqlite3"
    with Database.open(path) as db:
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "registry-anchor",
                first.order_binding.order_ref,
                first.order_binding.ibkr_order_id,
                first.order_binding.perm_id,
                first.order_binding.ibkr_order_id,
                756733,
                "BUY",
                "1",
                canonical_bytes(registry).decode("utf-8"),
                sha256_json(registry),
                NOW.isoformat(),
            ),
        )

        binding = _verified_registry_binding(db, successor)

    assert binding is not None
    assert binding["plan_sha256"] == successor.sha256


def test_validate_only_constructs_composition_without_broker_io(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)
    calls = []

    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )

    def session_factory(**kwargs):
        calls.append(("configured", kwargs["client_id"], kwargs["read_only"]))

        def forbidden_connect():
            raise AssertionError("validate_only must not connect")

        return forbidden_connect

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.build_ibkr_session_factory",
        session_factory,
    )

    result = validate_production_composition(
        config=config,
        preflight=preflight,
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result["status"] == "PASS"
    assert result["broker_connections"] == 0
    assert result["broker_writes"] == 0
    assert result["model_executor_coordinated"] is True
    assert result["model_executor_armed"] is False
    assert result["writer_started"] is True
    assert result["writer_stopped"] is True
    assert result["watchdog_started"] is True
    assert result["watchdog_stopped"] is True
    assert result["writer_sole_capability"] is True
    assert result["legacy_direct_executor_selected"] is False
    assert result["production_gates_callable"] is True
    assert calls == [
        ("configured", WRITER_CLIENT_ID, False),
        ("configured", OBSERVER_CLIENT_ID, True),
    ]


def test_validate_only_reports_missing_alert_configuration_without_broker_io(
    tmp_path,
) -> None:
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["EXTERNAL_ALERT_CONFIGURATION_MISSING"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_rejects_invalid_validation_authority_hash(tmp_path) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="invalid",
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["PRODUCTION_VALIDATION_SHA256_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_blocks_an_armed_or_uncoordinated_model_executor(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_model_executor",
        lambda **_kwargs: SimpleNamespace(
            armed=True,
            is_coordinated_model_executor=False,
        ),
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["PRODUCTION_COMPOSITION_MODEL_EXECUTOR_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_reports_missing_schema_without_broker_io(tmp_path) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path):
        pass

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["CONTINUITY_SCHEMA_V3_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_shuts_down_partial_startup_and_reports_exact_stage(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )
    trace = []

    class Writer:
        execution_client_id = WRITER_CLIENT_ID
        production_authority_validator = SimpleNamespace(validate_before_write=lambda: None)
        execution_lock_verifier = lambda self: False

        def start(self):
            trace.append("writer_start")

        def wait_until_ready(self, _timeout):
            return True

        def stop(self, _timeout):
            trace.append("writer_stop")
            return True

    class Watchdog:
        def start(self, _timeout):
            trace.append("watchdog_start")
            raise RuntimeError("synthetic watchdog failure")

        def stop(self, _timeout):
            trace.append("watchdog_stop")
            return SimpleNamespace(stopped=True, timed_out=False)

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_authoritative_writer",
        lambda **_kwargs: Writer(),
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_continuity_watchdog",
        lambda **_kwargs: Watchdog(),
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result["status"] == "BLOCK"
    assert result["reason_codes"] == [
        "PRODUCTION_COMPOSITION_START_FAILED:RuntimeError"
    ]
    assert result["broker_connections"] == 0
    assert result["broker_writes"] == 0
    assert trace == [
        "writer_start",
        "watchdog_start",
        "watchdog_stop",
        "writer_stop",
    ]
