from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canary_authority import (
    CanaryAuthorityValidator,
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
    recorder = CanaryLifecycleRecorder("canary-1", FAMILY, CONTRACT)
    recorder.record_submit("a" * 64)
    recorder.record_bind("b" * 64)
    recorder.record_entry_fill("c" * 64)
    recorder.record_position("d" * 64)
    recorder.record_management("e" * 64)
    recorder.record_exit_fill("f" * 64)
    recorder.record_flat_state("0" * 64, open_orders=0, positions=0)
    projection = recorder.record_economics("9" * 64, reconciled=True)

    assert projection.status == "PASS"
    assert projection.full_lifecycle_verified is True
    assert projection.flat is True


def test_no_fill_terminal_order_cannot_certify_family():
    recorder = CanaryLifecycleRecorder("canary-1", FAMILY, CONTRACT)
    recorder.record_submit("a" * 64)
    recorder.record_bind("b" * 64)
    projection = recorder.record_terminal_no_fill("c" * 64)

    assert projection.status == "TRANSMIT_ONLY"
    assert projection.full_lifecycle_verified is False
    with pytest.raises(CanaryLifecycleError, match="LIFECYCLE_STEP_OUT_OF_ORDER"):
        recorder.record_position("d" * 64)


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
