from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
from ibkr_paper_30d.broker_write_coordinator import (
    AuthorizedBrokerCommand,
    BrokerCommandType,
    BrokerWriteCoordinator,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.contract_ownership import canonical_contract_identity
from ibkr_paper_30d.coordinated_model_executor import (
    ModelExecutionOperation,
    ModelExecutionRequest,
)
from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.open_order_management import (
    canonical_open_order,
    canonical_order_contract_snapshot,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.sleeve_execution_authority import (
    SleeveAuthorityReservationStore,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.production_authority import (
    ProductionAuthoritySnapshot,
    ProductionAuthorityValidator,
    ProductionBrokerEvidence,
)
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle


def _trade():
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733, symbol="SPY", localSymbol="SPY", secType="STK",
            exchange="SMART", currency="USD",
            lastTradeDateOrContractMonth="", strike=0, right="", multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-writer", orderId=41, permId=9001,
            clientId=19761, account="DU123456", action="BUY", orderType="LMT",
            totalQuantity=2, lmtPrice=10, auxPrice=0, tif="DAY",
            goodTillDate="", outsideRth=False, parentId=0, ocaGroup="",
            transmit=True, conditions=[], goodAfterTime="",
            smartComboRoutingParams=[], algoStrategy="", algoParams=[],
            orderMiscOptions=[],
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0,
        ),
        fills=[],
    )


def _command(sequence=1, command_type=BrokerCommandType.CANCEL, **changes):
    snapshot = canonical_open_order(_trade())
    payload = {
        "command_id": f"command-{sequence}",
        "durable_sequence": sequence,
        "execution_key": f"execution-{sequence}",
        "source": "WATCHDOG",
        "command_type": command_type,
        "evaluation_id": f"evaluation-{sequence}",
        "evaluation_sha256": "1" * 64,
        "plan_id": "plan-1",
        "plan_sha256": "2" * 64,
        "fact_snapshot_sha256": "3" * 64,
        "order_ref": snapshot["orderRef"],
        "order_id": snapshot["orderId"],
        "perm_id": snapshot["permId"],
        "execution_client_id": snapshot["clientId"],
        "account_identity_sha256": expected_identity_hash(snapshot["account"]),
        "contract_identity_sha256": sha256_json(snapshot["contract"]),
        "observed_state_sha256": snapshot["state_sha256"],
        "authority_class": "PREAUTHORIZED_CONTINUITY",
        "new_total_quantity": None,
        "new_limit_price": None,
        "new_tif": None,
        "new_good_till_date_utc": None,
        "epoch_id": "AUTONOMY_EPOCH_2",
        "definition_sha256": "4" * 64,
        "owner_authorization_sha256": "5" * 64,
        "created_at_utc": datetime(2026, 10, 1, 14, tzinfo=timezone.utc),
    }
    payload.update(changes)
    payload["resolved_total_quantity"] = payload.get("new_total_quantity") or Decimal(
        str(snapshot["totalQuantity"])
    )
    payload["resolved_limit_price"] = payload.get("new_limit_price") or Decimal(
        str(snapshot["limitPrice"])
    )
    payload["proposed_order_sha256"] = sha256_json(
        {
            "order_ref": payload["order_ref"],
            "command_type": str(payload["command_type"]),
            "quantity": payload["resolved_total_quantity"],
            "limit_price": payload["resolved_limit_price"],
        }
    )
    payload["maximum_authorized_liability"] = Decimal("500")
    payload["liability_requirement"] = {
        "plan_id": payload["plan_id"],
        "plan_sha256": payload["plan_sha256"],
        "maximum_authorized_liability": payload["maximum_authorized_liability"],
        "account_identity_sha256": payload["account_identity_sha256"],
        "contract_identity_sha256": payload["contract_identity_sha256"],
        "proposed_order_sha256": payload["proposed_order_sha256"],
        "required_leg_identity_sha256": (payload["contract_identity_sha256"],),
        "maximum_evidence_age_seconds": "30",
    }
    return AuthorizedBrokerCommand.model_validate(payload)


class FakeGateway:
    def __init__(self, client_id, *, disconnect_after_write=False):
        self.client_id = client_id
        self.trade = _trade()
        self.cancel_calls = []
        self.place_calls = []
        self.disconnect_after_write = disconnect_after_write
        self.disconnected = False
        self.all_order_visibility = True

    def reqAllOpenOrders(self):
        return [self.trade]

    def reqExecutions(self):
        return []

    def positions(self):
        return []

    def cancelOrder(self, order):
        self.cancel_calls.append(order.orderId)
        if self.disconnect_after_write:
            raise ConnectionError("after cancel write")
        self.trade.orderStatus.status = "PendingCancel"
        return self.trade

    def placeOrder(self, contract, order):
        self.place_calls.append((contract.conId, order.orderId))
        if self.disconnect_after_write:
            raise ConnectionError("after modify write")
        self.trade.order = order
        return self.trade

    def disconnect(self):
        self.disconnected = True


class PositionGateway(FakeGateway):
    def __init__(self, client_id, *, quantity=Decimal("4")):
        super().__init__(client_id)
        self.position = SimpleNamespace(
            account="DU123456",
            contract=self.trade.contract,
            position=quantity,
            avgCost=Decimal("118.60"),
        )
        self.client = SimpleNamespace(getReqId=lambda: 84)

    def positions(self):
        return [self.position]

    def placeOrder(self, contract, order):
        self.place_calls.append((contract.conId, order.orderId))
        order.permId = 9100
        order.clientId = self.client_id
        self.trade = SimpleNamespace(
            contract=contract,
            order=order,
            orderStatus=SimpleNamespace(
                status="PreSubmitted", filled=0, remaining=order.totalQuantity,
                avgFillPrice=0,
            ),
            fills=[],
        )
        return self.trade


class ImmediateFillPositionGateway(PositionGateway):
    def __init__(self, client_id):
        super().__init__(client_id)
        self._filled = False
        self.execution = None

    def reqAllOpenOrders(self):
        return [] if self._filled else [self.trade]

    def reqExecutions(self):
        return [] if self.execution is None else [self.execution]

    def positions(self):
        return [] if self._filled else [self.position]

    def placeOrder(self, contract, order):
        self.place_calls.append((contract.conId, order.orderId))
        self._filled = True
        self.execution = SimpleNamespace(
            contract=contract,
            execution=SimpleNamespace(
                orderRef=order.orderRef,
                orderId=order.orderId,
                permId=9200,
                clientId=self.client_id,
                acctNumber=order.account,
                shares=order.totalQuantity,
                side="SLD",
            ),
        )
        return SimpleNamespace(
            contract=contract,
            order=order,
            orderStatus=SimpleNamespace(
                status="Filled",
                filled=order.totalQuantity,
                remaining=0,
                avgFillPrice=119,
            ),
            fills=[self.execution],
        )


class TimeoutAwareGateway(FakeGateway):
    def __init__(self, client_id):
        super().__init__(client_id)
        self.RequestTimeout = None


class OpenOrdersTimeoutGateway(FakeGateway):
    def reqAllOpenOrders(self):
        raise TimeoutError("simulated stalled IBKR request")


class GatewayFactory:
    def __init__(self, **gateway_options):
        self.gateway_options = gateway_options
        self.connection_ids = []
        self.gateway = None

    def __call__(self, client_id):
        if client_id in self.connection_ids:
            raise RuntimeError("326 duplicate client id")
        self.connection_ids.append(client_id)
        self.gateway = FakeGateway(client_id, **self.gateway_options)
        return self.gateway


def _start_writer(
    *,
    validator=lambda command, evidence: (),
    factory=None,
    lock_verifier=lambda: True,
    attempt_persister=None,
    result_persister=None,
    model_execution_engine=None,
    production_validation_sha256="6" * 64,
    **writer_kwargs,
):
    coordinator = BrokerWriteCoordinator()
    factory = factory or GatewayFactory()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=factory,
        execution_client_id=19761,
        execution_lock_verifier=lock_verifier,
        authority_validator=validator,
        attempt_persister=attempt_persister,
        result_persister=result_persister,
        model_execution_engine=model_execution_engine,
        production_validation_sha256=production_validation_sha256,
        **writer_kwargs,
    )
    writer.start()
    assert writer.wait_until_ready(2)
    return coordinator, writer, factory


def test_writer_thread_owns_event_loop_for_real_broker_session():
    observed = {}

    def broker_factory(client_id):
        observed["loop"] = asyncio.get_event_loop()
        return FakeGateway(client_id)

    coordinator = BrokerWriteCoordinator()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=broker_factory,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda command, evidence: (),
    )

    writer.start()
    try:
        assert writer.wait_until_ready(2)
    finally:
        assert writer.stop(2)

    assert observed["loop"].is_closed() is True


def test_writer_applies_bounded_timeout_to_broker_session():
    factory = GatewayFactory()
    factory.gateway_options = {}

    def broker_factory(client_id):
        gateway = TimeoutAwareGateway(client_id)
        factory.gateway = gateway
        return gateway

    coordinator = BrokerWriteCoordinator()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=broker_factory,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda command, evidence: (),
        broker_request_timeout_seconds=15,
    )

    writer.start()
    try:
        assert writer.wait_until_ready(2)
        assert factory.gateway.RequestTimeout == 15.0
    finally:
        assert writer.stop(2)


def test_open_orders_timeout_has_deterministic_reason_code():
    coordinator = BrokerWriteCoordinator()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=lambda client_id: OpenOrdersTimeoutGateway(client_id),
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda command, evidence: (),
    )

    decision, evidence, reasons = writer._production_authority_read(
        request=_model_request(1, ModelExecutionOperation.NEW_TRADE),
        broker=OpenOrdersTimeoutGateway(19761),
    )

    assert decision is None
    assert evidence == {}
    assert reasons == ("BROKER_EVIDENCE_OPEN_ORDERS_TIMEOUT",)


def _model_request(sequence: int, operation: ModelExecutionOperation):
    payload = {
        ModelExecutionOperation.NEW_TRADE: AutonomousTradeProposal(
            thesis="test", symbol="SPY", sec_type="STK", direction="LONG",
            action="BUY", quantity="1", order_type="LMT", limit_price="1",
            capital_required="1", maximum_loss="1", loss_is_bounded=True,
            probability_profit="0.6", probability_loss="0.4",
            expected_gain="1", expected_loss="1", expected_value="0.2",
            expected_holding_period="one day", entry_condition="entry",
            invalidation_condition="invalid", exit_plan="exit",
            alternatives_considered=["cash"], evidence_used=["PAPER"],
            disconfirming_evidence=["spread"], confidence="0.6",
        ),
        ModelExecutionOperation.OPEN_ORDER_ACTION: AutonomousOpenOrderAction(
            order_ref="order-1", order_id=41, perm_id=9001, client_id=19761,
            contract_id=756733, observed_state_sha256="7" * 64,
            reason="cancel",
        ),
        ModelExecutionOperation.POSITION_ACTION: AutonomousPositionAction(
            symbol="SPY", sec_type="STK", action="SELL", quantity="1",
            order_type="LMT", limit_price="1", contract_id=756733,
            reason="reduce",
        ),
    }[operation]
    decision = {
        ModelExecutionOperation.NEW_TRADE: TraderDecision.PROPOSE_TRADE,
        ModelExecutionOperation.OPEN_ORDER_ACTION: TraderDecision.CANCEL_ORDER,
        ModelExecutionOperation.POSITION_ACTION: TraderDecision.REDUCE_POSITION,
    }[operation]
    bundle = TraderInputBundle(
        decision_cycle_id=f"cycle-{sequence}", utc_timestamp="2026-10-02T14:00:00Z",
        market_session_state="OPEN", reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={}, broker_account_snapshot={},
        positions_snapshot=[], open_orders_snapshot=[], risk_snapshot={},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"}, candidate_screen_results=[],
        relevant_previous_immutable_decisions=[], process_policy_version="v1",
        execution_realism_version="v1", benchmark_state={},
    )
    return ModelExecutionRequest(
        request_id=f"model-request-{sequence}", durable_sequence=sequence,
        execution_key=f"model-execution-{sequence}", source="MODEL",
        operation=operation, launch_attempt_id="launch-1",
        epoch_id="AUTONOMY_EPOCH_2", approved_head="a" * 40,
        account_identity_sha256="b" * 64, invocation_id=f"invocation-{sequence}",
        decision_cycle_id=bundle.decision_cycle_id, accepted_decision=decision,
        accepted_result_sha256="c" * 64, payload=payload,
        payload_sha256=sha256_json(payload), input_bundle=bundle,
        input_bundle_sha256=bundle.sha256, created_at_utc=datetime(
            2026, 10, 2, 14, tzinfo=timezone.utc
        ),
    )


class RecordingModelEngine:
    def __init__(self, *, block=None, raises=False):
        self.calls = []
        self.block = block
        self.raises = raises

    def execute(
        self,
        broker,
        request,
        authority_context,
        final_write_authority_check=None,
    ):
        self.calls.append((broker, request, authority_context, threading.get_ident()))
        if final_write_authority_check is not None:
            reasons = tuple(final_write_authority_check())
            if reasons:
                return PaperExecutionResult(False, "BLOCKED", reasons, {}, {})
        if self.block is not None:
            self.block.wait(2)
        if self.raises:
            raise RuntimeError("model engine failed")
        return PaperExecutionResult(
            True, request.operation.value, (), {"request": request.request_id}, {}
        )


def test_v4_writer_reserves_sleeve_authority_before_write_boundary(tmp_path):
    from test_sleeve_execution_authority import _broker, _snapshot, _v4_request

    events = []
    request = _v4_request()

    class FinalGateEngine:
        def execute(
            self,
            broker,
            candidate,
            authority_context,
            final_write_authority_check=None,
        ):
            events.append("what_if")
            reasons = tuple(
                final_write_authority_check(
                    {"canonical_contract": _broker(candidate)["canonical_contract"]}
                )
            )
            if reasons:
                return PaperExecutionResult(False, "BLOCKED", reasons, {}, {})
            events.append("write")
            return PaperExecutionResult(True, "SUBMITTED", (), {}, {})

    with Database.open(tmp_path / "writer-v4.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        reservation_store = SleeveAuthorityReservationStore(db)
        from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
        SleeveLedgerStore(db).bootstrap_extended()

        def snapshot_reader(candidate):
            assert db.connection.in_transaction is True
            events.append("db")
            return _snapshot(candidate)

        coordinator = BrokerWriteCoordinator()
        capability = coordinator.attach_writer()
        writer = AuthoritativeBrokerWriter(
            coordinator,
            broker_factory=GatewayFactory(),
            execution_client_id=19761,
            execution_lock_verifier=lambda: True,
            authority_validator=lambda command, evidence: (),
            model_execution_engine=FinalGateEngine(),
            production_validation_sha256="6" * 64,
            attempt_persister=lambda candidate, evidence: events.append("attempt"),
            sleeve_authority_reservation_store=reservation_store,
            sleeve_authority_snapshot_reader=snapshot_reader,
            sleeve_broker_evidence_collector=lambda broker, candidate, raw: (
                events.append("broker")
                or (
                    _broker(candidate)
                    if raw["model_write_context"]["canonical_contract"]
                    == _broker(candidate)["canonical_contract"]
                    else (_ for _ in ()).throw(AssertionError("missing write context"))
                )
            ),
        )
        future = coordinator.submit(request)
        claimed_request, _ = coordinator.claim(capability, timeout=0.1)
        result = writer._execute_model(claimed_request, FakeGateway(19761))
        future.set_result(result)
        coordinator.task_done(capability)
        coordinator.detach_writer(capability)

        assert result.success is True
        assert events == ["what_if", "broker", "db", "attempt", "write"]
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_authority_events"
        ).fetchone()[0] == 1


def test_all_model_operations_dispatch_on_one_writer_thread_and_broker():
    engine = RecordingModelEngine()
    coordinator, writer, factory = _start_writer(model_execution_engine=engine)
    try:
        results = [
            coordinator.submit(_model_request(index, operation)).result(2)
            for index, operation in enumerate(ModelExecutionOperation, start=1)
        ]
    finally:
        writer.stop(2)

    assert [result.status for result in results] == [item.value for item in ModelExecutionOperation]
    assert len({id(call[0]) for call in engine.calls}) == 1
    assert len({call[3] for call in engine.calls}) == 1
    assert factory.connection_ids == [19761]
    assert all(call[2].request_sha256 == call[1].sha256 for call in engine.calls)


def test_model_request_without_engine_blocks_before_broker_write():
    coordinator, writer, factory = _start_writer(model_execution_engine=None)
    try:
        result = coordinator.submit(
            _model_request(1, ModelExecutionOperation.NEW_TRADE)
        ).result(2)
    finally:
        writer.stop(2)

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("MODEL_EXECUTION_ENGINE_REQUIRED",)
    assert factory.gateway.cancel_calls == []
    assert factory.gateway.place_calls == []


def test_second_writer_cannot_claim_shared_coordinator():
    coordinator, writer, _ = _start_writer()
    second = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=GatewayFactory(),
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda command, evidence: (),
    )
    try:
        with pytest.raises(RuntimeError, match="AUTHORITATIVE_WRITER_ALREADY_ATTACHED"):
            second.start()
    finally:
        writer.stop(2)


def test_writer_shutdown_marks_queued_model_request_uncertain():
    release = threading.Event()
    engine = RecordingModelEngine(block=release)
    coordinator, writer, _ = _start_writer(model_execution_engine=engine)
    first = coordinator.submit(_model_request(1, ModelExecutionOperation.NEW_TRADE))
    second = coordinator.submit(_model_request(2, ModelExecutionOperation.POSITION_ACTION))
    for _ in range(100):
        if engine.calls:
            break
        threading.Event().wait(0.01)
    writer._stop.set()
    release.set()
    assert writer.stop(2)

    assert first.result(1).status == "NEW_TRADE"
    assert second.result(1).status == "UNCERTAIN"
    assert second.result().reason_codes == ("WRITER_STOPPED_WITH_PENDING_COMMAND",)


def test_model_engine_failure_is_uncertain_and_not_retried():
    engine = RecordingModelEngine(raises=True)
    coordinator, writer, factory = _start_writer(model_execution_engine=engine)
    try:
        result = coordinator.submit(
            _model_request(1, ModelExecutionOperation.NEW_TRADE)
        ).result(2)
    finally:
        writer.stop(2)

    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("WRITER_INTERNAL_FAILURE:RuntimeError",)
    assert len(engine.calls) == 1
    assert factory.connection_ids == [19761]


def test_model_and_watchdog_commands_share_one_writer_owned_client_id():
    coordinator, writer, factory = _start_writer()
    try:
        retain = coordinator.submit(
            _command(1, BrokerCommandType.RETAIN, source="MODEL")
        ).result(2)
        cancel = coordinator.submit(_command(2)).result(2)
    finally:
        writer.stop(2)

    assert retain.success is True
    assert cancel.success is True
    assert factory.connection_ids == [19761]
    assert factory.gateway.cancel_calls == [41]


def _position_command(*, command_type=BrokerCommandType.CLOSE_POSITION, quantity="4"):
    contract = _trade().contract
    contract_sha = canonical_contract_identity(
        {
            "conId": contract.conId,
            "secType": contract.secType,
            "currency": contract.currency,
            "exchange": contract.exchange,
            "localSymbol": contract.localSymbol,
            "multiplier": contract.multiplier,
        }
    ).sha256
    account_sha = expected_identity_hash("DU123456")
    position_sha = sha256_json(
        {
            "account_identity_sha256": account_sha,
            "canonical_contract_sha256": contract_sha,
            "signed_quantity": "4",
        }
    )
    return _command(
        1,
        command_type,
        authority_class=(
            "CLOSE_POSITION"
            if command_type == BrokerCommandType.CLOSE_POSITION
            else "REDUCE_POSITION"
        ),
        account_identity_sha256=account_sha,
        contract_identity_sha256=contract_sha,
        canonical_contract_sha256=contract_sha,
        position_identity_sha256=position_sha,
        position_action="SELL",
        position_quantity=Decimal(quantity),
        position_order_type="MKT",
        position_limit_price=None,
    )


def test_writer_executes_exact_model_authored_position_close():
    gateway = PositionGateway(19761)
    coordinator, writer, _ = _start_writer(factory=lambda _: gateway)
    try:
        result = coordinator.submit(_position_command()).result(2)
    finally:
        writer.stop(2)

    assert result.success is True
    assert result.status == "BROKER_BOUND"
    assert result.order["orderId"] == 84
    assert result.order["permId"] == 9100
    assert gateway.trade.order.action == "SELL"
    assert Decimal(str(gateway.trade.order.totalQuantity)) == Decimal("4")
    assert gateway.trade.order.orderType == "MKT"


def test_writer_accepts_exact_immediate_fill_when_order_leaves_open_orders():
    gateway = ImmediateFillPositionGateway(19761)
    coordinator, writer, _ = _start_writer(factory=lambda _: gateway)
    try:
        result = coordinator.submit(_position_command()).result(2)
    finally:
        writer.stop(2)

    assert result.success is True
    assert result.status == "FILLED"
    assert result.order == {
        "orderRef": result.order["orderRef"],
        "orderId": 84,
        "permId": 9200,
        "status": "Filled",
    }
    assert result.broker_validation["post_write_position_quantity"] == "0"
    assert writer._frozen_order_refs == set()


def test_writer_blocks_position_continuity_when_broker_position_changed():
    gateway = PositionGateway(19761, quantity=Decimal("3"))
    coordinator, writer, _ = _start_writer(factory=lambda _: gateway)
    try:
        result = coordinator.submit(_position_command()).result(2)
    finally:
        writer.stop(2)

    assert result.success is False
    assert result.reason_codes == ("CONTINUITY_POSITION_IDENTITY_CHANGED",)
    assert gateway.place_calls == []


def test_queue_is_fifo_and_final_authority_is_reread_for_each_command():
    observed = []

    def validator(command, evidence):
        observed.append(command.durable_sequence)
        return () if command.durable_sequence == 1 else ("PLAN_STATE_CHANGED",)

    coordinator, writer, factory = _start_writer(validator=validator)
    try:
        first = coordinator.submit(_command(1, BrokerCommandType.RETAIN))
        second = coordinator.submit(_command(2, BrokerCommandType.CANCEL))
        assert first.result(2).success is True
        blocked = second.result(2)
    finally:
        writer.stop(2)

    assert observed == [1, 1, 2]
    assert blocked.status == "BLOCKED"
    assert blocked.reason_codes == ("PLAN_STATE_CHANGED",)
    assert factory.gateway.cancel_calls == []


def test_writer_continues_while_model_caller_is_blocked():
    coordinator, writer, factory = _start_writer()
    model_block = threading.Event()
    model_finished = threading.Event()

    def blocked_model():
        model_block.wait(2)
        model_finished.set()

    thread = threading.Thread(target=blocked_model)
    thread.start()
    try:
        result = coordinator.submit(_command(1)).result(2)
        assert result.success is True
        assert model_finished.is_set() is False
    finally:
        model_block.set()
        thread.join(2)
        writer.stop(2)

    assert factory.gateway.cancel_calls == [41]


def test_nonowner_or_stale_order_identity_blocks_without_write():
    coordinator, writer, factory = _start_writer()
    try:
        nonowner = coordinator.submit(
            _command(1, execution_client_id=88)
        ).result(2)
        stale = coordinator.submit(
            _command(2, observed_state_sha256="0" * 64)
        ).result(2)
    finally:
        writer.stop(2)

    assert nonowner.reason_codes == ("NON_OWNER_EXECUTION_CLIENT",)
    assert stale.reason_codes == ("OPEN_ORDER_STATE_CHANGED",)
    assert factory.gateway.cancel_calls == []


def test_modify_changes_only_preauthorized_mutable_fields():
    coordinator, writer, factory = _start_writer()
    try:
        result = coordinator.submit(
            _command(
                1,
                BrokerCommandType.MODIFY,
                new_total_quantity=Decimal("1"),
                new_limit_price=Decimal("9.50"),
                new_tif="GTD",
                new_good_till_date_utc=datetime(
                    2026, 10, 1, 19, 30, tzinfo=timezone.utc
                ),
            )
        ).result(2)
    finally:
        writer.stop(2)

    assert result.success is True
    modified = factory.gateway.trade.order
    assert modified.orderId == 41
    assert modified.permId == 9001
    assert modified.totalQuantity == 1.0
    assert modified.lmtPrice == 9.5
    assert modified.tif == "GTD"
    assert modified.goodTillDate.startswith("20261001 19:30:00")


def test_disconnect_after_write_is_uncertain_and_freezes_order():
    factory = GatewayFactory(disconnect_after_write=True)
    coordinator, writer, factory = _start_writer(factory=factory)
    try:
        uncertain = coordinator.submit(_command(1)).result(2)
        frozen = coordinator.submit(_command(2)).result(2)
    finally:
        writer.stop(2)

    assert uncertain.status == "UNCERTAIN"
    assert uncertain.reason_codes == ("CONTINUITY_ORDER_STATE_UNCERTAIN",)
    assert frozen.status == "BLOCKED"
    assert frozen.reason_codes == ("ORDER_WRITE_AUTHORITY_FROZEN",)


def test_duplicate_execution_key_is_blocked():
    coordinator, writer, _ = _start_writer()
    try:
        first = coordinator.submit(_command(1, BrokerCommandType.RETAIN)).result(2)
        duplicate = coordinator.submit(
            _command(2, BrokerCommandType.RETAIN, execution_key="execution-1")
        ).result(2)
    finally:
        writer.stop(2)

    assert first.success is True
    assert duplicate.reason_codes == ("DUPLICATE_EXECUTION_KEY",)


def test_missing_execution_lock_blocks_before_write():
    coordinator, writer, factory = _start_writer(lock_verifier=lambda: False)
    try:
        result = coordinator.submit(_command(1)).result(2)
    finally:
        writer.stop(2)

    assert result.reason_codes == ("EXECUTION_LOCK_REQUIRED",)
    assert factory.gateway.cancel_calls == []


def test_uncertain_all_order_visibility_blocks_before_write():
    coordinator, writer, factory = _start_writer()
    factory.gateway.all_order_visibility = False
    try:
        result = coordinator.submit(_command(1)).result(2)
    finally:
        writer.stop(2)

    assert result.status == "BLOCKED"
    assert result.reason_codes[0].startswith("BROKER_EVIDENCE_UNAVAILABLE")
    assert factory.gateway.cancel_calls == []


def test_partial_fill_prevents_modify_to_zero_remainder():
    coordinator, writer, factory = _start_writer()
    factory.gateway.trade.orderStatus.filled = 1
    factory.gateway.trade.orderStatus.remaining = 1
    snapshot = canonical_open_order(factory.gateway.trade)
    try:
        result = coordinator.submit(
            _command(
                1,
                BrokerCommandType.MODIFY,
                observed_state_sha256=snapshot["state_sha256"],
                new_total_quantity=Decimal("1"),
            )
        ).result(2)
    finally:
        writer.stop(2)

    assert result.reason_codes == ("ORDER_WOULD_HAVE_NO_REMAINING_QUANTITY",)
    assert factory.gateway.place_calls == []


def test_result_persistence_failure_after_ack_is_uncertain_and_not_retried():
    def fail_result(command, result, evidence):
        raise OSError("disk unavailable")

    coordinator, writer, factory = _start_writer(result_persister=fail_result)
    try:
        uncertain = coordinator.submit(_command(1)).result(2)
        frozen = coordinator.submit(_command(2)).result(2)
    finally:
        writer.stop(2)

    assert uncertain.reason_codes == ("CONTINUITY_ORDER_STATE_UNCERTAIN",)
    assert frozen.reason_codes == ("ORDER_WRITE_AUTHORITY_FROZEN",)
    assert factory.gateway.cancel_calls == [41]


def test_queue_claim_requires_private_writer_capability():
    coordinator = BrokerWriteCoordinator()
    with pytest.raises(PermissionError, match="WRITER_CAPABILITY_REQUIRED"):
        coordinator.claim(object(), timeout=0)


def test_writer_source_contains_no_global_cancel_path():
    source = inspect.getsource(AuthoritativeBrokerWriter)
    assert "reqGlobalCancel" not in source


def _production_snapshot(command, **updates):
    values = {
        "snapshot_id": "authority-1",
        "observed_at_utc": datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
        "lock_owned_by_process": True,
        "approved_head": "a" * 40,
        "runtime_provenance_valid": True,
        "environment": "PAPER",
        "account_identity_sha256": command.account_identity_sha256,
        "owner_authorization_valid": True,
        "epoch_id": command.epoch_id,
        "clock_active": True,
        "kill_switch_clear": True,
        "auditor_gate_pass": True,
        "market_data_gate_pass": True,
        "continuity_schema_valid": True,
        "authority_chains_valid": True,
        "active_plan_sha256": command.plan_sha256,
        "binding_plan_sha256": command.plan_sha256,
        "provider_state_allows": True,
        "accepted_result_sha256": "c" * 64,
        "review_allows": True,
        "execution_count": 0,
        "maximum_execution_count": 1,
        "used_execution_keys": (),
        "order_state_sha256": command.observed_state_sha256,
        "positions_sha256": "1" * 64,
        "executions_sha256": "2" * 64,
        "experiment_capital_boundary": "500",
        "sqlite_write_transaction_active": False,
    }
    values.update(updates)
    return ProductionAuthoritySnapshot.model_validate(values)


def _production_broker_evidence(command):
    now = datetime(2026, 10, 2, 14, tzinfo=timezone.utc)
    return ProductionBrokerEvidence(
        evidence_id="broker-evidence-1",
        collected_at_utc=now,
        broker_time_utc=now,
        fresh_until_utc=now + timedelta(seconds=30),
        account_identity_sha256=command.account_identity_sha256,
        all_order_visibility=True,
        open_orders_sha256="3" * 64,
        positions_sha256="1" * 64,
        executions_sha256="2" * 64,
        target_order_state_sha256=getattr(
            command, "observed_state_sha256", "f" * 64
        ),
        evidence_sha256="4" * 64,
    )


def test_production_writer_orders_external_evidence_db_reads_and_short_persistence():
    events = []
    command = _command(1)
    validator = ProductionAuthorityValidator(
        snapshot_reader=lambda request: (
            events.append("db") or _production_snapshot(command)
        ),
        expected_approved_head="a" * 40,
    )
    factory = GatewayFactory()
    coordinator = BrokerWriteCoordinator()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=factory,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda request, evidence: (),
        production_authority_validator=validator,
        production_broker_evidence_collector=lambda broker, request, raw: (
            events.append("broker") or _production_broker_evidence(command)
        ),
        attempt_persister=lambda request, evidence: events.append("attempt"),
        result_persister=lambda request, result, evidence: events.append("result"),
        now_utc=lambda: datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
    )
    writer.start()
    assert writer.wait_until_ready(2)
    original_cancel = factory.gateway.cancelOrder

    def record_cancel(order):
        events.append("write")
        return original_cancel(order)

    factory.gateway.cancelOrder = record_cancel
    try:
        result = coordinator.submit(command).result(2)
    finally:
        writer.stop(2)

    assert result.success is True
    assert events == ["broker", "db", "broker", "db", "attempt", "write", "result"]


def test_production_writer_blocks_db_race_after_broker_collection_without_write():
    command = _command(1)
    snapshots = iter(
        [
            _production_snapshot(command, snapshot_id="first"),
            _production_snapshot(
                command,
                snapshot_id="second",
                experiment_capital_boundary="499",
            ),
        ]
    )
    validator = ProductionAuthorityValidator(
        snapshot_reader=lambda request: next(snapshots),
        expected_approved_head="a" * 40,
    )
    coordinator = BrokerWriteCoordinator()
    factory = GatewayFactory()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=factory,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda request, evidence: (),
        production_authority_validator=validator,
        production_broker_evidence_collector=lambda broker, request, raw: (
            _production_broker_evidence(command)
        ),
        now_utc=lambda: datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
    )
    writer.start()
    assert writer.wait_until_ready(2)
    try:
        result = coordinator.submit(command).result(2)
    finally:
        writer.stop(2)

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("AUTHORITY_STATE_CHANGED_DURING_VALIDATION",)
    assert factory.gateway.cancel_calls == []


def test_model_final_what_if_precedes_final_authority_read_and_attempt():
    events = []
    request = _model_request(1, ModelExecutionOperation.NEW_TRADE)

    def snapshot_reader(candidate):
        events.append("db")
        return ProductionAuthoritySnapshot(
            snapshot_id=f"authority-{events.count('db')}",
            observed_at_utc=datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
            lock_owned_by_process=True,
            approved_head=request.approved_head,
            runtime_provenance_valid=True,
            environment="PAPER",
            account_identity_sha256=request.account_identity_sha256,
            owner_authorization_valid=True,
            epoch_id=request.epoch_id,
            clock_active=True,
            kill_switch_clear=True,
            auditor_gate_pass=True,
            market_data_gate_pass=True,
            continuity_schema_valid=True,
            authority_chains_valid=True,
            active_plan_sha256=None,
            binding_plan_sha256=None,
            provider_state_allows=True,
            accepted_result_sha256=request.accepted_result_sha256,
            review_allows=True,
            execution_count=0,
            maximum_execution_count=1,
            used_execution_keys=(),
            order_state_sha256="f" * 64,
            positions_sha256="1" * 64,
            executions_sha256="2" * 64,
            experiment_capital_boundary="500",
            sqlite_write_transaction_active=False,
        )

    class FinalGateEngine:
        def execute(
            self,
            broker,
            candidate,
            authority_context,
            final_write_authority_check=None,
        ):
            events.append("what_if")
            reasons = tuple(final_write_authority_check())
            if reasons:
                return PaperExecutionResult(False, "BLOCKED", reasons, {}, {})
            events.append("write")
            return PaperExecutionResult(True, "SUBMITTED", (), {}, {})

    validator = ProductionAuthorityValidator(snapshot_reader=snapshot_reader)
    coordinator, writer, _ = _start_writer(
        model_execution_engine=FinalGateEngine(),
        attempt_persister=lambda candidate, evidence: events.append("attempt"),
        result_persister=lambda candidate, result, evidence: events.append("result"),
    )
    writer.production_authority_validator = validator
    writer.production_broker_evidence_collector = (
        lambda broker, candidate, raw: (
            events.append("broker") or _production_broker_evidence(candidate)
        )
    )
    writer.now_utc = lambda: datetime(2026, 10, 2, 14, tzinfo=timezone.utc)
    try:
        result = coordinator.submit(request).result(2)
    finally:
        writer.stop(2)

    assert result.success is True
    assert events == [
        "broker",
        "db",
        "what_if",
        "broker",
        "db",
        "attempt",
        "write",
        "result",
    ]
    assert coordinator.expire_before_write(request.execution_key) is False


def test_request_expiring_during_final_broker_read_never_crosses_write_boundary():
    events = []
    request = _model_request(1, ModelExecutionOperation.NEW_TRADE)

    def snapshot_reader(candidate):
        return ProductionAuthoritySnapshot(
            snapshot_id="authority-race",
            observed_at_utc=datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
            lock_owned_by_process=True,
            approved_head=request.approved_head,
            runtime_provenance_valid=True,
            environment="PAPER",
            account_identity_sha256=request.account_identity_sha256,
            owner_authorization_valid=True,
            epoch_id=request.epoch_id,
            clock_active=True,
            kill_switch_clear=True,
            auditor_gate_pass=True,
            market_data_gate_pass=True,
            continuity_schema_valid=True,
            authority_chains_valid=True,
            active_plan_sha256=None,
            binding_plan_sha256=None,
            provider_state_allows=True,
            accepted_result_sha256=request.accepted_result_sha256,
            review_allows=True,
            execution_count=0,
            maximum_execution_count=1,
            used_execution_keys=(),
            order_state_sha256="f" * 64,
            positions_sha256="1" * 64,
            executions_sha256="2" * 64,
            experiment_capital_boundary="500",
            sqlite_write_transaction_active=False,
        )

    class FinalGateEngine:
        def execute(
            self,
            broker,
            candidate,
            authority_context,
            final_write_authority_check=None,
        ):
            events.append("what_if")
            reasons = tuple(final_write_authority_check())
            if reasons:
                return PaperExecutionResult(False, "BLOCKED", reasons, {}, {})
            events.append("write")
            return PaperExecutionResult(True, "SUBMITTED", (), {}, {})

    validator = ProductionAuthorityValidator(snapshot_reader=snapshot_reader)
    coordinator, writer, _ = _start_writer(
        model_execution_engine=FinalGateEngine(),
        attempt_persister=lambda candidate, evidence: events.append("attempt"),
    )
    calls = 0

    def collect(broker, candidate, raw):
        nonlocal calls
        calls += 1
        events.append(f"broker-{calls}")
        if calls == 2:
            assert coordinator.expire_before_write(request.execution_key) is True
        return _production_broker_evidence(candidate)

    writer.production_authority_validator = validator
    writer.production_broker_evidence_collector = collect
    writer.now_utc = lambda: datetime(2026, 10, 2, 14, tzinfo=timezone.utc)
    try:
        result = coordinator.submit(request).result(2)
    finally:
        writer.stop(2)

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("MODEL_EXECUTION_REQUEST_EXPIRED",)
    assert "attempt" not in events
    assert "write" not in events
    assert coordinator.begin_write(request.execution_key) is False


def test_capability_describe_is_connection_free():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ibkr_paper_30d.broker_writer_capability",
            "--describe",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["connections_performed"] == 0
    assert payload["writes_performed"] == 0
    assert any("same-client" in item for item in payload["required_checks"])
