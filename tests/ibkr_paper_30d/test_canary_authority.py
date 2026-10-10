from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canary_authority import (
    CanaryAuthorityValidator,
    CanaryBrokerLifecycleReceipt,
    CanaryExecutionTarget,
    CanaryLifecycleError,
    CanaryLifecycleRecorder,
    CanaryMaintenanceGate,
    MaintenanceSafetyState,
    RollbackEnvelope,
)
from ibkr_paper_30d.multi_universe_models import CanaryAuthorization


NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
FAMILY = "1" * 64
CONTRACT = "2" * 64
SUCCESSOR = "3" * 64
ACCOUNT = "4" * 64


def _receipt(recorder, step, ordinal, **overrides):
    values = {
        "canary_id": recorder.canary_id,
        "step": step,
        "endpoint": "PAPER",
        "account_identity_sha256": ACCOUNT,
        "product_family_sha256": FAMILY,
        "contract_identity_sha256": CONTRACT,
        "broker_event_id_sha256": f"{ordinal:064x}",
        "broker_snapshot_sha256": f"{ordinal + 8:064x}",
        "previous_receipt_sha256": recorder.last_receipt_sha256,
        "observed_at_utc": NOW + timedelta(seconds=ordinal),
        "open_orders": 0 if step in {"FLAT_STATE", "ECONOMICS_RECONCILED"} else 1,
        "positions": 0 if step in {"SUBMITTED", "BROKER_BOUND", "FLAT_STATE", "ECONOMICS_RECONCILED"} else 1,
        "economics_reconciled": step == "ECONOMICS_RECONCILED",
    }
    values.update(overrides)
    return CanaryBrokerLifecycleReceipt(**values)


def _authorization(**overrides) -> CanaryAuthorization:
    values = {
        "authorization_id": "canary-auth-1",
        "owner_id": "owner",
        "account_identity_sha256": ACCOUNT,
        "successor_definition_sha256": SUCCESSOR,
        "product_family_sha256": FAMILY,
        "contract_scope_sha256": (CONTRACT,),
        "maximum_debit_usd": Decimal("10.00"),
        "maximum_loss_usd": Decimal("12.00"),
        "fee_allowance_usd": Decimal("1.00"),
        "maximum_order_count": 2,
        "issued_at_utc": NOW - timedelta(minutes=1),
        "expires_at_utc": NOW + timedelta(minutes=30),
    }
    values.update(overrides)
    return CanaryAuthorization(**values)


def _target(**overrides) -> CanaryExecutionTarget:
    values = {
        "endpoint": "PAPER",
        "account_identity_sha256": ACCOUNT,
        "successor_definition_sha256": SUCCESSOR,
        "product_family_sha256": FAMILY,
        "contract_identity_sha256": CONTRACT,
        "debit_usd": Decimal("10.00"),
        "maximum_loss_usd": Decimal("12.00"),
        "estimated_fees_usd": Decimal("1.00"),
        "order_count": 2,
        "capital_replenishment_usd": Decimal("0"),
        "sleeve_transfer_usd": Decimal("0"),
    }
    values.update(overrides)
    return CanaryExecutionTarget(**values)


def test_exact_canary_budget_and_scope_passes():
    receipt = CanaryAuthorityValidator.validate(_authorization(), _target(), NOW)
    assert receipt.status == "PASS"
    assert receipt.freeze_new_order_authority is False


@pytest.mark.parametrize(
    "authorization,target,now,reason",
    [
        (None, _target(), NOW, "CANARY_AUTHORIZATION_MISSING"),
        (_authorization(), _target(), NOW + timedelta(hours=1), "CANARY_AUTHORIZATION_EXPIRED"),
        (_authorization(), _target(product_family_sha256="f" * 64), NOW, "CANARY_FAMILY_MISMATCH"),
        (_authorization(), _target(debit_usd="10.01"), NOW, "CANARY_DEBIT_EXCEEDED"),
        (_authorization(), _target(maximum_loss_usd="12.01"), NOW, "CANARY_LOSS_EXCEEDED"),
        (_authorization(), _target(estimated_fees_usd="1.01"), NOW, "CANARY_FEES_EXCEEDED"),
        (_authorization(), _target(order_count=3), NOW, "CANARY_ORDER_COUNT_EXCEEDED"),
        (_authorization(), _target(capital_replenishment_usd="0.01"), NOW, "CANARY_REPLENISHMENT_FORBIDDEN"),
        (_authorization(), _target(sleeve_transfer_usd="0.01"), NOW, "CANARY_SLEEVE_TRANSFER_FORBIDDEN"),
        (_authorization(), _target(endpoint="LIVE"), NOW, "POSSIBLE_LIVE_CONNECTION"),
    ],
)
def test_canary_authority_fails_closed_at_exact_boundary(
    authorization, target, now, reason
):
    receipt = CanaryAuthorityValidator.validate(authorization, target, now)
    assert receipt.status == "BLOCK"
    assert receipt.freeze_new_order_authority is True
    assert reason in receipt.reason_codes


def test_full_canary_lifecycle_requires_ordered_broker_evidence():
    recorder = CanaryLifecycleRecorder("canary-1", ACCOUNT, FAMILY, CONTRACT)
    for ordinal, step in enumerate(recorder.sequence, 1):
        projection = recorder.record(_receipt(recorder, step, ordinal))

    assert projection.status == "PASS"
    assert projection.full_lifecycle_verified is True
    assert projection.flat is True


def test_no_fill_terminal_order_cannot_certify_family():
    recorder = CanaryLifecycleRecorder("canary-1", ACCOUNT, FAMILY, CONTRACT)
    recorder.record(_receipt(recorder, "SUBMITTED", 1))
    recorder.record(_receipt(recorder, "BROKER_BOUND", 2))
    projection = recorder.record(
        _receipt(recorder, "TERMINAL_NO_FILL", 3, open_orders=0, positions=0)
    )

    assert projection.status == "TRANSMIT_ONLY"
    assert projection.full_lifecycle_verified is False
    with pytest.raises(CanaryLifecycleError, match="LIFECYCLE_STEP_OUT_OF_ORDER"):
        recorder.record(_receipt(recorder, "POSITION_VISIBLE", 4))


def test_arbitrary_hash_cannot_be_used_as_broker_lifecycle_evidence():
    recorder = CanaryLifecycleRecorder("canary-1", ACCOUNT, FAMILY, CONTRACT)

    with pytest.raises(TypeError, match="CanaryBrokerLifecycleReceipt"):
        recorder.record("a" * 64)


def test_lifecycle_receipt_must_preserve_identity_and_hash_chain():
    recorder = CanaryLifecycleRecorder("canary-1", ACCOUNT, FAMILY, CONTRACT)
    recorder.record(_receipt(recorder, "SUBMITTED", 1))

    wrong_account = _receipt(
        recorder,
        "BROKER_BOUND",
        2,
        account_identity_sha256="f" * 64,
    )
    with pytest.raises(CanaryLifecycleError, match="CANARY_RECEIPT_IDENTITY_MISMATCH"):
        recorder.record(wrong_account)

    broken_chain = _receipt(
        recorder,
        "BROKER_BOUND",
        2,
        previous_receipt_sha256="e" * 64,
    )
    with pytest.raises(CanaryLifecycleError, match="CANARY_RECEIPT_CHAIN_MISMATCH"):
        recorder.record(broken_chain)


def test_rollback_envelope_must_be_strictly_shorter_than_deadline():
    passed = RollbackEnvelope.evaluate(
        timedelta(seconds=10),
        timedelta(seconds=20),
        timedelta(seconds=5),
        timedelta(seconds=36),
    )
    equal = RollbackEnvelope.evaluate(
        timedelta(seconds=10),
        timedelta(seconds=20),
        timedelta(seconds=5),
        timedelta(seconds=35),
    )
    assert passed.status == "PASS"
    assert equal.status == "BLOCK"
    assert equal.reason_codes == ("ROLLBACK_ENVELOPE_UNSAFE",)


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"day1_open_order_count": 1}, "DAY1_OPEN_ORDER_PRESENT"),
        ({"day1_uncovered_position_count": 1}, "DAY1_UNCOVERED_POSITION_PRESENT"),
        ({"writer_count": 2}, "SECOND_WRITER_PRESENT"),
        ({"broker_state_certain": False}, "BROKER_STATE_UNCERTAIN"),
    ],
)
def test_maintenance_never_liquidates_day1_for_canary_convenience(updates, reason):
    values = {
        "day1_open_order_count": 0,
        "day1_uncovered_position_count": 0,
        "writer_count": 1,
        "broker_state_certain": True,
    }
    values.update(updates)
    decision = CanaryMaintenanceGate.evaluate(MaintenanceSafetyState(**values))
    assert decision.status == "BLOCK"
    assert reason in decision.reason_codes
    assert decision.day1_liquidation_permitted is False
