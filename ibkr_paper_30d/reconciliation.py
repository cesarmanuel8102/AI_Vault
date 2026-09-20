from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .broker import OrderIdentity


class ReconcileOutcome(str, Enum):
    ORDER_FOUND = "ORDER_FOUND"
    ORDER_NOT_FOUND_WITH_PROOF = "ORDER_NOT_FOUND_WITH_PROOF"
    ORDER_STATE_AMBIGUOUS = "ORDER_STATE_AMBIGUOUS"


@dataclass(frozen=True)
class BrokerOrderObservation:
    identity: OrderIdentity
    status: str
    source: str


@dataclass(frozen=True)
class BrokerRecoverySnapshot:
    captured_monotonic: float
    account_id: str
    connected: bool
    authenticated: bool
    open_orders_complete: bool
    completed_orders_complete: bool
    executions_complete: bool
    orders: tuple[BrokerOrderObservation, ...]

    @property
    def queries_complete(self) -> bool:
        return (
            self.open_orders_complete
            and self.completed_orders_complete
            and self.executions_complete
        )


class RecoverySnapshotSource(Protocol):
    def complete_snapshot(
        self, identity: OrderIdentity | None
    ) -> BrokerRecoverySnapshot: ...


class Clock(Protocol):
    def now(self) -> float: ...

    def wait(self, seconds: float) -> None: ...


class ManualClock:
    def __init__(self, initial: float = 0.0):
        self._value = initial

    def now(self) -> float:
        return self._value

    def wait(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("wait interval cannot be negative")
        self._value += seconds

    def advance(self, seconds: float) -> None:
        self.wait(seconds)


@dataclass(frozen=True)
class OrderReconcileResult:
    outcome: ReconcileOutcome
    reason_codes: tuple[str, ...]
    snapshots_examined: int
    matched_order: BrokerOrderObservation | None = None


@dataclass(frozen=True)
class AccountRecoveryInputs:
    database_integrity: bool = True
    subledger_matches: bool = True
    duplicate_orders_absent: bool = True
    market_data_ready: bool = True
    execution_lock_verified: bool = True


@dataclass(frozen=True)
class AccountReconcileResult:
    status: str
    reason_codes: tuple[str, ...]
    account_id: str | None


class Reconciler:
    def __init__(
        self,
        broker: RecoverySnapshotSource,
        *,
        expected_account_id: str,
        not_found_confirmation_window: float | None,
        clock: Clock,
    ):
        if (
            not_found_confirmation_window is not None
            and not_found_confirmation_window <= 0
        ):
            raise ValueError("not-found confirmation window must be positive or unset")
        self.broker = broker
        self.expected_account_id = expected_account_id
        self.window = not_found_confirmation_window
        self.clock = clock

    def with_window(self, window: float | None) -> "Reconciler":
        return Reconciler(
            self.broker,
            expected_account_id=self.expected_account_id,
            not_found_confirmation_window=window,
            clock=self.clock,
        )

    def reconcile_order(self, identity: OrderIdentity) -> OrderReconcileResult:
        first = self.broker.complete_snapshot(identity)
        first_reasons = self._snapshot_failures(first)
        if first_reasons:
            return self._ambiguous(first_reasons, 1)

        first_matches, first_conflict = _matches(first.orders, identity)
        if first_conflict:
            return self._ambiguous(("IDENTITY_CONFLICT",), 1)
        if len(first_matches) > 1:
            return self._ambiguous(("MULTIPLE_MATCHES",), 1)
        if len(first_matches) == 1:
            return OrderReconcileResult(
                ReconcileOutcome.ORDER_FOUND,
                (),
                1,
                first_matches[0],
            )
        if self.window is None:
            return self._ambiguous(("NOT_FOUND_WINDOW_UNSET",), 1)

        self.clock.wait(self.window)
        second = self.broker.complete_snapshot(identity)
        second_reasons = self._snapshot_failures(second)
        if second_reasons:
            return self._ambiguous(second_reasons, 2)
        if second.account_id != first.account_id:
            return self._ambiguous(("ACCOUNT_IDENTITY_CHANGED",), 2)

        second_matches, second_conflict = _matches(second.orders, identity)
        if second_conflict:
            return self._ambiguous(("IDENTITY_CONFLICT",), 2)
        if len(second_matches) > 1:
            return self._ambiguous(("MULTIPLE_MATCHES",), 2)
        if len(second_matches) == 1:
            return OrderReconcileResult(
                ReconcileOutcome.ORDER_FOUND,
                (),
                2,
                second_matches[0],
            )
        if second.captured_monotonic - first.captured_monotonic < self.window:
            return self._ambiguous(("CONFIRMATION_WINDOW_NOT_ELAPSED",), 2)
        return OrderReconcileResult(
            ReconcileOutcome.ORDER_NOT_FOUND_WITH_PROOF,
            (),
            2,
        )

    def reconcile_account(
        self, inputs: AccountRecoveryInputs
    ) -> AccountReconcileResult:
        snapshot = self.broker.complete_snapshot(None)
        reasons = list(self._snapshot_failures(snapshot))
        checks = (
            (inputs.database_integrity, "DATABASE_INTEGRITY_FAILURE"),
            (inputs.subledger_matches, "SUBLEDGER_MISMATCH"),
            (inputs.duplicate_orders_absent, "DUPLICATE_ORDER_DETECTED"),
            (inputs.market_data_ready, "MARKET_DATA_RECOVERY_REQUIRED"),
            (inputs.execution_lock_verified, "EXECUTION_LOCK_AMBIGUOUS"),
        )
        for passed, reason in checks:
            if not passed and reason not in reasons:
                reasons.append(reason)
        return AccountReconcileResult(
            status="BLOCK" if reasons else "PASS",
            reason_codes=tuple(reasons),
            account_id=snapshot.account_id,
        )

    def _snapshot_failures(
        self, snapshot: BrokerRecoverySnapshot
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if not snapshot.connected:
            reasons.append("BROKER_DISCONNECTED")
        if not snapshot.authenticated:
            reasons.append("BROKER_AUTH_UNCERTAIN")
        if not snapshot.queries_complete:
            reasons.append("INCOMPLETE_BROKER_QUERIES")
        if snapshot.account_id != self.expected_account_id:
            reasons.append("ACCOUNT_IDENTITY_MISMATCH")
        return tuple(reasons)

    @staticmethod
    def _ambiguous(
        reasons: tuple[str, ...], snapshots_examined: int
    ) -> OrderReconcileResult:
        return OrderReconcileResult(
            ReconcileOutcome.ORDER_STATE_AMBIGUOUS,
            reasons,
            snapshots_examined,
        )


def _matches(
    observations: tuple[BrokerOrderObservation, ...],
    expected: OrderIdentity,
) -> tuple[list[BrokerOrderObservation], bool]:
    matches: list[BrokerOrderObservation] = []
    conflict = False
    for observation in observations:
        candidate = observation.identity
        if not _shares_identifier(candidate, expected):
            continue
        if _identity_conflicts(candidate, expected):
            conflict = True
            continue
        matches.append(observation)
    return matches, conflict


def _shares_identifier(left: OrderIdentity, right: OrderIdentity) -> bool:
    pairs = (
        (left.client_order_id, right.client_order_id),
        (left.order_ref, right.order_ref),
        (left.ibkr_order_id, right.ibkr_order_id),
        (left.perm_id, right.perm_id),
    )
    return any(a is not None and b is not None and a == b for a, b in pairs)


def _identity_conflicts(left: OrderIdentity, right: OrderIdentity) -> bool:
    pairs = (
        (left.decision_id, right.decision_id),
        (left.idempotency_key, right.idempotency_key),
        (left.client_order_id, right.client_order_id),
        (left.order_ref, right.order_ref),
        (left.ibkr_order_id, right.ibkr_order_id),
        (left.perm_id, right.perm_id),
    )
    return any(a is not None and b is not None and a != b for a, b in pairs)
