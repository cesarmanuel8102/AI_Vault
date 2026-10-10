from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import Future
import hashlib

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
    _ProductionSnapshotReader,
    _ProductionSleeveAuthoritySnapshotReader,
    build_ibkr_session_factory,
    validate_production_runtime_configuration,
    _verified_registry_binding,
    _collect_continuity_liability_evidence,
    _broker_evidence_collector,
    create_authoritative_writer,
    validate_production_composition,
)


def test_v4_writer_factory_wires_path_scoped_sleeve_authority(tmp_path, monkeypatch) -> None:
    from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4

    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    db_path = tmp_path / "runtime.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=db_path,
        paper_host="127.0.0.1",
        paper_port=4002,
        target_successor_epoch_id="AUTONOMY_EPOCH_3",
        target_successor_definition_sha256="1" * 64,
        initial_allocation=Decimal("500"),
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "b" * 40,
    )

    writer = create_authoritative_writer(
        coordinator=BrokerWriteCoordinator(),
        db_path=db_path,
        config=config,
        preflight=preflight,
        execution_lock_verifier=lambda: True,
        uncertainty_reporter=lambda _reason: None,
        toolbox=object(),
        production_validation_sha256="c" * 64,
        validation_broker_factory=lambda: object(),
        current_adapter_sha256="d" * 64,
    )

    assert writer.sleeve_authority_reservation_store is not None
    assert callable(writer.sleeve_authority_snapshot_reader)
    assert callable(writer.sleeve_broker_evidence_collector)
    assert writer.model_execution_engine.final_write_authority_required is True
    assert (
        writer.model_execution_engine._load().mechanics
        ._runtime_final_write_authority_required
        is True
    )


def test_bag_sleeve_evidence_resolves_every_leg_from_broker() -> None:
    from ibkr_paper_30d.contract_ownership import canonical_contract_identity
    from ibkr_paper_30d.production_continuity_runtime import (
        _sleeve_broker_evidence_collector,
    )

    parent = canonical_contract_identity(
        {
            "conId": 9000,
            "secType": "BAG",
            "currency": "USD",
            "exchange": "SMART",
            "comboLegs": [
                {"conId": 9001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
                {"conId": 9002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
            ],
        }
    )

    class Broker:
        def reqContractDetails(self, requested):
            con_id = int(requested.conId)
            return [
                SimpleNamespace(
                    contract=SimpleNamespace(
                        conId=con_id,
                        secType="OPT",
                        currency="USD",
                        exchange="SMART",
                        primaryExchange="",
                        localSymbol=f"LEG-{con_id}",
                        tradingClass="SPY",
                        multiplier="100",
                    )
                )
            ]

    request = SimpleNamespace(sha256="f" * 64)
    evidence = _sleeve_broker_evidence_collector("a" * 64)(
        Broker(),
        request,
        {
            "model_write_context": {
                "canonical_contract": parent.model_dump(mode="json"),
                "order_ref": "codex-order-1",
            },
            "production_authority": {
                "authority_snapshot_sha256": "b" * 64
            },
        },
    )

    assert evidence["contract_identity_sha256"] == parent.sha256
    assert evidence["order_ref"] == "codex-order-1"
    assert [item["con_id"] for item in evidence["ownership_contracts"]] == [
        9000,
        9001,
        9002,
    ]


def test_sleeve_broker_evidence_binds_target_writer_reconciliation_and_owner() -> None:
    from ibkr_paper_30d.contract_ownership import canonical_contract_identity
    from ibkr_paper_30d.production_continuity_runtime import (
        _sleeve_broker_evidence_collector,
    )

    contract = canonical_contract_identity(
        {
            "conId": 756733,
            "secType": "STK",
            "currency": "USD",
            "exchange": "SMART",
            "primaryExchange": "ARCA",
            "localSymbol": "SPY",
            "tradingClass": "SPY",
        }
    )
    request = SimpleNamespace(
        sha256="f" * 64,
        capital_sleeve=SimpleNamespace(value="CONTINUOUS_SLEEVE"),
        input_bundle=SimpleNamespace(
            multi_sleeve_portfolio={
                "transition_target_sha256": "1" * 64,
                "writer_binding_sha256": "2" * 64,
            },
            contract_ownership_snapshot={
                "contract_sleeves": {contract.sha256: "CONTINUOUS_SLEEVE"}
            },
            reconciliation_receipt={"status": "PASS"},
        ),
    )
    evidence = _sleeve_broker_evidence_collector("a" * 64)(
        SimpleNamespace(),
        request,
        {
            "model_write_context": {
                "canonical_contract": contract.model_dump(mode="json"),
                "order_ref": "codex-order-2",
            },
            "production_authority": {"authority_snapshot_sha256": "b" * 64},
        },
    )

    assert evidence["transition_target_sha256"] == "1" * 64
    assert evidence["writer_binding_sha256"] == "2" * 64
    assert evidence["reconciliation_status"] == "PASS"
    assert evidence["owned_contract_sleeve"] == "CONTINUOUS_SLEEVE"
    assert evidence["management_identity_match"] is True
    assert evidence["possible_live_connection"] is False


def test_v4_snapshot_reader_rejects_missing_or_non_hash_adapter_identity(tmp_path):
    config = SimpleNamespace(target_successor_definition_sha256="1" * 64)

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="CURRENT_ADAPTER_SHA256_REQUIRED",
    ):
        _ProductionSleeveAuthoritySnapshotReader(
            tmp_path / "runtime.sqlite3", config, "process-policy-v4"
        )


def test_multi_universe_composition_has_one_of_each_authority(tmp_path) -> None:
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.production_continuity_runtime import (
        build_multi_universe_runtime_stores,
        inject_multi_universe_runtime_stores,
        validate_multi_universe_runtime_topology,
    )

    with Database.open(tmp_path / "runtime.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        stores = build_multi_universe_runtime_stores(
            db, current_adapter_sha256="a" * 64
        )

    provider = SimpleNamespace()
    service = SimpleNamespace()
    coordinator = SimpleNamespace()
    writer = SimpleNamespace(execution_client_id=WRITER_CLIENT_ID)
    lock = object()
    inject_multi_universe_runtime_stores(stores, provider, service, coordinator, writer)
    report = validate_multi_universe_runtime_topology(
        providers=(provider,),
        service_loops=(service,),
        coordinators=(coordinator,),
        writers=(writer,),
        write_capable_client_ids=(WRITER_CLIENT_ID,),
        execution_locks=(lock,),
        stores=stores,
        direct_executor_selected=False,
    )

    assert report["status"] == "PASS"
    assert report["authority_counts"] == {
        "providers": 1,
        "service_loops": 1,
        "coordinators": 1,
        "writers": 1,
        "write_capable_clients": 1,
        "execution_locks": 1,
    }
    assert set(report["injected_stores"]) == {
        "capability",
        "ledger",
        "ownership",
        "reconciliation",
        "transition",
    }
    assert provider.multi_universe_stores is stores
    assert service.multi_universe_stores is stores
    assert coordinator.multi_universe_stores is stores
    assert writer.multi_universe_stores is stores


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"providers": (object(), object())}, "PROVIDER_COUNT_INVALID"),
        ({"service_loops": ()}, "SERVICE_LOOP_COUNT_INVALID"),
        ({"coordinators": (object(), object())}, "COORDINATOR_COUNT_INVALID"),
        ({"writers": (object(), object())}, "WRITER_COUNT_INVALID"),
        ({"write_capable_client_ids": (19761, 19763)}, "WRITE_CLIENT_COUNT_INVALID"),
        ({"execution_locks": ()}, "EXECUTION_LOCK_COUNT_INVALID"),
        ({"direct_executor_selected": True}, "DIRECT_EXECUTOR_FORBIDDEN"),
    ],
)
def test_multi_universe_composition_rejects_parallel_authority(update, reason) -> None:
    from ibkr_paper_30d.production_continuity_runtime import (
        MultiUniverseRuntimeStores,
        validate_multi_universe_runtime_topology,
    )

    values = {
        "providers": (object(),),
        "service_loops": (object(),),
        "coordinators": (object(),),
        "writers": (SimpleNamespace(execution_client_id=WRITER_CLIENT_ID),),
        "write_capable_client_ids": (WRITER_CLIENT_ID,),
        "execution_locks": (object(),),
        "stores": MultiUniverseRuntimeStores(
            ledger=object(),
            ownership=object(),
            capability=object(),
            reconciliation=object(),
            transition=object(),
        ),
        "direct_executor_selected": False,
    }
    values.update(update)

    report = validate_multi_universe_runtime_topology(**values)

    assert report["status"] == "BLOCK"
    assert reason in report["reason_codes"]


from ibkr_paper_30d.production_authority import ProductionBrokerEvidence
from production_epoch_v1_fixture import build_production_epoch_v1_fixture

NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def test_production_snapshot_accepts_anchored_legacy_epoch_history(tmp_path) -> None:
    path = tmp_path / "production.sqlite3"
    build_production_epoch_v1_fixture(path)
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    receipt = tmp_path / "auditor.json"
    policy = tmp_path / "market-policy.json"
    validation = tmp_path / "market-validation.json"
    for artifact in (receipt, policy, validation):
        artifact.write_text("{}", encoding="utf-8")
    artifact_sha256 = hashlib.sha256(b"{}").hexdigest()
    account_hash = expected_identity_hash("DU123456")
    broker = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        managedAccounts=lambda: ["DU123456"],
        all_order_visibility=True,
    )
    _broker_evidence_collector(path)(
        broker,
        SimpleNamespace(),
        {"open_orders": [], "positions": [], "executions": []},
    )
    config = SimpleNamespace(
        target_successor_epoch_id=None,
        initial_allocation=Decimal("500"),
        repo_root=Path(__file__).parents[2],
        auditor_receipt_path=receipt,
        market_policy_path=policy,
        market_validation_path=validation,
    )
    preflight = SimpleNamespace(
        expected_account_hash=account_hash,
        auditor_receipt_sha256=artifact_sha256,
        market_policy_sha256=artifact_sha256,
        market_validation_sha256=artifact_sha256,
    )

    snapshot = _ProductionSnapshotReader(
        db_path=path,
        config=config,
        preflight=preflight,
        execution_lock_verifier=lambda: True,
    )(SimpleNamespace(accepted_result_sha256="a" * 64))

    assert snapshot.authority_chains_valid is True


class FakeIB:
    def __init__(self) -> None:
        self.connect_calls = []
        self.RequestTimeout = 0.0
        self.request_timeout_at_connect = None
        self.disconnected = False

    def connect(self, host, port, **kwargs):
        self.request_timeout_at_connect = getattr(self, "RequestTimeout", None)
        self.connect_calls.append((host, port, kwargs))

    def isConnected(self):
        return True

    def managedAccounts(self):
        return ["DU123456"]

    def disconnect(self):
        self.disconnected = True


def test_broker_evidence_collector_returns_typed_evidence_and_persists_schema(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    broker = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        managedAccounts=lambda: ["DU123456"],
        all_order_visibility=True,
    )
    evidence = _broker_evidence_collector(path)(
        broker,
        SimpleNamespace(),
        {"open_orders": [], "positions": [], "executions": []},
    )

    assert isinstance(evidence, ProductionBrokerEvidence)
    assert evidence.account_identity_sha256 == expected_identity_hash("DU123456")
    with Database.open(path) as db:
        payload = db.execute(
            "SELECT payload_json FROM state_events "
            "WHERE event_type='BROKER_AUTHORITY_OBSERVATION_V1'"
        ).fetchone()[0]
    assert '"schema":"BROKER_AUTHORITY_OBSERVATION_V1"' in payload


def test_broker_evidence_collector_reuses_fresh_server_time_within_pacing_window(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    class PacedBroker:
        all_order_visibility = True

        def __init__(self) -> None:
            self.current_time_calls = 0

        def reqCurrentTime(self):
            self.current_time_calls += 1
            if self.current_time_calls > 1:
                raise TimeoutError("duplicate server-time request was paced")
            return NOW

        @staticmethod
        def managedAccounts():
            return ["DU123456"]

    broker = PacedBroker()
    collector = _broker_evidence_collector(path)
    raw = {"open_orders": [], "positions": [], "executions": []}

    first = collector(broker, SimpleNamespace(), raw)
    second = collector(broker, SimpleNamespace(), raw)

    assert first.broker_time_utc == NOW
    assert second.broker_time_utc == NOW
    assert broker.current_time_calls == 1
    with Database.open(path) as db:
        persisted = db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type='BROKER_AUTHORITY_OBSERVATION_V1'"
        ).fetchone()[0]
    assert persisted == 2


def test_broker_evidence_collector_refreshes_server_time_after_pacing_window(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    current = [NOW]

    class Broker:
        all_order_visibility = True

        def __init__(self) -> None:
            self.current_time_calls = 0

        def reqCurrentTime(self):
            self.current_time_calls += 1
            return current[0]

        @staticmethod
        def managedAccounts():
            return ["DU123456"]

    broker = Broker()
    collector = _broker_evidence_collector(path, now_utc=lambda: current[0])
    raw = {"open_orders": [], "positions": [], "executions": []}

    first = collector(broker, SimpleNamespace(), raw)
    current[0] += timedelta(seconds=16)
    second = collector(broker, SimpleNamespace(), raw)

    assert first.broker_time_utc == NOW
    assert second.broker_time_utc == NOW + timedelta(seconds=16)
    assert broker.current_time_calls == 2


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
    assert created[0].request_timeout_at_connect == 4.0
    assert created[0].connect_calls == [
        (
            "127.0.0.1",
            4002,
            {"clientId": client_id, "timeout": 4.0, "readonly": read_only},
        )
    ]


def test_missing_external_alert_configuration_fails_with_exact_reason(tmp_path) -> None:
    config = SimpleNamespace(repo_root=Path(tmp_path))

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="EXTERNAL_ALERT_CONFIGURATION_MISSING",
    ):
        validate_production_runtime_configuration(config)


def test_readonly_observer_returns_only_canonical_facts(
    continuity_plan_factory,
) -> None:
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


def test_readonly_observer_reuses_server_time_within_watchdog_tick() -> None:
    current = [0.0]

    class PacedBroker:
        def __init__(self) -> None:
            self.calls = 0

        def reqCurrentTime(self):
            self.calls += 1
            if self.calls > 1 and current[0] < 4.0:
                raise TimeoutError("duplicate server-time request was paced")
            return NOW + timedelta(seconds=self.calls)

    raw = PacedBroker()
    observer = ReadOnlyContinuityBroker(
        raw,
        account_identity_sha256=expected_identity_hash("DU123456"),
        monotonic=lambda: current[0],
    )

    first = observer.reqCurrentTime()
    second = observer.reqCurrentTime()

    assert first == second
    assert raw.calls == 1

    current[0] = 5.0
    refreshed = observer.reqCurrentTime()

    assert refreshed == NOW + timedelta(seconds=2)
    assert raw.calls == 2


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
    broker = ReadOnlyContinuityBroker(raw, account_identity_sha256=account_hash)

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
        assert (
            db.execute("SELECT COUNT(*) FROM continuity_execution_events").fetchone()[0]
            == 1
        )


def test_production_alert_freezes_first_and_deduplicates_across_time(tmp_path) -> None:
    path = tmp_path / "alerts.sqlite3"
    with Database.open(path) as db:
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="test setup", actor="TEST")
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
    assert result["liability_evidence_collector_callable"] is True
    assert calls == [
        ("configured", WRITER_CLIENT_ID, False),
        ("configured", OBSERVER_CLIENT_ID, True),
    ]


def test_production_liability_collector_proves_exact_vertical_maximum_loss() -> None:
    account_hash = expected_identity_hash("DU123456")
    combo_legs = [
        SimpleNamespace(conId=550001, ratio=1, action="BUY", exchange="SMART"),
        SimpleNamespace(conId=560001, ratio=1, action="SELL", exchange="SMART"),
    ]
    contract = SimpleNamespace(
        conId=0,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=combo_legs,
    )
    order = SimpleNamespace(
        orderRef="codex-order-78",
        orderId=78,
        permId=225256222,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=1,
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
        transmit=True,
        whatIf=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    canonical_contract = canonical_contract_identity(contract)
    leg_hashes = tuple(sha256_json(value) for value in canonical_contract["comboLegs"])
    requirement = SimpleNamespace(
        required_leg_identity_sha256=leg_hashes,
        maximum_evidence_age_seconds=Decimal("30"),
    )
    command = SimpleNamespace(
        order_ref=order.orderRef,
        ibkr_order_id=order.orderId,
        perm_id=order.permId,
        execution_client_id=order.clientId,
        account_identity_sha256=account_hash,
        contract_identity_sha256=sha256_json(canonical_contract),
        proposed_order_sha256="a" * 64,
        liability_requirement=requirement,
        resolved_total_quantity=Decimal("1"),
        resolved_limit_price=Decimal("3.50"),
        new_tif=None,
        new_good_till_date_utc=None,
        sha256="b" * 64,
    )
    option_contracts = {
        550001: SimpleNamespace(
            conId=550001,
            symbol="UTHR",
            secType="OPT",
            currency="USD",
            lastTradeDateOrContractMonth="20261016",
            strike=550,
            right="C",
            multiplier="100",
        ),
        560001: SimpleNamespace(
            conId=560001,
            symbol="UTHR",
            secType="OPT",
            currency="USD",
            lastTradeDateOrContractMonth="20261016",
            strike=560,
            right="C",
            multiplier="100",
        ),
    }
    what_if_orders = []

    class Broker:
        def reqAllOpenOrders(self):
            return [trade]

        def reqContractDetails(self, query):
            return [SimpleNamespace(contract=option_contracts[query.conId])]

        def whatIfOrder(self, exact_contract, proposed_order):
            assert exact_contract is contract
            what_if_orders.append(proposed_order)
            return SimpleNamespace(
                commission="1.00",
                initMarginChange="0",
                maintMarginChange="0",
                warningText="",
            )

    evidence = _collect_continuity_liability_evidence(Broker(), command, {})

    assert evidence.bounded is True
    assert evidence.maximum_loss == Decimal("350.00")
    assert evidence.covered_leg_identity_sha256 == leg_hashes
    assert evidence.account_identity_sha256 == account_hash
    assert evidence.contract_identity_sha256 == command.contract_identity_sha256
    assert evidence.proposed_order_sha256 == command.proposed_order_sha256
    assert evidence.command_sha256 == command.sha256
    assert len(what_if_orders) == 1
    assert what_if_orders[0].whatIf is True
    assert what_if_orders[0].transmit is True
    assert Decimal(str(what_if_orders[0].lmtPrice)) == Decimal("3.50")


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
        production_authority_validator = SimpleNamespace(
            validate_before_write=lambda: None
        )
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
