from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, ContextManager, Mapping, Protocol

from .types import BrokerState, SystemState


class BrokerEvent(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    TWO_FACTOR_REQUIRED = "TWO_FACTOR_REQUIRED"
    AUTHENTICATED = "AUTHENTICATED"
    AUTH_FAILED = "AUTH_FAILED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    RUNTIME_RESTARTED = "RUNTIME_RESTARTED"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"


class OrchestrationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryEvidence:
    broker_reconciliation_passed: bool
    execution_lock_verified: bool
    database_integrity: bool
    subledger_matches: bool
    heartbeats_fresh: bool

    @property
    def all_passed(self) -> bool:
        return all(
            (
                self.broker_reconciliation_passed,
                self.execution_lock_verified,
                self.database_integrity,
                self.subledger_matches,
                self.heartbeats_fresh,
            )
        )


class AlertSink(Protocol):
    def raise_event(
        self, event_type: str, *, owner_action_required: bool = False
    ) -> object: ...


class LockBoundary(Protocol):
    def hold(self) -> ContextManager[object]: ...


class TraderBoundary(Protocol):
    def invoke(self, trigger: str, bundle: object) -> object: ...


class HeartbeatMonitor:
    def __init__(self, *, timeout_seconds: float, initial_monotonic: float | None = None):
        if timeout_seconds <= 0:
            raise ValueError("heartbeat timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self.last_monotonic = initial_monotonic

    def record(self, now_monotonic: float) -> None:
        if self.last_monotonic is not None and now_monotonic < self.last_monotonic:
            raise ValueError("monotonic heartbeat cannot move backwards")
        self.last_monotonic = now_monotonic

    def evaluate(self, now_monotonic: float) -> str:
        if self.last_monotonic is None:
            return "TIMEOUT"
        if now_monotonic < self.last_monotonic:
            return "CLOCK_ERROR"
        if now_monotonic - self.last_monotonic > self.timeout_seconds:
            return "TIMEOUT"
        return "FRESH"


REQUIRED_GATE_ORDER = (
    "kill_switch",
    "paper_identity",
    "reconciliation",
    "heartbeat",
    "subledger",
    "market_data",
)


class PaperOrchestrator:
    """Coordinates read/gate boundaries and intentionally owns no order adapter."""

    def __init__(
        self,
        *,
        alerts: AlertSink,
        execution_lock: LockBoundary,
        trader: TraderBoundary,
        gates: Mapping[str, Callable[[], bool]],
        freeze_bundle: Callable[[str], object],
        heartbeat: HeartbeatMonitor,
    ):
        missing = [name for name in REQUIRED_GATE_ORDER if name not in gates]
        if missing:
            raise ValueError(f"missing orchestrator gates: {', '.join(missing)}")
        self.alerts = alerts
        self.execution_lock = execution_lock
        self.trader = trader
        self.gates = {name: gates[name] for name in REQUIRED_GATE_ORDER}
        self.freeze_bundle = freeze_bundle
        self.heartbeat = heartbeat
        self.system_state = SystemState.BOOTING
        self.broker_state = BrokerState.UNKNOWN
        self.last_alert: object | None = None

    def handle(
        self,
        event: BrokerEvent,
        *,
        recovery: RecoveryEvidence | None = None,
    ) -> None:
        if event is BrokerEvent.TWO_FACTOR_REQUIRED:
            self.system_state = SystemState.PAUSED
            self.broker_state = BrokerState.TWO_FACTOR_REQUIRED
            self._alert("BROKER_2FA_REAUTH_REQUIRED", owner_action_required=True)
            return
        if event is BrokerEvent.AUTHENTICATED:
            self.broker_state = BrokerState.RECONCILIATION_REQUIRED
            self.system_state = SystemState.PAUSED
            return
        if event is BrokerEvent.AUTH_FAILED:
            self.system_state = SystemState.PAUSED
            self.broker_state = BrokerState.AUTH_FAILED
            self._alert("BROKER_AUTH_FAILED")
            return
        if event is BrokerEvent.CONNECTED:
            self.broker_state = BrokerState.CONNECTED_UNVERIFIED
            self.system_state = SystemState.PREFLIGHT
            return
        if event is BrokerEvent.DISCONNECTED:
            self.broker_state = BrokerState.DISCONNECTED
            self.system_state = SystemState.PAUSED
            self._alert("BROKER_STATE_UNCERTAIN")
            return
        if event is BrokerEvent.RECONNECTING:
            self.broker_state = BrokerState.RECONNECTING
            self.system_state = SystemState.PAUSED
            return
        if event is BrokerEvent.RUNTIME_RESTARTED:
            self.system_state = SystemState.RECOVERING
            self.broker_state = BrokerState.RECONCILIATION_REQUIRED
            return
        if event is BrokerEvent.KILL_SWITCH_TRIGGERED:
            self.system_state = SystemState.PAUSED
            self._alert("KILL_SWITCH_TRIGGERED")
            return
        if event is BrokerEvent.RECONCILIATION_COMPLETED:
            if recovery is not None and recovery.all_passed:
                self.broker_state = BrokerState.READY
                self.system_state = SystemState.READY
            else:
                self.broker_state = BrokerState.BLOCKED
                self.system_state = SystemState.BLOCKED
                self._alert("RECOVERY_GATE_FAILURE")
            return
        raise ValueError(f"unsupported broker event: {event}")

    def record_heartbeat(self, *, now_monotonic: float) -> None:
        self.heartbeat.record(now_monotonic)

    def evaluate_heartbeat(self, *, now_monotonic: float) -> str:
        status = self.heartbeat.evaluate(now_monotonic)
        if status != "FRESH":
            self.system_state = SystemState.PAUSED
            self._alert("BROKER_HEARTBEAT_TIMEOUT")
        return status

    def evaluate_cycle(self, trigger: str) -> object:
        if self.system_state is not SystemState.READY:
            raise OrchestrationBlocked("SYSTEM_NOT_READY")
        if self.broker_state is not BrokerState.READY:
            raise OrchestrationBlocked("BROKER_NOT_READY")
        try:
            with self.execution_lock.hold():
                for name, gate in self.gates.items():
                    if not gate():
                        raise OrchestrationBlocked(f"{name.upper()}_GATE_BLOCKED")
                bundle = self.freeze_bundle(trigger)
                return self.trader.invoke(trigger, bundle)
        except OrchestrationBlocked as exc:
            self.system_state = SystemState.PAUSED
            event_type = (
                "EXECUTION_LOCK_AMBIGUOUS"
                if "EXECUTION_LOCK" in str(exc)
                else "FAIL_CLOSED"
            )
            self._alert(event_type)
            raise

    def _alert(self, event_type: str, *, owner_action_required: bool = False) -> None:
        self.last_alert = self.alerts.raise_event(
            event_type,
            owner_action_required=owner_action_required,
        )
