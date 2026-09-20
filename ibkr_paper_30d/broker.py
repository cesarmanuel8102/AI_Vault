from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .canonical import sha256_json


class BrokerWriteNotAuthorized(PermissionError):
    pass


@dataclass(frozen=True)
class OrderIdentity:
    decision_id: str
    idempotency_key: str
    client_order_id: str
    order_ref: str
    ibkr_order_id: int | None = None
    perm_id: int | None = None

    @classmethod
    def create(cls, decision_id: str, idempotency_key: str) -> "OrderIdentity":
        if not decision_id or not idempotency_key:
            raise ValueError("decision_id and idempotency_key are required")
        seed = f"{decision_id}\x00{idempotency_key}".encode("utf-8")
        digest = hashlib.sha256(seed).hexdigest()
        return cls(
            decision_id=decision_id,
            idempotency_key=idempotency_key,
            client_order_id=f"codex-{digest[:20]}",
            order_ref=f"ibkr-paper-30d:{digest[:24]}",
        )

    def bind_broker_ids(self, *, ibkr_order_id: int, perm_id: int) -> "OrderIdentity":
        if self.ibkr_order_id is not None or self.perm_id is not None:
            raise ValueError("broker identifiers are already bound")
        return replace(self, ibkr_order_id=ibkr_order_id, perm_id=perm_id)


@dataclass(frozen=True)
class OrderCommand:
    decision_id: str
    idempotency_key: str
    symbol: str
    contract_id: int
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    evidence_sha256: str
    risk_receipt_id: str
    lock_fencing_token: int

    def __post_init__(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("quantity must be finite and positive")
        if self.limit_price is not None and (
            not self.limit_price.is_finite() or self.limit_price <= 0
        ):
            raise ValueError("limit_price must be finite and positive")

    @property
    def sha256(self) -> str:
        return sha256_json(self)

    def with_quantity(self, quantity: Decimal) -> "OrderCommand":
        return replace(self, quantity=quantity)

    def with_identity(self, decision_id: str, idempotency_key: str) -> "OrderCommand":
        return replace(
            self,
            decision_id=decision_id,
            idempotency_key=idempotency_key,
        )


@dataclass(frozen=True)
class BrokerCommandResult:
    status: str
    reason_codes: tuple[str, ...] = ()
    identity: OrderIdentity | None = None


@runtime_checkable
class BrokerReadProtocol(Protocol):
    def account(self) -> object: ...

    def positions(self) -> tuple[object, ...]: ...

    def orders(self) -> tuple[object, ...]: ...

    def executions(self) -> tuple[object, ...]: ...


@runtime_checkable
class BrokerWriteProtocol(Protocol):
    def submit_order(self, command: OrderCommand) -> BrokerCommandResult: ...

    def cancel_order(self, identity: OrderIdentity) -> BrokerCommandResult: ...

    def modify_order(self, command: OrderCommand) -> BrokerCommandResult: ...


class IBKRPaperExecutionAdapter:
    """Real-facing adapter with order writes hard-disabled by current authority."""

    def __init__(self, *, real_client: object | None = None):
        self._real_client = real_client
        self.api_write_calls = 0

    @staticmethod
    def _deny() -> None:
        raise BrokerWriteNotAuthorized("REAL_PAPER_ORDER_WRITE_AUTHORIZED=false")

    def submit_order(self, command: OrderCommand) -> BrokerCommandResult:
        self._deny()

    def cancel_order(self, identity: OrderIdentity) -> BrokerCommandResult:
        self._deny()

    def modify_order(self, command: OrderCommand) -> BrokerCommandResult:
        self._deny()
