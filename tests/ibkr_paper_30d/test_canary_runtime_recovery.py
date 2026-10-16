from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3
import threading
import time

import pytest

import test_canary_execution as execution
import test_canary_pilot as pilot
from test_continuity_watchdog import Broker, _initialize
from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.canary_execution import CanaryExecutionAdapter
from ibkr_paper_30d.canary_candidate import CanaryDiscoveryOutcome
from ibkr_paper_30d.canary_pilot import CanaryPilotOrchestrator
from ibkr_paper_30d.continuity_watchdog import ContinuityWatchdog
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.product_capability import ProductCapabilityError
from ibkr_paper_30d import production_continuity_runtime as runtime


def test_adapter_identity_survives_new_launch_receipts_but_changes_with_code():
    from ibkr_paper_30d.epoch_manifest import product_adapter_sha256
    first = {"immutable_kernel_manifest_hash": "a" * 64,
             "epoch_manifest_sha256": "b" * 64, "created_at_utc": "2026-10-13T23:00:00Z"}
    restarted = {**first, "epoch_manifest_sha256": "c" * 64,
                 "created_at_utc": "2026-10-14T01:00:00Z"}
    assert product_adapter_sha256(first) == product_adapter_sha256(restarted)
    assert product_adapter_sha256({**restarted, "immutable_kernel_manifest_hash": "d" * 64}) != product_adapter_sha256(first)
    with pytest.raises(ValueError, match="PRODUCT_ADAPTER_KERNEL_HASH_REQUIRED"):
        product_adapter_sha256({"epoch_manifest_sha256": "e" * 64})


def test_new_candidate_same_adapter_preserves_prior_transmit_evidence(tmp_path):
    import test_product_capability as capability
    db, store = capability._store(tmp_path)
    try:
        family = capability._family()
        for step in capability.CERTIFICATION_SEQUENCE[:6]:
            capability._record(store, family, step)
        before = store.projection(family)
        after = store.record_read_only_candidate_evidence(
            family, evidence_sha256="d" * 64,
            account_sha256=capability.ACCOUNT, adapter_sha256=capability.ADAPTER,
            observed_at_utc=capability.NOW,
            expires_at_utc=capability.NOW + capability.timedelta(days=1),
            paper_limitations=("PAPER_SIMULATION_ONLY",))
        assert after.status == before.status
        assert after.completed_steps == before.completed_steps
        assert after.executable is False
    finally:
        db.close()


def test_writer_pumps_broker_events_while_queue_is_idle():
    pumped = threading.Event()
    broker = SimpleNamespace(sleep=lambda _: pumped.set(), disconnect=lambda: None)
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(), broker_factory=lambda _: broker,
        execution_client_id=19761, execution_lock_verifier=lambda: True,
        authority_validator=lambda *args: ())
    try:
        writer.start()
        assert writer.wait_until_ready(1)
        assert pumped.wait(1)
    finally:
        writer.stop(1)


def test_observer_collects_all_orders_once_per_poll():
    from test_authoritative_broker_writer import _trade
    from ibkr_paper_30d.open_order_management import canonical_open_order
    trade = _trade()
    calls = []
    raw = SimpleNamespace(reqAllOpenOrders=lambda: calls.append(1) or [trade])
    broker = runtime.ReadOnlyContinuityBroker(raw, account_identity_sha256="a" * 64)
    binding = SimpleNamespace(
        order_ref=trade.order.orderRef, ibkr_order_id=trade.order.orderId,
        perm_id=trade.order.permId, execution_client_id=trade.order.clientId,
        account_identity_sha256=runtime.expected_identity_hash(trade.order.account),
        contract_identity_sha256=runtime.sha256_json(canonical_open_order(trade)["contract"]))
    broker.begin_poll()
    assert broker._matching_order(binding) is not None
    assert broker._matching_order(binding) is not None
    assert len(calls) == 1
    broker.begin_poll()
    assert broker._matching_order(binding) is not None
    assert len(calls) == 2


def test_durable_canary_claim_is_blocked_by_current_kill_switch(tmp_path):
    from ibkr_paper_30d.experiment_control import KillSwitchStore
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    path = tmp_path / "claim.sqlite3"
    _initialize(path)
    with Database.open(path) as db:
        install_multi_universe_schema_v4(db)
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="TEST_INITIAL_STATE")
        KillSwitchStore(db).set("KILL_SWITCH_TRIGGERED", reason="TEST_WATCHDOG_FAILURE")
    assert runtime._ProductionCanaryStore(path).begin_write("new-entry") is False
    with Database.open(path) as db:
        assert db.execute("SELECT COUNT(*) FROM canary_authorization_events").fetchone()[0] == 0


def test_confirmed_prewrite_block_is_not_an_orphaned_broker_operation(tmp_path):
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    path = tmp_path / "prewrite-result.sqlite3"
    _initialize(path)
    with Database.open(path) as db:
        install_multi_universe_schema_v4(db)
        runtime._ProductionCanaryStore._append_in_transaction(
            db, authorization_id="candidate", event_type="AUTHORIZED",
            body={"candidate_sha256": "a" * 64})
        db.commit()
    store = runtime._ProductionCanaryStore(path)
    store.persist_result("a" * 64, {
        "status": "BLOCKED", "broker_write_boundary_crossed": False,
        "reason_codes": ["CONTINUITY_WATCHDOG_UNHEALTHY"]})
    assert store.has_orphaned_durable_state() is False


@pytest.mark.parametrize("clear", [False, None])
def test_canary_kill_switch_must_be_explicitly_clear(clear):
    request = execution._request()
    broker = execution.LifecycleBroker(execution._full_events())
    result = CanaryExecutionAdapter(
        begin_write=lambda key: True, now_utc=lambda: execution.NOW
    ).execute(request, broker, execution._evidence(request, kill_switch_clear=clear))
    assert result.status == "BLOCKED"
    assert "KILL_SWITCH_TRIGGERED" in result.reason_codes
    assert broker.calls == 0
    assert result.broker_write_boundary_crossed is False


def test_canary_rechecks_controls_after_contract_qualification():
    request = execution._request()
    controls = {"clear": True}
    class Gateway:
        all_order_visibility = True
        def reqAllOpenOrders(self): return []
        def reqExecutions(self): return []
        def positions(self): return []
        def qualifyContracts(self, contract):
            controls["clear"] = False
            return [contract]
        def placeOrder(self, *args):
            pytest.fail("kill switch must prevent this broker write")
    broker = Gateway()
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(), broker_factory=lambda _: broker,
        execution_client_id=19761, execution_lock_verifier=lambda: True,
        authority_validator=lambda *args: (),
        canary_execution_adapter=CanaryExecutionAdapter(
            begin_write=lambda key: True, now_utc=lambda: execution.NOW),
        canary_evidence_collector=lambda *args: execution._evidence(
            request, kill_switch_clear=controls["clear"]),
    )
    result = writer._execute(request, broker)
    assert result.status == "BLOCKED"
    assert result.reason_codes == ("KILL_SWITCH_TRIGGERED",)
    assert result.broker_write_boundary_crossed is False


def test_canary_writer_preserves_model_selected_ioc_terms():
    request = execution._request()
    request = request.model_copy(update={"entry_terms": request.entry_terms.model_copy(
        update={"time_in_force": "IOC"})})
    orders = []
    class Gateway:
        all_order_visibility = True
        def reqAllOpenOrders(self): return []
        def reqExecutions(self): return []
        def positions(self): return []
        def qualifyContracts(self, contract): return [contract]
        def placeOrder(self, contract, order):
            orders.append(order)
            return SimpleNamespace(orderStatus=SimpleNamespace(
                status="Cancelled", filled=0, remaining=order.totalQuantity))
    broker = Gateway()
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(), broker_factory=lambda _: broker,
        execution_client_id=19761, execution_lock_verifier=lambda: True,
        authority_validator=lambda *args: (),
        canary_execution_adapter=CanaryExecutionAdapter(
            begin_write=lambda key: True, now_utc=lambda: execution.NOW),
        canary_evidence_collector=lambda *args: execution._evidence(request))
    result = writer._execute(request, broker)
    assert result.status == "TERMINAL_NO_FILL"
    assert orders[0].tif == "IOC"
    assert orders[0].lmtPrice == float(request.entry_terms.limit_price)


def test_canary_blocks_during_watchdog_transient_recovery():
    request = execution._request()
    broker = execution.LifecycleBroker(execution._full_events())
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(), broker_factory=lambda _: broker,
        execution_client_id=19761, execution_lock_verifier=lambda: True,
        authority_validator=lambda *args: (),
        canary_execution_adapter=CanaryExecutionAdapter(
            begin_write=lambda key: True, now_utc=lambda: execution.NOW),
        canary_evidence_collector=lambda *args: execution._evidence(request))
    writer.canary_supervision_verifier = lambda: False
    result = writer._execute(request, broker)
    assert result.status == "BLOCKED"
    assert result.reason_codes == ("CONTINUITY_WATCHDOG_UNHEALTHY",)
    assert broker.calls == 0


@pytest.mark.parametrize("failure", [
    ProductCapabilityError("CERTIFICATION_ADAPTER_DRIFT"),
    sqlite3.DatabaseError("corrupt"),
    ProductCapabilityError("CERTIFICATION_CHAIN_MISMATCH"),
])
def test_candidate_cannot_bypass_failed_finalization_on_next_cycle(failure):
    proposal = pilot._proposal()
    store = pilot.Store()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE", proposal=proposal,
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256, transcript_sha256="a" * 64)
    def finalize(*args, **kwargs): raise failure
    orchestrator = CanaryPilotOrchestrator(
        discovery_runner=lambda *args: outcome,
        capability_evidence_collector=lambda *args: pilot._evidence(proposal),
        store=store, coordinator=object(), owner_pilot_authorization=pilot._owner(),
        writer_binding_sha256=pilot.WRITER, durable_sequence_allocator=lambda: 1,
        now_utc=lambda: pilot.NOW, candidate_finalizer=finalize)
    if str(failure) == "CERTIFICATION_ADAPTER_DRIFT":
        assert orchestrator.discover(object())["status"] == "BLOCK"
    else:
        with pytest.raises(type(failure)):
            orchestrator.discover(object())
    assert store.load_candidate() is None


def test_recertification_checks_other_contracts_in_same_family():
    proposal = pilot._proposal()
    bundle = SimpleNamespace(multi_sleeve_portfolio={"account_observation": {
        "positions": [{"contract": {"conId": 495759171, "secType": "CRYPTO",
                                    "exchange": "PAXOS"}, "position": 1}],
        "open_orders": [], "position_count": 1, "open_order_count": 0}})
    assert runtime._canary_family_exposure(bundle, proposal) == (0, 1)


def test_recertification_missing_observation_fails_closed():
    with pytest.raises(runtime.ProductionRuntimeConfigurationError,
                       match="CANARY_RECERTIFICATION_UNSAFE"):
        runtime._canary_family_exposure(SimpleNamespace(), pilot._proposal())


def test_watchdog_recovers_observation_after_alarm_without_clearing_kill(tmp_path):
    from ibkr_paper_30d.experiment_control import KillSwitchStore
    path = tmp_path / "watchdog.sqlite3"
    _initialize(path)
    with Database.open(path) as db:
        KillSwitchStore(db).set("KILL_SWITCH_TRIGGERED", reason="unrelated existing incident", actor="TEST")
    recovered = threading.Event()
    reports = []
    attempts = []
    def poll(*args):
        attempts.append(1)
        if len(attempts) <= 3: raise TimeoutError("gateway request timed out")
        recovered.set()
    watchdog = ContinuityWatchdog(
        db_factory=lambda: Database.open(path), broker_factory=Broker,
        poll_once=poll, coordinator=object(), broker_time_reader=lambda _: execution.NOW,
        poll_interval_seconds=0.01, heartbeat_max_age_seconds=1,
        uncertainty_reporter=reports.append, recover_after_failure_limit=True)
    watchdog._backoff_seconds = lambda *args: 0.01
    try:
        watchdog.start()
        assert recovered.wait(2)
        deadline = time.monotonic() + 1
        while not watchdog.is_healthy(execution.NOW) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert watchdog.is_healthy(execution.NOW)
        assert reports == []
    finally:
        watchdog.stop(2)
    with Database.open(path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"
        assert db.execute("SELECT COUNT(*) FROM continuity_watchdog_events WHERE event_type='RECOVERY_PENDING'").fetchone()[0] == 1


@pytest.mark.parametrize("code,message", [
    ("CODEX_PROVIDER_INVALID_JSONL", "CODEX_PROVIDER_INVALID_JSONL:invalid_jsonl"),
    ("RETURN_CODE_1", "CANARY_DISCOVERY_CODEX_PROVIDER_FAILED"),
])
def test_canary_provider_protocol_failure_is_recoverable_at_service_boundary(tmp_path, code, message):
    from test_autonomous_service import _authorized_production_topology, _make_passing_bundle
    from ibkr_paper_30d.autonomous_service import RecoverableProviderInvocationError
    with Database.open(tmp_path / "canary-provider.sqlite3") as db:
        service = _authorized_production_topology(db)
        service.multi_universe_runtime_authority = SimpleNamespace(transition_phase="CANARY_EXCLUSIVE")
        bundle = _make_passing_bundle()()
        bundle.multi_sleeve_portfolio = {
            "entry_eligibility": {}, "management_eligibility": {},
            "account_observation": {"open_order_count": 0}}
        service._builder = lambda: SimpleNamespace(build=lambda **kwargs: bundle)
        def execute(bundle):
            service.provider.last_failure_code = code
            raise RuntimeError(message)
        service.canary_pilot_orchestrator = SimpleNamespace(execute=execute)
        with pytest.raises(RecoverableProviderInvocationError):
            service._run_cycle_with_lifecycle("POSITION_EVENT")
        assert db.execute("SELECT COUNT(*) FROM alerts WHERE event_type='AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION'").fetchone()[0] == 1
