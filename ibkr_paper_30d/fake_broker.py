from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal

from .broker import BrokerCommandResult, OrderCommand, OrderIdentity


@dataclass(frozen=True)
class FakeAccount:
    account_id: str
    currency: str = "USD"


@dataclass
class FakePosition:
    symbol: str
    contract_id: int
    quantity: Decimal


@dataclass
class FakeOrder:
    identity: OrderIdentity
    command: OrderCommand
    status: str
    filled_quantity: Decimal = Decimal("0")


@dataclass(frozen=True)
class FakeExecution:
    execution_id: str
    identity: OrderIdentity
    quantity: Decimal
    price: Decimal


class FakeIBKRPaperBroker:
    def __init__(self, *, account_id: str, history_limit: int = 100):
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self._account = FakeAccount(account_id)
        self.history_limit = history_limit
        self.connected = False
        self.two_factor_required = False
        self.submit_count = 0
        self._next_order_id = 1000
        self._faults: list[str] = []
        self._orders: list[FakeOrder] = []
        self._executions: list[FakeExecution] = []
        self._positions: dict[int, FakePosition] = {}
        self._command_hashes: dict[str, str] = {}

    def connect(self, *, require_2fa: bool = False) -> None:
        self.connected = True
        self.two_factor_required = require_2fa

    def complete_2fa(self) -> None:
        if not self.connected:
            raise RuntimeError("broker is disconnected")
        self.two_factor_required = False

    def disconnect(self) -> None:
        self.connected = False

    def inject(self, fault: str) -> None:
        self._faults.append(fault)

    def account(self) -> FakeAccount:
        return self._account

    def positions(self) -> tuple[FakePosition, ...]:
        return tuple(copy.deepcopy(list(self._positions.values())))

    def orders(self) -> tuple[FakeOrder, ...]:
        return tuple(copy.deepcopy(self._orders))

    def executions(self) -> tuple[FakeExecution, ...]:
        return tuple(self._executions[-self.history_limit :])

    def command_hash_for(self, idempotency_key: str) -> str | None:
        return self._command_hashes.get(idempotency_key)

    def submit(self, command: OrderCommand) -> BrokerCommandResult:
        self.submit_count += 1
        self._command_hashes[command.idempotency_key] = command.sha256
        identity = OrderIdentity.create(
            command.decision_id, command.idempotency_key
        ).bind_broker_ids(
            ibkr_order_id=self._next_order_id,
            perm_id=900_000 + self._next_order_id,
        )
        self._next_order_id += 1

        if self._consume_fault("UNKNOWN_SUBMIT_RESULT"):
            return BrokerCommandResult("UNKNOWN", ("SUBMIT_RESULT_UNKNOWN",), identity)

        status = "ACKNOWLEDGED"
        result_status = "SUCCESS"
        reasons: tuple[str, ...] = ()
        if self._consume_fault("REJECT_NEXT_ORDER"):
            status = "REJECTED"
            result_status = "REJECTED"
            reasons = ("FAKE_BROKER_REJECTION",)
        elif self._consume_fault("DELAY_ACK"):
            status = "PENDING_ACK"
            result_status = "PENDING_ACK"
        self._orders.append(FakeOrder(identity, command, status))
        return BrokerCommandResult(result_status, reasons, identity)

    def cancel(self, identity: OrderIdentity) -> BrokerCommandResult:
        order = self._find(identity)
        if order is None:
            return BrokerCommandResult("UNKNOWN", ("ORDER_NOT_FOUND",), identity)
        if order.status in {"FILLED", "CANCELLED", "REJECTED"}:
            return BrokerCommandResult("BLOCKED", ("ORDER_NOT_CANCELLABLE",), identity)
        order.status = "CANCELLED"
        return BrokerCommandResult("SUCCESS", identity=order.identity)

    def modify(self, command: OrderCommand) -> BrokerCommandResult:
        order = self._find_by_key(command.idempotency_key)
        if order is None:
            return BrokerCommandResult("UNKNOWN", ("ORDER_NOT_FOUND",))
        if order.status in {"FILLED", "CANCELLED", "REJECTED"}:
            return BrokerCommandResult(
                "BLOCKED", ("ORDER_NOT_MODIFIABLE",), order.identity
            )
        if command.quantity < order.filled_quantity:
            return BrokerCommandResult(
                "BLOCKED", ("QUANTITY_BELOW_FILLED",), order.identity
            )
        order.command = command
        order.status = "WORKING"
        return BrokerCommandResult("SUCCESS", identity=order.identity)

    def partial_fill(
        self,
        identity: OrderIdentity | None,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        order = self._require_order(identity)
        remaining = order.command.quantity - order.filled_quantity
        if quantity <= 0 or quantity >= remaining:
            raise ValueError("partial fill must be positive and less than remaining")
        self._record_fill(order, quantity, price)
        order.status = "PARTIALLY_FILLED"

    def fill(self, identity: OrderIdentity | None, price: Decimal) -> None:
        order = self._require_order(identity)
        remaining = order.command.quantity - order.filled_quantity
        if remaining <= 0:
            raise ValueError("order has no remaining quantity")
        self._record_fill(order, remaining, price)
        order.status = "FILLED"

    def release_delayed_acks(self) -> None:
        for order in self._orders:
            if order.status == "PENDING_ACK":
                order.status = "ACKNOWLEDGED"

    def restart(self) -> "FakeIBKRPaperBroker":
        return copy.deepcopy(self)

    def _record_fill(self, order: FakeOrder, quantity: Decimal, price: Decimal) -> None:
        if not quantity.is_finite() or not price.is_finite() or price <= 0:
            raise ValueError("fill quantity and price must be finite and positive")
        order.filled_quantity += quantity
        signed_quantity = quantity if order.command.side == "BUY" else -quantity
        position = self._positions.get(order.command.contract_id)
        if position is None:
            position = FakePosition(
                order.command.symbol,
                order.command.contract_id,
                Decimal("0"),
            )
            self._positions[order.command.contract_id] = position
        position.quantity += signed_quantity
        self._executions.append(
            FakeExecution(
                execution_id=f"fake-exec-{len(self._executions) + 1}",
                identity=order.identity,
                quantity=quantity,
                price=price,
            )
        )

    def _consume_fault(self, fault: str) -> bool:
        if fault not in self._faults:
            return False
        self._faults.remove(fault)
        return True

    def _find(self, identity: OrderIdentity) -> FakeOrder | None:
        return next(
            (
                order
                for order in self._orders
                if order.identity.client_order_id == identity.client_order_id
                or (
                    identity.perm_id is not None
                    and order.identity.perm_id == identity.perm_id
                )
            ),
            None,
        )

    def _find_by_key(self, idempotency_key: str) -> FakeOrder | None:
        return next(
            (
                order
                for order in self._orders
                if order.identity.idempotency_key == idempotency_key
            ),
            None,
        )

    def _require_order(self, identity: OrderIdentity | None) -> FakeOrder:
        if identity is None:
            raise ValueError("order identity is required")
        order = self._find(identity)
        if order is None:
            raise KeyError(identity.client_order_id)
        return order


class FakePaperExecutionAdapter:
    def __init__(self, broker: FakeIBKRPaperBroker):
        self.broker = broker

    def submit_order(self, command: OrderCommand) -> BrokerCommandResult:
        existing = self.broker.command_hash_for(command.idempotency_key)
        if existing is not None:
            reason = (
                "DUPLICATE_IDEMPOTENCY_KEY"
                if existing == command.sha256
                else "IDEMPOTENCY_COMMAND_MISMATCH"
            )
            return BrokerCommandResult("BLOCKED", (reason,))
        unavailable = self._availability_failure()
        if unavailable is not None:
            return unavailable
        return self.broker.submit(command)

    def cancel_order(self, identity: OrderIdentity) -> BrokerCommandResult:
        unavailable = self._availability_failure()
        return unavailable or self.broker.cancel(identity)

    def modify_order(self, command: OrderCommand) -> BrokerCommandResult:
        unavailable = self._availability_failure()
        return unavailable or self.broker.modify(command)

    def _availability_failure(self) -> BrokerCommandResult | None:
        if not self.broker.connected:
            return BrokerCommandResult("BLOCKED", ("BROKER_DISCONNECTED",))
        if self.broker.two_factor_required:
            return BrokerCommandResult(
                "BLOCKED", ("BROKER_2FA_REAUTH_REQUIRED",)
            )
        return None
