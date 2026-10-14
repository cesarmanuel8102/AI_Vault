from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from test_canary_execution import _request, NOW
from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.canary_execution import CanaryRecoveryRequest
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash


def recovery():
    original = _request(account_identity_sha256=expected_identity_hash("DU12345"))
    return CanaryRecoveryRequest(
        original_request=original, durable_sequence=2,
        execution_key="recovery:exact-eth", owner_authorization_sha256="e" * 64,
        entry_execution_id_sha256=sha256_json("entry-fill"),
        created_at_utc=NOW, expires_at_utc=NOW + timedelta(minutes=5),
    )


class Broker:
    all_order_visibility = True

    def __init__(self, request, quantity=None):
        identity = request.original_request.canonical_contract
        self.contract = SimpleNamespace(conId=identity.con_id, secType="CRYPTO")
        self.quantity = quantity if quantity is not None else request.original_request.quantity
        self.request = request
        self.client = SimpleNamespace(getReqId=lambda: 500)
        self.orders = []
        self.fills = [SimpleNamespace(contract=self.contract, execution=SimpleNamespace(
            execId="entry-fill", acctNumber="DU12345", clientId=19761,
            orderRef=f"codex-ibkr-paper-30d-canary-entry-{request.original_request.sha256[:12]}",
            side="BOT", shares=request.original_request.quantity, price=10,
            permId=1001, orderId=101,
        ))]

    def reqAllOpenOrders(self):
        return []

    def qualifyContracts(self, contract):
        return [contract]

    def positions(self):
        return [] if self.quantity == 0 else [SimpleNamespace(
            account="DU12345", contract=self.contract, position=self.quantity, avgCost=10,
        )]

    def reqExecutions(self):
        return self.fills

    def reqMktData(self, contract, snapshot=True):
        return SimpleNamespace(bid=Decimal("9.99"), ask=Decimal("10.01"))

    def sleep(self, _seconds):
        pass

    def placeOrder(self, contract, order):
        if not getattr(contract, "exchange", ""):
            raise ValueError("IBKR_321_MISSING_ORDER_EXCHANGE")
        self.orders.append(order)
        self.quantity -= Decimal(str(order.totalQuantity))
        order.permId = order.permId or 1002
        order.clientId = 19761
        self.fills.append(SimpleNamespace(contract=contract, execution=SimpleNamespace(
            execId="exit-fill", acctNumber="DU12345", clientId=19761,
            orderRef=order.orderRef, side="SLD", shares=order.totalQuantity,
            price=order.lmtPrice, permId=order.permId, orderId=order.orderId,
        )))
        return SimpleNamespace(order=order, orderStatus=SimpleNamespace(
            status="Filled", filled=order.totalQuantity, remaining=0,
        ))


def writer(broker, claims, receipts, **kwargs):
    return AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(), broker_factory=lambda _id: broker,
        execution_client_id=19761, execution_lock_verifier=lambda: True,
        authority_validator=lambda *_args: (), now_utc=lambda: NOW,
        canary_recovery_claim=lambda request, facts: claims.append((request, facts)) or True,
        canary_recovery_result_persister=lambda request, result: receipts.append(result),
        **kwargs,
    )


def test_recovery_only_sells_verified_owned_fill_without_new_entry():
    request = recovery()
    broker = Broker(request)
    claims, receipts = [], []
    result = writer(broker, claims, receipts)._execute(request, broker)
    assert result.success is True
    assert result.status == "FILLED"
    assert len(broker.orders) == 1
    assert broker.orders[0].action == "SELL"
    assert broker.orders[0].tif == "GTC"
    assert broker.orders[0].totalQuantity == float(request.original_request.quantity)
    assert broker.quantity == 0
    assert len(claims) == len(receipts) == 1


@pytest.mark.parametrize("change", ["quantity", "fill", "client", "expired"])
def test_recovery_blocks_any_changed_identity_or_authority(change):
    request = recovery()
    broker = Broker(request)
    if change == "quantity":
        broker.quantity *= 2
    elif change == "fill":
        broker.fills[0].execution.execId = "forged"
    elif change == "client":
        broker.fills[0].execution.clientId = 44
    else:
        request = request.model_copy(update={"expires_at_utc": NOW - timedelta(seconds=1)})
    claims, receipts = [], []
    result = writer(broker, claims, receipts)._execute(request, broker)
    assert result.success is False
    assert broker.orders == claims == []


def test_recovery_durable_duplicate_claim_never_sends_again():
    request = recovery()
    broker = Broker(request)
    w = writer(broker, [], [])
    w.canary_recovery_claim = lambda *_args: False
    result = w._execute(request, broker)
    assert result.reason_codes == ("CANARY_RECOVERY_ALREADY_CLAIMED",)
    assert broker.orders == []


def test_recovery_without_separate_owner_authority_blocks():
    request = recovery()
    broker = Broker(request)
    w = writer(broker, [], [])
    w.canary_recovery_claim = None
    result = w._execute(request, broker)
    assert result.reason_codes == ("CANARY_RECOVERY_AUTHORITY_REQUIRED",)
    assert broker.orders == []


def test_recovery_rereads_position_after_quote_before_claim():
    request = recovery()
    broker = Broker(request)
    original = broker.reqMktData

    def changed_position(*args, **kwargs):
        broker.quantity *= 2
        return original(*args, **kwargs)

    broker.reqMktData = changed_position
    claims = []
    result = writer(broker, claims, [])._execute(request, broker)
    assert result.success is False
    assert broker.orders == claims == []


def test_recovery_filled_status_without_execution_is_not_certified():
    request = recovery()
    broker = Broker(request)
    actual_place = broker.placeOrder

    def missing_execution(*args):
        trade = actual_place(*args)
        broker.fills.pop()
        return trade

    broker.placeOrder = missing_execution
    result = writer(broker, [], [])._execute(request, broker)
    assert result.status == "UNCERTAIN"


def test_bound_recovery_refreshes_same_order_not_a_second_order():
    request = recovery()
    broker = Broker(request)
    from ib_insync import Order
    ref = f"codex-ibkr-paper-30d-canary-recovery-{request.sha256[:12]}"
    order = Order(orderId=230, permId=9001, clientId=19761, orderRef=ref,
                  action="SELL", totalQuantity=float(request.original_request.quantity),
                  orderType="LMT", lmtPrice=11, tif="GTC", account="DU12345")
    trade = SimpleNamespace(contract=broker.contract, order=order,
                            orderStatus=SimpleNamespace(status="Submitted", filled=0, remaining=order.totalQuantity))
    broker.reqAllOpenOrders = lambda: [] if broker.quantity == 0 else [trade]
    actual_place = broker.placeOrder
    seen_ids = []

    def modify(contract, actual_order):
        seen_ids.append(actual_order.orderId)
        filled = actual_place(contract, actual_order)
        trade.orderStatus = filled.orderStatus
        trade.order = filled.order
        return trade

    broker.placeOrder = modify
    w = writer(broker, [], [])
    w.canary_recovery_bound_order_reader = lambda _request: {
        "orderId": 230, "permId": 9001, "clientId": 19761, "orderRef": ref,
    }
    result = w._execute(request, broker)
    assert result.status == "FILLED"
    assert seen_ids == [230]
    assert broker.quantity == 0
