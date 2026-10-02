from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_execution import (
    AutonomousPaperExecutionNotArmed,
    AutonomousPaperExecutor,
)
from ibkr_paper_30d.autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
    ProposalValidation,
)
from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_binding import ContinuityBindingError
from ibkr_paper_30d.continuity_models import TimeInForce
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.open_order_management import (
    EXECUTION_CLIENT_ID,
    _contract_identity_matches,
    canonical_open_order,
)
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle


class NoCallToolbox:
    def validate_proposal(self, proposal, bundle):
        raise AssertionError("toolbox should not be called when deterministic safety gate blocks")


def bundle(*, reconciliation="PASS", kill_switch="KILL_SWITCH_CLEAR", market_gate="PASS"):
    return TraderInputBundle(
        decision_cycle_id="cycle-exec-1",
        utc_timestamp="2026-09-20T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": reconciliation},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"buying_power": "500.00"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state=kill_switch,
        market_data_snapshot={"gate_status": market_gate},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )


def proposal():
    return AutonomousTradeProposal(
        thesis="test",
        catalyst="test",
        symbol="SPY",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="MKT",
        limit_price=None,
        expiry=None,
        strike=None,
        right=None,
        legs=[],
        capital_required="100",
        maximum_loss="100",
        loss_is_bounded=True,
        probability_profit="0.6",
        probability_loss="0.4",
        expected_gain="20",
        expected_loss="10",
        expected_value="8",
        expected_reward_risk="2",
        expected_holding_period="intraday",
        entry_condition="now",
        invalidation_condition="invalid",
        exit_plan="exit",
        why_now="test",
        alternatives_considered=["cash"],
        evidence_used=["quote"],
        disconfirming_evidence=[],
        confidence="0.6",
    )


def bag_proposal():
    return proposal().model_copy(
        update={
            "symbol": "IOVA",
            "sec_type": "BAG",
            "order_type": "LMT",
            "limit_price": Decimal("0.90"),
            "capital_required": Decimal("93.80"),
            "maximum_loss": Decimal("93.80"),
            "legs": [
                {
                    "symbol": "IOVA",
                    "sec_type": "OPT",
                    "expiry": "20261016",
                    "strike": Decimal("15"),
                    "right": "C",
                    "action": "BUY",
                    "ratio": 1,
                    "exchange": "SMART",
                    "currency": "USD",
                },
                {
                    "symbol": "IOVA",
                    "sec_type": "OPT",
                    "expiry": "20261016",
                    "strike": Decimal("18"),
                    "right": "C",
                    "action": "SELL",
                    "ratio": 1,
                    "exchange": "SMART",
                    "currency": "USD",
                },
            ],
        }
    )


def lifecycle_trade(*, total=2, filled=0, limit_price=10):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=EXECUTION_CLIENT_ID,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=total,
            lmtPrice=limit_price,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
            parentId=0,
            ocaGroup="",
            transmit=False,
            conditions=[],
            goodAfterTime="",
            goodTillDate="",
            smartComboRoutingParams=[],
            algoStrategy="",
            algoParams=[],
            orderMiscOptions=[],
        ),
        orderStatus=SimpleNamespace(
            status="Submitted",
            filled=filled,
            remaining=Decimal(str(total)) - Decimal(str(filled)),
            avgFillPrice=0,
        ),
        fills=[],
    )


def bag_lifecycle_trade(*, total=2, filled=0, limit_price="0.90"):
    value = lifecycle_trade(total=total, filled=filled, limit_price=limit_price)
    value.contract = SimpleNamespace(
        conId=28812380,
        symbol="IOVA",
        localSymbol="IOVA",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="",
        comboLegs=[
            SimpleNamespace(conId=913925915, ratio=1, action="BUY", exchange="SMART"),
            SimpleNamespace(conId=926221865, ratio=1, action="SELL", exchange="SMART"),
        ],
    )
    value.order.orderRef = "codex-ibkr-paper-30d-a-f8da732bc64a"
    value.order.orderId = 13
    value.order.permId = 1401602203
    return value


def open_order_action_from_trade(value):
    snapshot = canonical_open_order(value)
    return AutonomousOpenOrderAction(
        order_ref=snapshot["orderRef"],
        order_id=snapshot["orderId"],
        perm_id=snapshot["permId"],
        client_id=snapshot["clientId"],
        contract_id=snapshot["contract"]["conId"],
        observed_state_sha256=snapshot["state_sha256"],
        reason="Cancel the selected resting experiment order.",
    )


def register_issuance(db, value):
    snapshot = canonical_open_order(value)
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
        "lifecycle_event": "ISSUED_PRE_SEND",
        "order_ref": snapshot["orderRef"],
        "client_order_id": snapshot["orderId"],
        "perm_id": snapshot["permId"],
        "ibkr_order_id": snapshot["orderId"],
        "contract_id": snapshot["contract"]["conId"],
        "action": snapshot["action"],
        "quantity": snapshot["totalQuantity"],
        "execution_client_id": snapshot["clientId"],
        "account": snapshot["account"],
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-test-anchor",
            snapshot["orderRef"],
            snapshot["orderId"],
            snapshot["permId"],
            snapshot["orderId"],
            snapshot["contract"]["conId"],
            snapshot["action"],
            snapshot["totalQuantity"],
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-23T12:00:00Z",
        ),
    )


def register_legacy_bag_anchors(db, value):
    snapshot = canonical_open_order(value)
    for registry_id, lifecycle_event, perm_id in (
        ("legacy-bag-pre-send", "ISSUED_PRE_SEND", 0),
        ("legacy-bag-broker-bound", "BROKER_BOUND", snapshot["permId"]),
    ):
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
            "lifecycle_event": lifecycle_event,
            "order_ref": snapshot["orderRef"],
            "client_order_id": snapshot["orderId"],
            "perm_id": perm_id,
            "ibkr_order_id": snapshot["orderId"],
            "contract_id": 0,
            "action": snapshot["action"],
            "quantity": snapshot["totalQuantity"],
            "execution_client_id": snapshot["clientId"],
            "account": snapshot["account"],
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                registry_id,
                snapshot["orderRef"],
                snapshot["orderId"],
                perm_id,
                snapshot["orderId"],
                0,
                snapshot["action"],
                snapshot["totalQuantity"],
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                "2026-09-29T17:55:57Z",
            ),
        )


class FakeLifecycleIB:
    def __init__(
        self,
        target,
        *,
        disconnect_after_cancel=False,
        reject_cancel=False,
        confirmation_timeout=False,
        fill_during_cancel=False,
        corrupt_confirmation=False,
        disconnect_raises=False,
    ):
        self.target = target
        self.disconnect_after_cancel = disconnect_after_cancel
        self.reject_cancel = reject_cancel
        self.confirmation_timeout = confirmation_timeout
        self.fill_during_cancel = fill_during_cancel
        self.corrupt_confirmation = corrupt_confirmation
        self.disconnect_raises = disconnect_raises
        self.cancel_calls = 0
        self.cancelled_order_ids = []
        self.global_cancel_calls = 0
        self.place_calls = []
        self.client = SimpleNamespace(getReqId=lambda: 4242)

    def reqOpenOrders(self):
        return self.openTrades()

    def openTrades(self):
        return (
            []
            if self.target.orderStatus.status in {"Cancelled", "Filled"}
            else [self.target]
        )

    def cancelOrder(self, order):
        self.cancel_calls += 1
        self.cancelled_order_ids.append(order.orderId)
        if self.reject_cancel:
            raise RuntimeError("cancel rejected")
        if self.fill_during_cancel:
            self.target.orderStatus.status = "Filled"
            self.target.orderStatus.filled = self.target.order.totalQuantity
            self.target.orderStatus.remaining = 0
        elif not self.confirmation_timeout:
            self.target.orderStatus.status = "Cancelled"
        if self.corrupt_confirmation:
            self.target.order.totalQuantity = "not-a-number"
        if self.disconnect_after_cancel:
            raise ConnectionError("disconnected after cancel")
        return self.target

    def sleep(self, seconds):
        return True

    def disconnect(self):
        if self.disconnect_raises:
            raise RuntimeError("disconnect cleanup failed")
        return None


class LifecycleToolbox:
    def __init__(self, broker, *, fail_connects=0):
        self.broker = broker
        self.fail_connects = fail_connects
        self.connect_calls = 0

    def _connect(self, *, client_id=None):
        assert client_id == EXECUTION_CLIENT_ID
        self.connect_calls += 1
        if self.connect_calls <= self.fail_connects:
            raise ConnectionError("initial connection failed")
        return self.broker


class ModificationValidationIB(FakeLifecycleIB):
    def __init__(self, target, *, what_if_state=None):
        super().__init__(target)
        self.quote_contract_ids = []
        self.what_if_calls = 0
        self.what_if_state = what_if_state
        self.last_what_if_order = None

    def reqAllOpenOrders(self):
        return self.openTrades()

    def whatIfOrder(self, contract, order):
        self.what_if_calls += 1
        self.last_what_if_order = order
        if self.what_if_state is not None:
            return self.what_if_state
        return SimpleNamespace(
            commission="1.00",
            minCommission="1.00",
            maxCommission="1.00",
            initMarginChange="100.00",
            maintMarginChange="100.00",
            warningText="",
        )


class FakeModifyIB(FakeLifecycleIB):
    def __init__(
        self,
        target,
        *,
        change_state_after_what_if=False,
        disconnect_after_place=False,
        mutate_preserved_field_after_place=None,
        corrupt_confirmation=False,
        disconnect_raises=False,
    ):
        super().__init__(
            target,
            corrupt_confirmation=corrupt_confirmation,
            disconnect_raises=disconnect_raises,
        )
        self.change_state_after_what_if = change_state_after_what_if
        self.disconnect_after_place = disconnect_after_place
        self.mutate_preserved_field_after_place = mutate_preserved_field_after_place
        self.what_if_calls = 0

    def reqAllOpenOrders(self):
        return self.openTrades()

    def whatIfOrder(self, contract, order):
        self.what_if_calls += 1
        if self.change_state_after_what_if:
            self.target.order.lmtPrice = 10.25
        return SimpleNamespace(
            commission="1.00",
            minCommission="1.00",
            maxCommission="1.00",
            initMarginChange="100.00",
            maintMarginChange="100.00",
            warningText="",
        )

    def placeOrder(self, contract, order):
        self.place_calls.append((contract, order))
        self.target.order = order
        if self.mutate_preserved_field_after_place is not None:
            field, value = self.mutate_preserved_field_after_place
            setattr(self.target.order, field, value)
        self.target.orderStatus.status = "Submitted"
        self.target.orderStatus.remaining = Decimal(str(order.totalQuantity)) - Decimal(
            str(self.target.orderStatus.filled)
        )
        if self.corrupt_confirmation:
            self.target.order.totalQuantity = "not-a-number"
        if self.disconnect_after_place:
            raise ConnectionError("disconnected after modify")
        return self.target


def modification_validation_fixture(
    *,
    total="2",
    filled="0",
    new_total="1",
    quote_success=True,
    what_if_state=None,
    order_type="LMT",
    status="Submitted",
):
    target = lifecycle_trade(total=total, filled=filled)
    target.order.orderType = order_type
    target.orderStatus.status = status
    snapshot = canonical_open_order(target)
    action = open_order_action_from_trade(target).model_copy(
        update={
            "new_total_quantity": Decimal(new_total),
            "new_limit_price": Decimal("9.50"),
            "reason": "Reduce and reprice the resting order.",
        }
    )
    value = bundle().model_copy(update={"open_orders_snapshot": [snapshot]})
    fake_ib = ModificationValidationIB(target, what_if_state=what_if_state)
    toolbox = IBKRResearchToolbox()
    toolbox.live_contract_quote_evidence = lambda ib, contract: (
        fake_ib.quote_contract_ids.append(contract.conId)
        or {
            "success": quote_success,
            "bid": 9.45,
            "ask": 9.50,
            "market_data_type": 1,
        }
    )
    return toolbox, fake_ib, value, action


@contextmanager
def armed_modify_fixture(
    tmp_path,
    *,
    change_state_after_what_if=False,
    disconnect_after_place=False,
    mutate_preserved_field_after_place=None,
    corrupt_confirmation=False,
    disconnect_raises=False,
):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "modify.sqlite3") as db:
        target = lifecycle_trade()
        action = open_order_action_from_trade(target).model_copy(
            update={
                "new_total_quantity": Decimal("1"),
                "new_limit_price": Decimal("9.50"),
                "reason": "Reduce and reprice the resting order.",
            }
        )
        register_issuance(db, target)
        broker = FakeModifyIB(
            target,
            change_state_after_what_if=change_state_after_what_if,
            disconnect_after_place=disconnect_after_place,
            mutate_preserved_field_after_place=mutate_preserved_field_after_place,
            corrupt_confirmation=corrupt_confirmation,
            disconnect_raises=disconnect_raises,
        )
        toolbox = IBKRResearchToolbox()
        toolbox._connect = lambda *, client_id=None: broker
        toolbox.live_contract_quote_evidence = lambda ib, contract: {
            "success": True,
            "bid": 9.45,
            "ask": 9.50,
            "market_data_type": 1,
        }
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )
        yield executor, db, broker, action, value


@contextmanager
def armed_cancel_fixture(
    tmp_path,
    *,
    disconnect_after_cancel=False,
    reject_cancel=False,
    confirmation_timeout=False,
    fill_during_cancel=False,
    corrupt_confirmation=False,
    disconnect_raises=False,
    fail_connects=0,
    fresh_safety_check=lambda scope: (),
    operator_control_check=lambda: (),
):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "cancel.sqlite3") as db:
        target = lifecycle_trade()
        action = open_order_action_from_trade(target)
        register_issuance(db, target)
        broker = FakeLifecycleIB(
            target,
            disconnect_after_cancel=disconnect_after_cancel,
            reject_cancel=reject_cancel,
            confirmation_timeout=confirmation_timeout,
            fill_during_cancel=fill_during_cancel,
            corrupt_confirmation=corrupt_confirmation,
            disconnect_raises=disconnect_raises,
        )
        toolbox = LifecycleToolbox(broker, fail_connects=fail_connects)
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=fresh_safety_check,
            operator_control_check=operator_control_check,
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )
        yield executor, db, broker, action, value


def lifecycle_events(db, order_ref):
    rows = db.execute(
        "SELECT payload_json FROM experiment_order_registry "
        "WHERE order_ref=? ORDER BY sequence",
        (order_ref,),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def test_executor_is_not_armed_by_default(monkeypatch):
    monkeypatch.delenv("IBKR_AUTONOMOUS_PAPER_ARMED", raising=False)
    executor = AutonomousPaperExecutor(NoCallToolbox())

    with pytest.raises(AutonomousPaperExecutionNotArmed):
        executor.execute(proposal(), bundle())


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"reconciliation": "BLOCK"}, "BROKER_RECONCILIATION_REQUIRED"),
        ({"kill_switch": "KILL_SWITCH_TRIGGERED"}, "KILL_SWITCH_TRIGGERED"),
        ({"market_gate": "BLOCK"}, "MARKET_DATA_GATE_BLOCK"),
    ],
)
def test_executor_retains_non_strategic_safety_gates(kwargs, reason):
    executor = AutonomousPaperExecutor(NoCallToolbox(), armed=True)

    result = executor.execute(proposal(), bundle(**kwargs))

    assert result.success is False
    assert result.status == "BLOCKED"
    assert reason in result.reason_codes


class _FakeIB:
    def __init__(self):
        self.place_calls = 0
        self.client = SimpleNamespace(getReqId=lambda: 4242)

    def managedAccounts(self):
        return ["DU1234567"]

    def placeOrder(self, contract, order):
        self.place_calls += 1
        raise AssertionError("placeOrder must not be reached")

    def disconnect(self):
        pass


class _PassUntilOperatorControlToolbox:
    def __init__(self):
        self.ib = _FakeIB()
        self.requested_client_ids = []
        self.validation_connections = []

    def _connect(self, *, client_id=None):
        self.requested_client_ids.append(client_id)
        return self.ib

    def _proposal_contract(self, ib, proposal):
        return SimpleNamespace(conId=123, symbol=proposal.symbol)

    def live_contract_quote_evidence(
        self, ib, contract, *, wait_seconds=2.0, max_age_seconds=15.0
    ):
        return {"success": True, "market_data_type": 1}

    def validate_proposal(self, proposal, bundle, *, ib=None):
        self.validation_connections.append(ib)
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={"what_if": {"success": True}},
        )


class _RejectingContinuityBindingService:
    def __init__(self):
        self.stage_calls = 0

    def stage_new_order(self, *args, **kwargs):
        self.stage_calls += 1
        raise ContinuityBindingError("TEST_PERSISTENCE_FAILURE")


class _ResolvedBagIB:
    def __init__(self, resolved_contract):
        self.resolved_contract = resolved_contract
        self.client = SimpleNamespace(getReqId=lambda: 13)

    def managedAccounts(self):
        return ["DU1234567"]

    def placeOrder(self, contract, order):
        order.permId = 1401602203
        order.clientId = EXECUTION_CLIENT_ID
        return SimpleNamespace(
            contract=self.resolved_contract,
            order=order,
            orderStatus=SimpleNamespace(
                status="PreSubmitted", filled=0, remaining=1, avgFillPrice=0
            ),
            fills=[],
        )

    def sleep(self, seconds):
        return True

    def disconnect(self):
        return None


class _DelayedResolvedBagIB(_ResolvedBagIB):
    def __init__(
        self,
        pre_send_contract,
        resolved_contract,
        *,
        server_order_updates=None,
        unrelated_leg=False,
    ):
        super().__init__(resolved_contract)
        self.pre_send_contract = pre_send_contract
        self.server_order_updates = server_order_updates or {}
        self.unrelated_leg = unrelated_leg
        self.server_trade = None
        self.readback_calls = 0

    def placeOrder(self, contract, order):
        local_order = SimpleNamespace(**order.__dict__)
        local_order.permId = 1401602217
        local_order.clientId = EXECUTION_CLIENT_ID
        server_order = SimpleNamespace(**order.__dict__)
        server_order.permId = 1401602217
        server_order.clientId = EXECUTION_CLIENT_ID
        for field, value in self.server_order_updates.items():
            setattr(server_order, field, value)
        server_contract = deepcopy(self.resolved_contract)
        if self.unrelated_leg:
            server_contract.comboLegs[1].conId = 999999999
        self.server_trade = SimpleNamespace(
            contract=server_contract,
            order=server_order,
            orderStatus=SimpleNamespace(
                status="PendingSubmit", filled=0, remaining=1, avgFillPrice=0
            ),
            fills=[],
        )
        return SimpleNamespace(
            contract=self.pre_send_contract,
            order=local_order,
            orderStatus=SimpleNamespace(
                status="Cancelled", filled=0, remaining=1, avgFillPrice=0
            ),
            fills=[],
        )

    def reqAllOpenOrders(self):
        self.readback_calls += 1
        return [self.server_trade]


class _ResolvedBagToolbox:
    def __init__(self):
        self.pre_send_contract = SimpleNamespace(
            conId=0,
            symbol="IOVA",
            localSymbol="",
            secType="BAG",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="",
            comboLegs=[
                SimpleNamespace(
                    conId=913925915, ratio=1, action="BUY", exchange="SMART"
                ),
                SimpleNamespace(
                    conId=926221865, ratio=1, action="SELL", exchange="SMART"
                ),
            ],
        )
        self.resolved_contract = SimpleNamespace(
            **{
                **self.pre_send_contract.__dict__,
                "conId": 28812380,
                "localSymbol": "IOVA",
            }
        )
        self.ib = _ResolvedBagIB(self.resolved_contract)

    def _connect(self, *, client_id=None):
        assert client_id in {None, EXECUTION_CLIENT_ID}
        return self.ib

    def _proposal_contract(self, ib, proposal):
        return self.pre_send_contract

    def live_contract_quote_evidence(self, ib, contract):
        return {"success": True, "market_data_type": 1}

    def validate_proposal(self, proposal, bundle, *, ib=None):
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={"what_if": {"success": True}},
        )


def test_bag_broker_bound_uses_resolved_trade_contract_and_persists_legs(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _ResolvedBagToolbox()
    with Database.open(tmp_path / "resolved-bag.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )

        result = executor.execute(bag_proposal(), bundle())
        rows = db.execute(
            "SELECT contract_id,payload_json FROM experiment_order_registry "
            "ORDER BY sequence"
        ).fetchall()

    assert result.success is True
    assert [row[0] for row in rows] == [0, 28812380]
    payloads = [json.loads(row[1]) for row in rows]
    assert payloads[0]["contract"]["comboLegs"] == [
        {"conId": 913925915, "ratio": 1, "action": "BUY", "exchange": "SMART"},
        {"conId": 926221865, "ratio": 1, "action": "SELL", "exchange": "SMART"},
    ]
    assert payloads[1]["lifecycle_event"] == "BROKER_BOUND"
    assert payloads[1]["contract"]["conId"] == 28812380


def test_bag_post_send_reconciles_delayed_broker_identity_before_result(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _ResolvedBagToolbox()
    toolbox.ib = _DelayedResolvedBagIB(
        toolbox.pre_send_contract, toolbox.resolved_contract
    )
    with Database.open(tmp_path / "delayed-resolved-bag.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )

        result = executor.execute(bag_proposal(), bundle())
        rows = db.execute(
            "SELECT contract_id,perm_id,payload_json "
            "FROM experiment_order_registry ORDER BY sequence"
        ).fetchall()

    assert result.success is True
    assert result.status == "PendingSubmit"
    assert toolbox.ib.readback_calls >= 1
    assert [(row[0], row[1]) for row in rows] == [
        (0, 0),
        (28812380, 1401602217),
    ]
    broker_bound = json.loads(rows[1][2])
    assert broker_bound["lifecycle_event"] == "BROKER_BOUND"
    assert broker_bound["contract"]["comboLegs"] == [
        {"conId": 913925915, "ratio": 1, "action": "BUY", "exchange": "SMART"},
        {"conId": 926221865, "ratio": 1, "action": "SELL", "exchange": "SMART"},
    ]


@pytest.mark.parametrize(
    "server_order_updates,unrelated_leg",
    [
        ({"orderRef": "codex-ibkr-paper-30d-a-other"}, False),
        ({"orderId": 99}, False),
        ({"clientId": 7}, False),
        ({"account": "DU7654321"}, False),
        ({"action": "SELL"}, False),
        ({"totalQuantity": 2}, False),
        ({}, True),
    ],
)
def test_post_send_readback_cannot_borrow_unrelated_bag_identity(
    tmp_path, server_order_updates, unrelated_leg
):
    from ibkr_paper_30d.persistence import Database

    toolbox = _ResolvedBagToolbox()
    toolbox.ib = _DelayedResolvedBagIB(
        toolbox.pre_send_contract,
        toolbox.resolved_contract,
        server_order_updates=server_order_updates,
        unrelated_leg=unrelated_leg,
    )
    with Database.open(tmp_path / "unrelated-readback.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )

        result = executor.execute(bag_proposal(), bundle())
        rows = db.execute(
            "SELECT contract_id,perm_id FROM experiment_order_registry "
            "ORDER BY sequence"
        ).fetchall()

    assert result.success is False
    assert result.status == "Cancelled"
    assert [(row[0], row[1]) for row in rows] == [(0, 0)]


def test_immediate_operator_control_blocks_place_order(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: ("OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE",),
        )
        result = executor.execute(proposal(), bundle())

    assert result.success is False
    assert result.status == "BLOCKED"
    assert "OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE" in result.reason_codes
    assert toolbox.ib.place_calls == 0
    assert toolbox.requested_client_ids == [19761]


def test_continuity_stage_failure_blocks_place_order(
    tmp_path, continuity_plan_factory
):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    binding_service = _RejectingContinuityBindingService()
    value = bundle().model_copy(
        update={"continuity_context": {"authority_contract_required": True}}
    )
    with Database.open(tmp_path / "continuity-stage.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
            continuity_binding_service=binding_service,
        )
        plan = continuity_plan_factory(
            invocation_id="inv-continuity-stage",
            order_binding={
                "binding_type": "NEW_PROPOSAL",
                "order_ref": "codex-ibkr-paper-30d-a-model-plan",
                "ibkr_order_id": None,
                "perm_id": None,
                "original_order_state_sha256": None,
                "proposal_sha256": sha256_json(proposal()),
                "original_intent_sha256": sha256_json(proposal()),
            },
        )
        result = executor.execute(
            proposal(),
            value,
            continuity_plan=plan,
            invocation_id=plan.invocation_id,
        )

    assert result.status == "BLOCKED"
    assert result.reason_codes == (
        "CONTINUITY_BINDING_FAILED:TEST_PERSISTENCE_FAILURE",
    )
    assert binding_service.stage_calls == 1
    assert toolbox.ib.place_calls == 0


def test_required_continuity_without_plan_fails_before_broker_connect(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    value = bundle().model_copy(
        update={"continuity_context": {"authority_contract_required": True}}
    )
    with Database.open(tmp_path / "continuity-required.sqlite3") as db:
        result = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        ).execute(proposal(), value)

    assert result.reason_codes == ("CONTINUITY_PLAN_REQUIRED",)
    assert toolbox.requested_client_ids == []
    assert toolbox.ib.place_calls == 0


def test_wrapped_executor_reuses_connection_for_proposal_validation(tmp_path):
    from ibkr_paper_30d.persistence import Database

    base = _PassUntilOperatorControlToolbox()
    toolbox = AutonomyToolbox(base, None)
    with Database.open(tmp_path / "wrapped-execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: ("TEST_BLOCK_BEFORE_WRITE",),
        )
        result = executor.execute(proposal(), bundle())

    assert result.reason_codes == ("TEST_BLOCK_BEFORE_WRITE",)
    assert base.requested_client_ids == [19761]
    assert base.validation_connections == [base.ib]
    assert base.ib.place_calls == 0


def test_position_management_uses_stable_execution_client(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    action = AutonomousPositionAction(
        symbol="SPY",
        sec_type="STK",
        action="SELL",
        quantity="1",
        order_type="MKT",
        reason="Reduce exposure.",
    )
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: ("TEST_BLOCK_BEFORE_WRITE",),
            operator_control_check=lambda: (),
        )

        result = executor.execute_position_action(
            action, bundle(), TraderDecision.REDUCE_POSITION
        )

    assert result.reason_codes == ("TEST_BLOCK_BEFORE_WRITE",)
    assert toolbox.requested_client_ids == [19761]
    assert toolbox.ib.place_calls == 0


def test_missing_immediate_operator_control_callback_fails_closed(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
        )
        result = executor.execute(proposal(), bundle())

    assert result.success is False
    assert "FRESH_OPERATOR_CONTROL_CHECK_REQUIRED" in result.reason_codes
    assert toolbox.ib.place_calls == 0


def test_operator_revocation_after_registry_blocks_final_send(tmp_path):
    from ibkr_paper_30d.persistence import Database

    toolbox = _PassUntilOperatorControlToolbox()
    checks = iter(((), ("OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE",)))
    with Database.open(tmp_path / "execution.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: next(checks),
        )
        result = executor.execute(proposal(), bundle())
        registry_count = db.execute(
            "SELECT COUNT(*) FROM experiment_order_registry"
        ).fetchone()[0]

    assert result.success is False
    assert result.status == "BLOCKED"
    assert "OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE" in result.reason_codes
    assert registry_count == 1
    assert toolbox.ib.place_calls == 0


def test_immediate_fill_payload_inherits_issued_order_identity():
    trade = SimpleNamespace(
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-issued",
            orderId=77,
            permId=88,
            clientId=99,
            account="DU1234567",
        ),
        fills=[
            SimpleNamespace(
                execution=SimpleNamespace(
                    execId="",
                    orderRef="",
                    permId=0,
                    orderId=0,
                    clientId=0,
                    side="BOT",
                    shares=1,
                    price=10.0,
                    time="2026-09-21T13:30:00Z",
                    cumQty=1,
                    avgPrice=10.0,
                ),
                contract=SimpleNamespace(
                    conId=123,
                    symbol="XYZ",
                    localSymbol="XYZ",
                    secType="STK",
                    exchange="SMART",
                    currency="USD",
                    lastTradeDateOrContractMonth="",
                    strike=0,
                    right="",
                    multiplier="1",
                ),
                commissionReport=None,
            )
        ],
    )

    payload = AutonomousPaperExecutor._fills_payload(
        trade,
        fallback_order_ref="codex-ibkr-paper-30d-a-issued",
    )
    assert len(payload) == 1
    fill = payload[0]
    assert fill["orderRef"] == "codex-ibkr-paper-30d-a-issued"
    assert fill["orderId"] == 77
    assert fill["permId"] == 88
    assert fill["clientId"] == 99
    assert fill["account"] == "DU1234567"
    assert fill["execution_id_hash"] is None


def test_order_registry_appends_broker_perm_id_without_rewriting_pre_send_identity(tmp_path):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "registry.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            NoCallToolbox(),
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        contract = SimpleNamespace(conId=123)
        pre_send = SimpleNamespace(orderId=77, permId=0, account="DU1234567")
        post_send = SimpleNamespace(
            orderId=77, permId=9001, account="DU1234567"
        )

        executor._register_order(
            order=pre_send,
            contract=contract,
            order_ref="codex-ibkr-paper-30d-a-test",
            action="BUY",
            quantity=Decimal("1"),
            lifecycle_event="ISSUED_PRE_SEND",
        )
        executor._register_order(
            order=post_send,
            contract=contract,
            order_ref="codex-ibkr-paper-30d-a-test",
            action="BUY",
            quantity=Decimal("1"),
            lifecycle_event="BROKER_BOUND",
        )

        rows = db.execute(
            "SELECT client_order_id,perm_id,payload_json FROM experiment_order_registry "
            "WHERE order_ref=? ORDER BY sequence",
            ("codex-ibkr-paper-30d-a-test",),
        ).fetchall()

    assert [(row[0], row[1]) for row in rows] == [(77, 0), (77, 9001)]
    payloads = [json.loads(row[2]) for row in rows]
    assert [item["lifecycle_event"] for item in payloads] == [
        "ISSUED_PRE_SEND",
        "BROKER_BOUND",
    ]
    assert [item["execution_client_id"] for item in payloads] == [19761, 19761]
    assert [item["account"] for item in payloads] == [
        "DU1234567",
        "DU1234567",
    ]


def test_order_registry_rejects_blank_account_anchor(tmp_path):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "registry.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            NoCallToolbox(),
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )

        with pytest.raises(RuntimeError, match="order account identity required"):
            executor._register_order(
                order=SimpleNamespace(orderId=77, permId=0, account=""),
                contract=SimpleNamespace(conId=123),
                order_ref="codex-ibkr-paper-30d-a-test",
                action="BUY",
                quantity=Decimal("1"),
                lifecycle_event="ISSUED_PRE_SEND",
            )

        assert db.execute(
            "SELECT COUNT(*) FROM experiment_order_registry"
        ).fetchone()[0] == 0


def test_cancel_calls_only_selected_owned_order_and_persists_attempt_and_result(
    tmp_path,
):
    with armed_cancel_fixture(tmp_path) as (executor, db, fake_ib, action, value):
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is True
    assert result.order["order_management"] == "CANCEL_ORDER"
    assert fake_ib.cancelled_order_ids == [action.order_id]
    assert fake_ib.global_cancel_calls == 0
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "CANCEL_ATTEMPT",
        "CANCEL_RESULT",
    ]
    assert result.order["post_action_reconciliation"]["target_actionable"] is False


def test_cancel_exact_legacy_bag_reconciles_identity_without_global_cancel(tmp_path):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "cancel-legacy-bag.sqlite3") as db:
        target = bag_lifecycle_trade()
        action = open_order_action_from_trade(target)
        register_legacy_bag_anchors(db, target)
        broker = FakeLifecycleIB(target)
        executor = AutonomousPaperExecutor(
            LifecycleToolbox(broker),
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )

        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is True
    assert broker.cancelled_order_ids == [13]
    assert broker.global_cancel_calls == 0
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "BROKER_BOUND",
        "BROKER_IDENTITY_BOUND",
        "CANCEL_ATTEMPT",
        "CANCEL_RESULT",
    ]
    assert events[2]["contract"]["conId"] == 28812380
    assert len(events[2]["contract"]["comboLegs"]) == 2


def test_cancel_post_write_disconnect_persists_attempt_and_blocks_replay(tmp_path):
    with armed_cancel_fixture(tmp_path, disconnect_after_cancel=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        first = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        second = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert first.success is False
    assert "BROKER_CONFIRMATION_UNAVAILABLE" in first.reason_codes
    assert second.reason_codes == ("DUPLICATE_ORDER_ACTION_REQUEST",)
    assert fake_ib.cancel_calls == 1
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "CANCEL_ATTEMPT",
        "CANCEL_RESULT",
    ]
    assert events[-1]["broker_evidence"]["exception_type"] == "ConnectionError"


def test_confirmed_cancel_is_not_overridden_by_disconnect_cleanup_failure(tmp_path):
    with armed_cancel_fixture(tmp_path, disconnect_raises=True) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )

    assert result.success is True
    assert fake_ib.cancel_calls == 1


def test_cancel_does_not_report_cancelled_when_order_filled_during_request(tmp_path):
    with armed_cancel_fixture(tmp_path, fill_during_cancel=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is False
    assert result.status == "FILLED"
    assert result.reason_codes == ("ORDER_FILLED_DURING_CANCELLATION",)
    assert fake_ib.cancel_calls == 1
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "CANCEL_ATTEMPT",
        "CANCEL_RESULT",
    ]


@pytest.mark.parametrize(
    ("fixture_kwargs", "reason"),
    [
        ({"reject_cancel": True}, "BROKER_CONFIRMATION_UNAVAILABLE"),
        ({"confirmation_timeout": True}, "BROKER_CANCELLATION_UNCONFIRMED"),
    ],
)
def test_cancel_broker_failure_is_explicit(tmp_path, fixture_kwargs, reason):
    with armed_cancel_fixture(tmp_path, **fixture_kwargs) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )

    assert result.success is False
    assert reason in result.reason_codes
    assert fake_ib.cancel_calls == 1
    if fixture_kwargs.get("reject_cancel"):
        assert result.status == "UNCERTAIN"


@pytest.mark.parametrize(
    ("fixture_kwargs", "reason"),
    [
        (
            {"fresh_safety_check": lambda scope: ("KILL_SWITCH_TRIGGERED",)},
            "KILL_SWITCH_TRIGGERED",
        ),
        (
            {
                "operator_control_check": lambda: (
                    "OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE",
                )
            },
            "OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE",
        ),
    ],
)
def test_cancel_control_change_blocks_before_broker_write(
    tmp_path, fixture_kwargs, reason
):
    with armed_cancel_fixture(tmp_path, **fixture_kwargs) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )

    assert result.success is False
    assert reason in result.reason_codes
    assert fake_ib.cancel_calls == 0


def test_cancel_initial_disconnect_is_retried_before_any_write(tmp_path):
    with armed_cancel_fixture(tmp_path, fail_connects=1) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )

    assert result.success is True
    assert result.order["order_management"] == "CANCEL_ORDER"
    assert executor.toolbox.connect_calls == 2
    assert fake_ib.cancel_calls == 1


def test_cancel_result_persistence_failure_is_uncertain_and_not_replayed(
    tmp_path, monkeypatch
):
    with armed_cancel_fixture(tmp_path) as fixture:
        executor, _, fake_ib, action, value = fixture
        original = executor._register_lifecycle_event

        def fail_result(**kwargs):
            if kwargs["lifecycle_event"] == "CANCEL_RESULT":
                raise RuntimeError("database unavailable")
            return original(**kwargs)

        monkeypatch.setattr(executor, "_register_lifecycle_event", fail_result)
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )

    assert result.success is False
    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("LIFECYCLE_RESULT_PERSISTENCE_FAILED",)
    assert fake_ib.cancel_calls == 1


def test_cancel_confirmation_processing_failure_is_persisted_uncertain(tmp_path):
    with armed_cancel_fixture(tmp_path, corrupt_confirmation=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is False
    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("BROKER_CONFIRMATION_UNAVAILABLE",)
    assert fake_ib.cancel_calls == 1
    assert events[-1]["lifecycle_event"] == "CANCEL_RESULT"
    assert events[-1]["broker_evidence"]["confirmation_stage"] == (
        "POST_WRITE_RECONCILIATION"
    )


def test_modify_validation_requires_fresh_quote_and_what_if():
    toolbox, fake_ib, value, action = modification_validation_fixture()

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is True
    assert fake_ib.quote_contract_ids == [action.contract_id]
    assert fake_ib.what_if_calls == 1
    assert result.broker_evidence["whatIf"] is True


def test_modify_validation_binds_gtd_to_what_if_order():
    toolbox, fake_ib, value, action = modification_validation_fixture()
    action = action.model_copy(
        update={
            "new_tif": TimeInForce.GTD,
            "new_good_till_date_utc": datetime(
                2026, 10, 1, 19, 30, tzinfo=timezone.utc
            ),
        }
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is True
    assert fake_ib.last_what_if_order.tif == "GTD"
    assert fake_ib.last_what_if_order.goodTillDate == "20261001 19:30:00 UTC"


def test_modify_gtd_preserves_order_identity_and_confirms_timestamp(tmp_path):
    with armed_modify_fixture(tmp_path) as fixture:
        executor, _, fake_ib, action, value = fixture
        action = action.model_copy(
            update={
                "new_tif": TimeInForce.GTD,
                "new_good_till_date_utc": datetime(
                    2026, 10, 1, 19, 30, tzinfo=timezone.utc
                ),
            }
        )
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )

    assert result.success is True
    assert fake_ib.place_calls[0][1].orderId == action.order_id
    assert fake_ib.place_calls[0][1].tif == "GTD"
    assert fake_ib.place_calls[0][1].goodTillDate == "20261001 19:30:00 UTC"


def test_modify_validation_rejects_pending_cancel_before_quote_or_what_if():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        status="PendingCancel"
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is False
    assert result.reason_codes == ("OPEN_ORDER_PENDING_CANCEL",)
    assert fake_ib.quote_contract_ids == []
    assert fake_ib.what_if_calls == 0


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("new_total_quantity", "OPEN_ORDER_TOTAL_NON_FINITE"),
        ("new_limit_price", "OPEN_ORDER_LIMIT_PRICE_NON_FINITE"),
    ],
)
def test_modify_validation_rejects_non_finite_values_before_what_if(field, reason):
    toolbox, fake_ib, value, action = modification_validation_fixture()
    action = action.model_copy(update={field: Decimal("Infinity")})

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is False
    assert result.reason_codes == (reason,)
    assert fake_ib.what_if_calls == 0


@pytest.mark.parametrize(
    ("quantity", "reason"),
    [
        ("3", "OPEN_ORDER_QUANTITY_INCREASE_FORBIDDEN"),
        ("0.5", "OPEN_ORDER_TOTAL_BELOW_FILLED"),
    ],
)
def test_modify_validation_rejects_unsafe_quantity(quantity, reason):
    toolbox, fake_ib, value, action = modification_validation_fixture(
        total="2", filled="1", new_total=quantity
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is False
    assert result.reason_codes == (reason,)
    assert fake_ib.what_if_calls == 0


def test_modify_to_filled_quantity_requires_reconciliation_not_zero_remainder():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        total="2", filled="1", new_total="1"
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.passed is False
    assert result.reason_codes == ("OPEN_ORDER_WOULD_HAVE_NO_REMAINING_QUANTITY",)


def test_modify_validation_rejects_no_effective_change():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        total="2", new_total="2"
    )
    action = action.model_copy(update={"new_limit_price": Decimal("10")})

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("OPEN_ORDER_NO_EFFECTIVE_CHANGE",)
    assert fake_ib.what_if_calls == 0


def test_modify_validation_requires_usable_quote():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        quote_success=False
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("OPEN_ORDER_QUOTE_UNUSABLE",)
    assert fake_ib.what_if_calls == 0


def test_modify_validation_applies_experiment_equity_to_what_if_margin():
    state = SimpleNamespace(
        commission="1.00",
        minCommission="1.00",
        maxCommission="1.00",
        initMarginChange="501.00",
        maintMarginChange="501.00",
        warningText="",
    )
    toolbox, fake_ib, value, action = modification_validation_fixture(
        what_if_state=state
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("BROKER_MARGIN_EXCEEDS_EXPERIMENT_EQUITY",)
    assert fake_ib.what_if_calls == 1


def test_modify_validation_blocks_limit_change_for_non_limit_order():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        order_type="MKT"
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("OPEN_ORDER_LIMIT_PRICE_CHANGE_REQUIRES_LMT",)
    assert fake_ib.what_if_calls == 0


def test_modify_validation_blocks_unacceptable_what_if_warning():
    state = SimpleNamespace(
        commission="1.00",
        minCommission="1.00",
        maxCommission="1.00",
        initMarginChange="100.00",
        maintMarginChange="100.00",
        warningText="Order not allowed for this account",
    )
    toolbox, fake_ib, value, action = modification_validation_fixture(
        what_if_state=state
    )

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("BROKER_FEASIBILITY_WARNING_BLOCK",)
    assert fake_ib.what_if_calls == 1


def test_modify_validation_blocks_when_broker_state_is_absent():
    toolbox, fake_ib, value, action = modification_validation_fixture()
    fake_ib.target.orderStatus.status = "Cancelled"

    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )

    assert result.reason_codes == ("OPEN_ORDER_NOT_FOUND",)
    assert fake_ib.what_if_calls == 0


def test_modify_preserves_identity_and_submits_same_order_id(tmp_path):
    with armed_modify_fixture(tmp_path) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is True
    assert result.order["order_management"] == "MODIFY_ORDER"
    contract, submitted = fake_ib.place_calls[0]
    assert submitted.orderId == action.order_id
    assert submitted.permId == action.perm_id
    assert submitted.clientId == action.client_id
    assert submitted.orderRef == action.order_ref
    assert submitted.account == "DU1234567"
    assert submitted.action == "BUY"
    assert submitted.orderType == "LMT"
    assert submitted.tif == "DAY"
    assert submitted.transmit is False
    assert submitted.totalQuantity == 1
    assert submitted.lmtPrice == 9.50
    assert contract.conId == action.contract_id
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "MODIFY_ATTEMPT",
        "MODIFY_RESULT",
    ]


def test_modify_exact_legacy_bag_reconciles_and_preserves_combo_identity(tmp_path):
    from ibkr_paper_30d.persistence import Database

    with Database.open(tmp_path / "modify-legacy-bag.sqlite3") as db:
        target = bag_lifecycle_trade()
        action = open_order_action_from_trade(target).model_copy(
            update={
                "new_total_quantity": Decimal("1"),
                "new_limit_price": Decimal("0.85"),
                "reason": "Reduce and reprice the exact BAG order.",
            }
        )
        register_legacy_bag_anchors(db, target)
        broker = FakeModifyIB(target)
        toolbox = IBKRResearchToolbox()
        toolbox._connect = lambda *, client_id=None: broker
        toolbox.live_contract_quote_evidence = lambda ib, contract: {
            "success": True,
            "bid": 0.80,
            "ask": 0.85,
            "market_data_type": 1,
        }
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )

        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is True
    assert len(broker.place_calls) == 1
    contract, submitted = broker.place_calls[0]
    assert contract.conId == 28812380
    assert [(leg.conId, leg.action) for leg in contract.comboLegs] == [
        (913925915, "BUY"),
        (926221865, "SELL"),
    ]
    assert submitted.orderId == 13
    assert submitted.permId == 1401602203
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "BROKER_BOUND",
        "BROKER_IDENTITY_BOUND",
        "MODIFY_ATTEMPT",
        "MODIFY_RESULT",
    ]


def test_bag_identity_tolerates_local_symbol_presentation_drift_only():
    expected = canonical_open_order(bag_lifecycle_trade())["contract"]
    numeric_local_symbol = bag_lifecycle_trade()
    numeric_local_symbol.contract.localSymbol = str(
        numeric_local_symbol.contract.conId
    )
    normalized = canonical_open_order(numeric_local_symbol)["contract"]

    assert normalized == expected
    assert normalized["localSymbol"] == "IOVA"

    actual = deepcopy(expected)
    actual["localSymbol"] = str(actual["conId"])

    assert _contract_identity_matches(
        expected, actual, allow_zero_parent=False
    ) is True

    wrong_parent = deepcopy(actual)
    wrong_parent["conId"] += 1
    assert _contract_identity_matches(
        expected, wrong_parent, allow_zero_parent=False
    ) is False

    wrong_leg = deepcopy(actual)
    wrong_leg["comboLegs"][0]["conId"] += 1
    assert _contract_identity_matches(
        expected, wrong_leg, allow_zero_parent=False
    ) is False


def test_modify_confirmation_rejects_changed_preserved_semantics(tmp_path):
    with armed_modify_fixture(
        tmp_path,
        mutate_preserved_field_after_place=("parentId", 88),
    ) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )

    assert result.success is False
    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("BROKER_MODIFICATION_UNCONFIRMED",)
    assert len(fake_ib.place_calls) == 1
    reconciliation = result.order["post_action_reconciliation"]
    assert reconciliation["preserved_state_matches"] is False


def test_modify_confirmation_processing_failure_is_persisted_uncertain(tmp_path):
    with armed_modify_fixture(tmp_path, corrupt_confirmation=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert result.success is False
    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("BROKER_CONFIRMATION_UNAVAILABLE",)
    assert len(fake_ib.place_calls) == 1
    assert events[-1]["lifecycle_event"] == "MODIFY_RESULT"
    assert events[-1]["broker_evidence"]["confirmation_stage"] == (
        "POST_WRITE_RECONCILIATION"
    )


def test_modify_result_persistence_failure_is_uncertain_and_not_replayed(
    tmp_path, monkeypatch
):
    with armed_modify_fixture(tmp_path) as fixture:
        executor, _, fake_ib, action, value = fixture
        original = executor._register_lifecycle_event

        def fail_result(**kwargs):
            if kwargs["lifecycle_event"] == "MODIFY_RESULT":
                raise RuntimeError("database unavailable")
            return original(**kwargs)

        monkeypatch.setattr(executor, "_register_lifecycle_event", fail_result)
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )

    assert result.success is False
    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("LIFECYCLE_RESULT_PERSISTENCE_FAILED",)
    assert len(fake_ib.place_calls) == 1


def test_confirmed_modify_is_not_overridden_by_disconnect_cleanup_failure(tmp_path):
    with armed_modify_fixture(tmp_path, disconnect_raises=True) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )

    assert result.success is True
    assert len(fake_ib.place_calls) == 1


def test_state_change_after_what_if_blocks_modify_before_place_order(tmp_path):
    with armed_modify_fixture(tmp_path, change_state_after_what_if=True) as fixture:
        executor, _, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )

    assert result.success is False
    assert result.reason_codes == ("OPEN_ORDER_STATE_CHANGED_AFTER_WHAT_IF",)
    assert fake_ib.place_calls == []


def test_modify_post_write_disconnect_is_not_replayed(tmp_path):
    with armed_modify_fixture(tmp_path, disconnect_after_place=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        first = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        second = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        events = lifecycle_events(db, action.order_ref)

    assert first.success is False
    assert "BROKER_CONFIRMATION_UNAVAILABLE" in first.reason_codes
    assert second.reason_codes == ("DUPLICATE_ORDER_ACTION_REQUEST",)
    assert len(fake_ib.place_calls) == 1
    assert [item["lifecycle_event"] for item in events] == [
        "ISSUED_PRE_SEND",
        "MODIFY_ATTEMPT",
        "MODIFY_RESULT",
    ]
    assert events[-1]["broker_evidence"]["exception_type"] == "ConnectionError"
