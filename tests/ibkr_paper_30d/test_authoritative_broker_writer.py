from __future__ import annotations

import inspect
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
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
from ibkr_paper_30d.open_order_management import canonical_open_order
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
    )
    writer.start()
    assert writer.wait_until_ready(2)
    return coordinator, writer, factory


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

    def execute(self, broker, request, authority_context):
        self.calls.append((broker, request, authority_context, threading.get_ident()))
        if self.block is not None:
            self.block.wait(2)
        if self.raises:
            raise RuntimeError("model engine failed")
        return PaperExecutionResult(
            True, request.operation.value, (), {"request": request.request_id}, {}
        )


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
