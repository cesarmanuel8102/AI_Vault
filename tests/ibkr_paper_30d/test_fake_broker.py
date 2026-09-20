from __future__ import annotations

from decimal import Decimal

import pytest

from ibkr_paper_30d.broker import OrderCommand
from ibkr_paper_30d.fake_broker import FakeIBKRPaperBroker, FakePaperExecutionAdapter


@pytest.fixture
def broker() -> FakeIBKRPaperBroker:
    broker = FakeIBKRPaperBroker(account_id="DU123456", history_limit=3)
    broker.connect()
    return broker


@pytest.fixture
def adapter(broker) -> FakePaperExecutionAdapter:
    return FakePaperExecutionAdapter(broker)


@pytest.fixture
def command() -> OrderCommand:
    return OrderCommand(
        decision_id="decision-001",
        idempotency_key="idem-001",
        symbol="SPY",
        contract_id=756733,
        side="BUY",
        quantity=Decimal("2"),
        order_type="LIMIT",
        limit_price=Decimal("500.00"),
        evidence_sha256="a" * 64,
        risk_receipt_id="risk-001",
        lock_fencing_token=7,
    )


def test_duplicate_idempotency_key_transmits_once(adapter, broker, command) -> None:
    first = adapter.submit_order(command)
    second = adapter.submit_order(command)

    assert first.status == "SUCCESS"
    assert second.status == "BLOCKED"
    assert "DUPLICATE_IDEMPOTENCY_KEY" in second.reason_codes
    assert broker.submit_count == 1


def test_same_key_with_changed_command_is_blocked(adapter, broker, command) -> None:
    adapter.submit_order(command)

    result = adapter.submit_order(command.with_quantity(Decimal("1")))

    assert result.status == "BLOCKED"
    assert "IDEMPOTENCY_COMMAND_MISMATCH" in result.reason_codes
    assert broker.submit_count == 1


def test_unknown_submit_is_never_retried(adapter, broker, command) -> None:
    broker.inject("UNKNOWN_SUBMIT_RESULT")

    first = adapter.submit_order(command)
    second = adapter.submit_order(command)

    assert first.status == "UNKNOWN"
    assert second.status == "BLOCKED"
    assert broker.submit_count == 1


def test_fake_lifecycle_supports_partial_fill_modify_cancel(adapter, broker, command) -> None:
    submitted = adapter.submit_order(command)
    identity = submitted.identity
    assert identity is not None

    broker.partial_fill(identity, Decimal("0.5"), Decimal("499.95"))
    modified = adapter.modify_order(command.with_quantity(Decimal("1.5")))
    cancelled = adapter.cancel_order(identity)

    order = broker.orders()[0]
    assert modified.status == "SUCCESS"
    assert cancelled.status == "SUCCESS"
    assert order.status == "CANCELLED"
    assert order.filled_quantity == Decimal("0.5")
    assert len(broker.executions()) == 1


def test_fake_can_fill_or_reject_order(adapter, broker, command) -> None:
    first = adapter.submit_order(command)
    broker.fill(first.identity, Decimal("500.00"))

    rejected_command = command.with_identity("decision-002", "idem-002")
    broker.inject("REJECT_NEXT_ORDER")
    rejected = adapter.submit_order(rejected_command)

    assert broker.orders()[0].status == "FILLED"
    assert rejected.status == "REJECTED"
    assert broker.positions()[0].quantity == Decimal("2")


def test_delayed_ack_is_visible_without_duplicate_submit(adapter, broker, command) -> None:
    broker.inject("DELAY_ACK")

    result = adapter.submit_order(command)

    assert result.status == "PENDING_ACK"
    assert broker.orders()[0].status == "PENDING_ACK"
    broker.release_delayed_acks()
    assert broker.orders()[0].status == "ACKNOWLEDGED"
    assert broker.submit_count == 1


def test_disconnect_and_two_factor_block_submission(adapter, broker, command) -> None:
    broker.disconnect()
    disconnected = adapter.submit_order(command)
    broker.connect(require_2fa=True)
    needs_2fa = adapter.submit_order(command.with_identity("decision-002", "idem-002"))

    assert disconnected.status == "BLOCKED"
    assert "BROKER_DISCONNECTED" in disconnected.reason_codes
    assert needs_2fa.status == "BLOCKED"
    assert "BROKER_2FA_REAUTH_REQUIRED" in needs_2fa.reason_codes
    assert broker.submit_count == 0


def test_restart_preserves_broker_state_and_idempotency(adapter, broker, command) -> None:
    first = adapter.submit_order(command)

    restarted_broker = broker.restart()
    restarted = FakePaperExecutionAdapter(restarted_broker)
    duplicate = restarted.submit_order(command)

    assert duplicate.status == "BLOCKED"
    assert restarted_broker.orders()[0].identity == first.identity
    assert restarted_broker.submit_count == 1


def test_history_limit_is_configurable(adapter, broker, command) -> None:
    for index in range(4):
        current = command.with_identity(f"decision-{index}", f"idem-{index}")
        result = adapter.submit_order(current)
        broker.fill(result.identity, Decimal("500.00"))

    assert len(broker.executions()) == 3
