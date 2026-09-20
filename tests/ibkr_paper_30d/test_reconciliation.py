from __future__ import annotations

from dataclasses import replace

import pytest

from ibkr_paper_30d.broker import OrderIdentity
from ibkr_paper_30d.reconciliation import (
    AccountRecoveryInputs,
    BrokerOrderObservation,
    BrokerRecoverySnapshot,
    ManualClock,
    ReconcileOutcome,
    Reconciler,
)


NOW = 1_000.0


def identity(suffix: str = "001") -> OrderIdentity:
    return OrderIdentity.create(f"decision-{suffix}", f"idem-{suffix}")


def observation(order_identity=None, *, status="ACKNOWLEDGED", source="OPEN"):
    return BrokerOrderObservation(
        identity=order_identity or identity(),
        status=status,
        source=source,
    )


def snapshot(*orders, **updates) -> BrokerRecoverySnapshot:
    values = {
        "captured_monotonic": NOW,
        "account_id": "DU123456",
        "connected": True,
        "authenticated": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "orders": tuple(orders),
    }
    values.update(updates)
    return BrokerRecoverySnapshot(**values)


class SequenceSource:
    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    def complete_snapshot(self, order_identity):
        value = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
        self.calls += 1
        return value


def reconciler(*snapshots, window=5.0):
    return Reconciler(
        SequenceSource(*snapshots),
        expected_account_id="DU123456",
        not_found_confirmation_window=window,
        clock=ManualClock(NOW),
    )


def test_unset_real_not_found_window_cannot_prove_absence() -> None:
    result = reconciler(snapshot(), window=None).reconcile_order(identity("missing"))

    assert result.outcome == ReconcileOutcome.ORDER_STATE_AMBIGUOUS
    assert "NOT_FOUND_WINDOW_UNSET" in result.reason_codes


@pytest.mark.parametrize("window", [0.1, 5.0, 30.0])
def test_two_complete_snapshots_prove_not_found(window) -> None:
    first = snapshot()
    second = replace(first, captured_monotonic=NOW + window)
    subject = reconciler(first, second, window=window)

    result = subject.reconcile_order(identity("missing"))

    assert result.outcome == ReconcileOutcome.ORDER_NOT_FOUND_WITH_PROOF
    assert result.snapshots_examined == 2
    assert subject.clock.now() == NOW + window


def test_order_appearing_in_second_snapshot_is_found() -> None:
    target = identity()
    result = reconciler(
        snapshot(),
        snapshot(observation(target), captured_monotonic=NOW + 5),
    ).reconcile_order(target)

    assert result.outcome == ReconcileOutcome.ORDER_FOUND
    assert result.matched_order.identity == target


def test_completed_order_or_execution_recovers_crash_window() -> None:
    target = identity()
    completed = observation(target, status="FILLED", source="COMPLETED")

    result = reconciler(snapshot(completed)).reconcile_order(target)

    assert result.outcome == ReconcileOutcome.ORDER_FOUND
    assert result.matched_order.status == "FILLED"


def test_multiple_matches_are_ambiguous() -> None:
    target = identity()
    duplicate = replace(target, ibkr_order_id=999)

    result = reconciler(
        snapshot(observation(target), observation(duplicate))
    ).reconcile_order(target)

    assert result.outcome == ReconcileOutcome.ORDER_STATE_AMBIGUOUS
    assert "MULTIPLE_MATCHES" in result.reason_codes


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"connected": False}, "BROKER_DISCONNECTED"),
        ({"authenticated": False}, "BROKER_AUTH_UNCERTAIN"),
        ({"open_orders_complete": False}, "INCOMPLETE_BROKER_QUERIES"),
        ({"account_id": "DU999999"}, "ACCOUNT_IDENTITY_MISMATCH"),
    ],
)
def test_incomplete_or_untrusted_snapshot_cannot_prove_absence(updates, reason) -> None:
    result = reconciler(snapshot(**updates)).reconcile_order(identity("missing"))

    assert result.outcome == ReconcileOutcome.ORDER_STATE_AMBIGUOUS
    assert reason in result.reason_codes


def test_disconnect_between_snapshots_invalidates_not_found_proof() -> None:
    result = reconciler(
        snapshot(),
        snapshot(connected=False, captured_monotonic=NOW + 5),
    ).reconcile_order(identity("missing"))

    assert result.outcome == ReconcileOutcome.ORDER_STATE_AMBIGUOUS
    assert "BROKER_DISCONNECTED" in result.reason_codes


def test_account_reconciliation_passes_only_when_all_recovery_checks_pass() -> None:
    subject = reconciler(snapshot())

    result = subject.reconcile_account(AccountRecoveryInputs())

    assert result.status == "PASS"
    assert result.reason_codes == ()


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"database_integrity": False}, "DATABASE_INTEGRITY_FAILURE"),
        ({"subledger_matches": False}, "SUBLEDGER_MISMATCH"),
        ({"duplicate_orders_absent": False}, "DUPLICATE_ORDER_DETECTED"),
        ({"market_data_ready": False}, "MARKET_DATA_RECOVERY_REQUIRED"),
        ({"execution_lock_verified": False}, "EXECUTION_LOCK_AMBIGUOUS"),
    ],
)
def test_account_recovery_fails_closed_for_each_required_check(updates, reason) -> None:
    inputs = AccountRecoveryInputs(**updates)

    result = reconciler(snapshot()).reconcile_account(inputs)

    assert result.status == "BLOCK"
    assert reason in result.reason_codes


def test_identity_conflict_is_ambiguous() -> None:
    target = identity()
    conflicting = replace(target, decision_id="other-decision")

    result = reconciler(snapshot(observation(conflicting))).reconcile_order(target)

    assert result.outcome == ReconcileOutcome.ORDER_STATE_AMBIGUOUS
    assert "IDENTITY_CONFLICT" in result.reason_codes
