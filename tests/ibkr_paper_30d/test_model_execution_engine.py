from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from ibkr_paper_30d.coordinated_model_executor import (
    ModelExecutionOperation,
    ModelExecutionRequest,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.model_execution_engine import (
    ModelExecutionAuthorityContext,
    ModelExecutionEngine,
)
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle
from ibkr_paper_30d.multi_universe_models import CapitalSleeve


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


def _request(operation: ModelExecutionOperation) -> ModelExecutionRequest:
    payload = {
        ModelExecutionOperation.NEW_TRADE: AutonomousTradeProposal(
            thesis="test",
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
            entry_condition="entry",
            invalidation_condition="invalidation",
            exit_plan="exit",
            alternatives_considered=["cash"],
            evidence_used=["PAPER quote"],
            disconfirming_evidence=["spread"],
            confidence="0.6",
        ),
        ModelExecutionOperation.OPEN_ORDER_ACTION: AutonomousOpenOrderAction(
            order_ref="order-1",
            order_id=41,
            perm_id=9001,
            client_id=19761,
            contract_id=756733,
            observed_state_sha256="1" * 64,
            reason="cancel",
        ),
        ModelExecutionOperation.POSITION_ACTION: AutonomousPositionAction(
            symbol="SPY",
            sec_type="STK",
            action="SELL",
            quantity="1",
            order_type="LMT",
            limit_price="1",
            contract_id=756733,
            reason="reduce",
        ),
    }[operation]
    decision = {
        ModelExecutionOperation.NEW_TRADE: TraderDecision.PROPOSE_TRADE,
        ModelExecutionOperation.OPEN_ORDER_ACTION: TraderDecision.CANCEL_ORDER,
        ModelExecutionOperation.POSITION_ACTION: TraderDecision.REDUCE_POSITION,
    }[operation]
    bundle = TraderInputBundle(
        decision_cycle_id="cycle-1",
        utc_timestamp=NOW.isoformat(),
        market_session_state="OPEN",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={},
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
    return ModelExecutionRequest(
        request_id=f"request-{operation.value}",
        durable_sequence=list(ModelExecutionOperation).index(operation) + 1,
        execution_key=f"execution-{operation.value}",
        source="MODEL",
        operation=operation,
        launch_attempt_id="launch-1",
        epoch_id="AUTONOMY_EPOCH_2",
        approved_head="a" * 40,
        account_identity_sha256="b" * 64,
        invocation_id="invocation-1",
        decision_cycle_id="cycle-1",
        accepted_decision=decision,
        accepted_result_sha256="c" * 64,
        payload=payload,
        payload_sha256=sha256_json(payload),
        input_bundle=bundle,
        input_bundle_sha256=bundle.sha256,
        continuity_plan=None,
        continuity_plan_sha256=None,
        created_at_utc=NOW,
    )


def test_v4_model_execution_request_binds_sleeve_and_product_family() -> None:
    legacy = _request(ModelExecutionOperation.NEW_TRADE)
    family_sha256 = "f" * 64
    bundle = legacy.input_bundle.model_copy(
        update={
            "multi_sleeve_portfolio": {
                "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
                "sleeves": {
                    "REGULAR_SLEEVE": {"equity": "500"},
                    "EXTENDED_SLEEVE": {"equity": "500"},
                },
            },
            "contract_ownership_snapshot": {"contract_sleeves": {}},
            "product_capability_snapshot": {"families": []},
        }
    )
    payload = legacy.payload.model_copy(
        update={
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "product_family_sha256": family_sha256,
        }
    )
    data = legacy.model_dump()
    data.update(
        {
            "payload": payload,
            "payload_sha256": sha256_json(payload),
            "input_bundle": bundle,
            "input_bundle_sha256": bundle.sha256,
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "sleeve_authority_sha256": sha256_json(
                bundle.multi_sleeve_portfolio
            ),
            "ownership_projection_sha256": sha256_json(
                bundle.contract_ownership_snapshot
            ),
            "product_family_sha256": family_sha256,
        }
    )

    assert (
        ModelExecutionRequest.model_validate(data).capital_sleeve
        is CapitalSleeve.EXTENDED_SLEEVE
    )
    with pytest.raises(ValueError, match="capital sleeve binding mismatch"):
        ModelExecutionRequest.model_validate(
            {**data, "capital_sleeve": CapitalSleeve.REGULAR_SLEEVE}
        )
    with pytest.raises(ValueError, match="V4 execution bindings are required"):
        ModelExecutionRequest.model_validate(
            {
                **data,
                "payload": payload.model_copy(
                    update={"capital_sleeve": None, "product_family_sha256": None}
                ),
                "payload_sha256": sha256_json(
                    payload.model_copy(
                        update={"capital_sleeve": None, "product_family_sha256": None}
                    )
                ),
                "capital_sleeve": None,
                "product_family_sha256": None,
            }
        )


class BrokerTripwire:
    def __init__(self) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0

    def connect(self, *args, **kwargs):
        self.connect_calls += 1
        raise AssertionError("engine attempted broker connect")

    def disconnect(self):
        self.disconnect_calls += 1
        raise AssertionError("engine attempted broker disconnect")


class RecordingMechanics:
    def __init__(self) -> None:
        self.calls = []

    @staticmethod
    def _result(name: str) -> PaperExecutionResult:
        return PaperExecutionResult(True, name, (), {"path": name}, {})

    def execute_with_broker(self, broker, proposal, bundle, **kwargs):
        self.calls.append(("new", broker, proposal, bundle, kwargs))
        return self._result("NEW_TRADE")

    def execute_open_order_action_with_broker(
        self, broker, action, bundle, decision, **kwargs
    ):
        self.calls.append(("open", broker, action, bundle, decision, kwargs))
        return self._result("OPEN_ORDER_ACTION")

    def execute_position_action_with_broker(
        self, broker, action, bundle, decision, **kwargs
    ):
        self.calls.append(("position", broker, action, bundle, decision, kwargs))
        return self._result("POSITION_ACTION")


def _context(request: ModelExecutionRequest, **updates) -> ModelExecutionAuthorityContext:
    values = {
        "request_sha256": request.sha256,
        "writer_thread_id": threading.get_ident(),
        "execution_client_id": 19761,
        "production_validation_sha256": "f" * 64,
    }
    values.update(updates)
    return ModelExecutionAuthorityContext.model_validate(values)


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (ModelExecutionOperation.NEW_TRADE, "NEW_TRADE"),
        (ModelExecutionOperation.OPEN_ORDER_ACTION, "OPEN_ORDER_ACTION"),
        (ModelExecutionOperation.POSITION_ACTION, "POSITION_ACTION"),
    ],
)
def test_engine_dispatches_all_operations_with_exact_injected_broker(
    operation, expected
) -> None:
    mechanics = RecordingMechanics()
    engine = ModelExecutionEngine(mechanics=mechanics)
    broker = BrokerTripwire()
    request = _request(operation)

    result = engine.execute(broker, request, _context(request))

    assert result.status == expected
    assert mechanics.calls[0][1] is broker
    assert broker.connect_calls == 0
    assert broker.disconnect_calls == 0


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"request_sha256": "0" * 64}, "MODEL_REQUEST_AUTHORITY_MISMATCH"),
        ({"writer_thread_id": -1}, "MODEL_WRITER_THREAD_MISMATCH"),
        ({"execution_client_id": 19762}, "MODEL_EXECUTION_CLIENT_MISMATCH"),
    ],
)
def test_engine_blocks_wrong_authority_context_without_dispatch(updates, reason) -> None:
    mechanics = RecordingMechanics()
    engine = ModelExecutionEngine(mechanics=mechanics, execution_client_id=19761)
    request = _request(ModelExecutionOperation.NEW_TRADE)

    result = engine.execute(BrokerTripwire(), request, _context(request, **updates))

    assert result.status == "BLOCKED"
    assert result.reason_codes == (reason,)
    assert mechanics.calls == []


def test_engine_rejects_non_typed_request() -> None:
    engine = ModelExecutionEngine(mechanics=RecordingMechanics())

    with pytest.raises(TypeError, match="MODEL_EXECUTION_REQUEST_REQUIRED"):
        engine.execute(BrokerTripwire(), object(), object())
