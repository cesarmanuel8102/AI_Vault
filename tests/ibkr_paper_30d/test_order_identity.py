from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from ibkr_paper_30d.broker import (
    BrokerWriteNotAuthorized,
    IBKRPaperExecutionAdapter,
    OrderCommand,
    OrderIdentity,
)


def command(**updates) -> OrderCommand:
    values = {
        "decision_id": "decision-001",
        "idempotency_key": "idem-001",
        "symbol": "SPY",
        "contract_id": 756733,
        "side": "BUY",
        "quantity": Decimal("1"),
        "order_type": "LIMIT",
        "limit_price": Decimal("500.00"),
        "evidence_sha256": "a" * 64,
        "risk_receipt_id": "risk-001",
        "lock_fencing_token": 7,
    }
    values.update(updates)
    return OrderCommand(**values)


def test_order_identity_is_deterministic_and_immutable() -> None:
    first = OrderIdentity.create("decision-001", "idem-001")
    second = OrderIdentity.create("decision-001", "idem-001")

    assert first == second
    assert first.client_order_id.startswith("codex-")
    assert first.order_ref.startswith("ibkr-paper-30d:")
    with pytest.raises(FrozenInstanceError):
        first.perm_id = 42


def test_broker_ids_bind_by_creating_a_new_identity() -> None:
    local = OrderIdentity.create("decision-001", "idem-001")
    bound = local.bind_broker_ids(ibkr_order_id=101, perm_id=9001)

    assert local.ibkr_order_id is None
    assert bound.ibkr_order_id == 101
    assert bound.perm_id == 9001
    assert bound.client_order_id == local.client_order_id


class DangerousClient:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name):
        self.calls += 1
        raise AssertionError(f"real API was touched through {name}")


@pytest.mark.parametrize("method", ["submit_order", "cancel_order", "modify_order"])
def test_real_adapter_writes_are_unconditionally_disabled(method) -> None:
    client = DangerousClient()
    adapter = IBKRPaperExecutionAdapter(real_client=client)

    with pytest.raises(
        BrokerWriteNotAuthorized,
        match="REAL_PAPER_ORDER_WRITE_AUTHORIZED=false",
    ):
        if method == "submit_order":
            getattr(adapter, method)(command())
        elif method == "cancel_order":
            getattr(adapter, method)(OrderIdentity.create("decision-001", "idem-001"))
        else:
            getattr(adapter, method)(command(quantity=Decimal("2")))

    assert adapter.api_write_calls == 0
    assert client.calls == 0
