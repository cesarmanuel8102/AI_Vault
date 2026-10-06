from __future__ import annotations

import inspect
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.coordinated_model_executor import (
    CoordinatedModelExecutor,
    ModelExecutionOperation,
    ModelExecutionRequest,
)
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


def _bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-1",
        utc_timestamp=NOW.isoformat(),
        market_session_state="OPEN",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"allocation": "500"},
        broker_account_snapshot={},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="v1",
        execution_realism_version="v1",
        benchmark_state={},
    )


def _proposal() -> AutonomousTradeProposal:
    return AutonomousTradeProposal(
        thesis="A bounded PAPER opportunity.",
        symbol="SPY",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="LMT",
        limit_price="1",
        capital_required="1",
        maximum_loss="1",
        loss_is_bounded=True,
        probability_profit="0.6",
        probability_loss="0.4",
        expected_gain="1",
        expected_loss="1",
        expected_value="0.2",
        expected_holding_period="one day",
        entry_condition="model-authored entry",
        invalidation_condition="model-authored invalidation",
        exit_plan="model-authored exit",
        alternatives_considered=["cash"],
        evidence_used=["PAPER quote"],
        disconfirming_evidence=["spread"],
        confidence="0.6",
    )


def _open_order_action() -> AutonomousOpenOrderAction:
    return AutonomousOpenOrderAction(
        order_ref="order-1",
        order_id=41,
        perm_id=9001,
        client_id=19761,
        contract_id=756733,
        observed_state_sha256="1" * 64,
        reason="Model-authored cancellation.",
    )


def _position_action() -> AutonomousPositionAction:
    return AutonomousPositionAction(
        symbol="SPY",
        sec_type="STK",
        action="SELL",
        quantity="1",
        order_type="LMT",
        limit_price="1",
        contract_id=756733,
        reason="Model-authored reduction.",
    )


def _request_payload(
    operation: ModelExecutionOperation = ModelExecutionOperation.NEW_TRADE,
) -> dict[str, object]:
    payload = {
        ModelExecutionOperation.NEW_TRADE: _proposal(),
        ModelExecutionOperation.OPEN_ORDER_ACTION: _open_order_action(),
        ModelExecutionOperation.POSITION_ACTION: _position_action(),
    }[operation]
    decision = {
        ModelExecutionOperation.NEW_TRADE: TraderDecision.PROPOSE_TRADE,
        ModelExecutionOperation.OPEN_ORDER_ACTION: TraderDecision.CANCEL_ORDER,
        ModelExecutionOperation.POSITION_ACTION: TraderDecision.REDUCE_POSITION,
    }[operation]
    bundle = _bundle()
    return {
        "request_id": "model-request-1",
        "durable_sequence": 1,
        "execution_key": "model-execution-1",
        "source": "MODEL",
        "operation": operation,
        "launch_attempt_id": "launch-1",
        "epoch_id": "AUTONOMY_EPOCH_2",
        "approved_head": "a" * 40,
        "account_identity_sha256": "b" * 64,
        "invocation_id": "invocation-1",
        "decision_cycle_id": bundle.decision_cycle_id,
        "accepted_decision": decision,
        "accepted_result_sha256": "c" * 64,
        "payload": payload,
        "payload_sha256": sha256_json(payload),
        "input_bundle": bundle,
        "input_bundle_sha256": bundle.sha256,
        "created_at_utc": NOW,
    }


@pytest.mark.parametrize("operation", list(ModelExecutionOperation))
def test_model_request_is_deterministic_and_operation_typed(operation) -> None:
    first = ModelExecutionRequest.model_validate(_request_payload(operation))
    second = ModelExecutionRequest.model_validate(_request_payload(operation))

    assert first.sha256 == second.sha256
    assert first.operation == operation
    assert first.source == "MODEL"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(source="WATCHDOG"),
        lambda payload: payload.pop("accepted_result_sha256"),
        lambda payload: payload.update(payload_sha256="0" * 64),
        lambda payload: payload.update(input_bundle_sha256="0" * 64),
        lambda payload: payload.update(operation="cancelOrder"),
        lambda payload: payload.update(broker_method="placeOrder"),
        lambda payload: payload.update(shell_text="Remove-Item -Recurse"),
        lambda payload: payload.update(callback=lambda: None),
    ],
)
def test_model_request_rejects_unbound_or_executable_payloads(mutation) -> None:
    payload = _request_payload()
    mutation(payload)

    with pytest.raises(ValidationError):
        ModelExecutionRequest.model_validate(payload)


class RecordingCoordinator:
    def __init__(self, result: PaperExecutionResult | None = None) -> None:
        self.requests = []
        self.result = result or PaperExecutionResult(
            success=True,
            status="Submitted",
            reason_codes=(),
            order={"orderRef": "order-1"},
            broker_validation={},
        )

    def submit(self, request):
        self.requests.append(request)
        future = Future()
        future.set_result(self.result)
        return future


def _executor(coordinator, *, timeout: float = 1) -> CoordinatedModelExecutor:
    sequence = iter(range(1, 20))
    return CoordinatedModelExecutor(
        coordinator=coordinator,
        launch_attempt_id="launch-1",
        epoch_id="AUTONOMY_EPOCH_2",
        approved_head="a" * 40,
        account_identity_sha256="b" * 64,
        accepted_result_sha256_reader=lambda invocation_id: "c" * 64,
        invocation_id_reader=lambda bundle: "invocation-1",
        durable_sequence_allocator=lambda: next(sequence),
        now_utc=lambda: NOW,
        result_timeout_seconds=timeout,
        production_validation_sha256="d" * 64,
    )


def test_proxy_submits_all_three_operations_without_broker_io() -> None:
    coordinator = RecordingCoordinator()
    executor = _executor(coordinator)

    results = (
        executor.execute(_proposal(), _bundle()),
        executor.execute_open_order_action(
            _open_order_action(), _bundle(), TraderDecision.CANCEL_ORDER
        ),
        executor.execute_position_action(
            _position_action(), _bundle(), TraderDecision.REDUCE_POSITION
        ),
    )

    assert all(result.status == "Submitted" for result in results)
    assert [request.operation for request in coordinator.requests] == list(
        ModelExecutionOperation
    )
    assert "ib_insync" not in inspect.getsource(inspect.getmodule(CoordinatedModelExecutor))
    assert not hasattr(executor, "_connect_execution")


def test_proxy_has_bounded_writer_wait() -> None:
    class NeverCompletes:
        def submit(self, request):
            return Future()

    result = _executor(NeverCompletes(), timeout=0.01).execute(
        _proposal(), _bundle()
    )

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("MODEL_EXECUTION_WRITER_TIMEOUT",)


def test_proxy_is_unarmed_without_production_validation() -> None:
    executor = _executor(RecordingCoordinator())
    unvalidated = executor.model_copy(update={"production_validation_sha256": None}) if hasattr(executor, "model_copy") else CoordinatedModelExecutor(
        coordinator=RecordingCoordinator(),
        launch_attempt_id="launch-1",
        epoch_id="AUTONOMY_EPOCH_2",
        approved_head="a" * 40,
        account_identity_sha256="b" * 64,
        accepted_result_sha256_reader=lambda invocation_id: "c" * 64,
        invocation_id_reader=lambda bundle: "invocation-1",
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW,
        result_timeout_seconds=1,
        production_validation_sha256=None,
    )

    assert executor.armed is True
    assert unvalidated.armed is False


def test_exact_duplicate_reuses_future_but_conflicting_key_blocks() -> None:
    coordinator = BrokerWriteCoordinator()
    request = ModelExecutionRequest.model_validate(_request_payload())

    first = coordinator.submit(request)
    exact_duplicate = coordinator.submit(request)
    conflict = request.model_copy(
        update={"request_id": "different-request", "durable_sequence": 2}
    )
    conflicting = coordinator.submit(conflict)

    assert exact_duplicate is first
    assert conflicting.result().reason_codes == ("DUPLICATE_EXECUTION_KEY",)


def test_blocked_model_wait_does_not_prevent_claiming_next_command() -> None:
    coordinator = BrokerWriteCoordinator()
    capability = coordinator.attach_writer()
    first = ModelExecutionRequest.model_validate(_request_payload())
    second = first.model_copy(
        update={
            "request_id": "model-request-2",
            "durable_sequence": 2,
            "execution_key": "model-execution-2",
        }
    )
    waiting = threading.Event()

    def caller() -> None:
        future = coordinator.submit(first)
        waiting.set()
        future.result(2)

    thread = threading.Thread(target=caller)
    thread.start()
    assert waiting.wait(1)
    coordinator.submit(second)
    claimed_first, future_first = coordinator.claim(capability, timeout=1)
    claimed_second, future_second = coordinator.claim(capability, timeout=1)
    future_first.set_result(PaperExecutionResult(False, "BLOCKED", (), {}, {}))
    future_second.set_result(PaperExecutionResult(False, "BLOCKED", (), {}, {}))
    thread.join(1)

    assert claimed_first.execution_key == "model-execution-1"
    assert claimed_second.execution_key == "model-execution-2"
    assert thread.is_alive() is False


def test_proxy_timeout_marks_request_expired_before_write() -> None:
    class NeverCompletes:
        def __init__(self):
            self.keys = []

        def submit(self, request):
            return Future()

        def expire_before_write(self, execution_key):
            self.keys.append(execution_key)
            return True

    coordinator = NeverCompletes()
    result = _executor(coordinator, timeout=0.01).execute(_proposal(), _bundle())

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("MODEL_EXECUTION_WRITER_TIMEOUT_PRE_WRITE",)
    assert len(coordinator.keys) == 1


def test_proxy_timeout_after_write_boundary_is_uncertain() -> None:
    class WriteAlreadyStarted:
        def submit(self, request):
            return Future()

        def expire_before_write(self, execution_key):
            return False

    result = _executor(WriteAlreadyStarted(), timeout=0.01).execute(
        _proposal(), _bundle()
    )

    assert result.status == "UNCERTAIN"
    assert result.reason_codes == (
        "MODEL_EXECUTION_WRITER_TIMEOUT_AFTER_WRITE_START",
    )


def test_coordinator_expiry_and_write_boundary_are_atomic() -> None:
    before = BrokerWriteCoordinator()
    assert before.expire_before_write("execution-1") is True
    assert before.begin_write("execution-1") is False
    assert before.is_execution_expired("execution-1") is True

    after = BrokerWriteCoordinator()
    assert after.begin_write("execution-2") is True
    assert after.expire_before_write("execution-2") is False
    assert after.is_execution_expired("execution-2") is False
