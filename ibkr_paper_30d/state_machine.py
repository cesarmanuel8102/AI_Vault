from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .repositories import EventRepository
from .types import BrokerState, ExecutionState, KillSwitchState, SystemState


ALLOWED_SYSTEM_EDGES = frozenset(
    {
        (SystemState.BOOTING, SystemState.PREFLIGHT),
        (SystemState.BOOTING, SystemState.BLOCKED),
        (SystemState.BOOTING, SystemState.STOPPED),
        (SystemState.PREFLIGHT, SystemState.READY),
        (SystemState.PREFLIGHT, SystemState.BLOCKED),
        (SystemState.PREFLIGHT, SystemState.PAUSED),
        (SystemState.PREFLIGHT, SystemState.STOPPED),
        (SystemState.BLOCKED, SystemState.PREFLIGHT),
        (SystemState.BLOCKED, SystemState.STOPPED),
        (SystemState.READY, SystemState.PAUSED),
        (SystemState.READY, SystemState.RECOVERING),
        (SystemState.READY, SystemState.BLOCKED),
        (SystemState.READY, SystemState.STOPPED),
        (SystemState.PAUSED, SystemState.PREFLIGHT),
        (SystemState.PAUSED, SystemState.RECOVERING),
        (SystemState.PAUSED, SystemState.BLOCKED),
        (SystemState.PAUSED, SystemState.STOPPED),
        (SystemState.RECOVERING, SystemState.PREFLIGHT),
        (SystemState.RECOVERING, SystemState.BLOCKED),
        (SystemState.RECOVERING, SystemState.STOPPED),
        (SystemState.STOPPED, SystemState.BOOTING),
    }
)

ALLOWED_BROKER_EDGES = frozenset(
    {
        (BrokerState.UNKNOWN, BrokerState.DISCONNECTED),
        (BrokerState.UNKNOWN, BrokerState.CONNECTING),
        (BrokerState.UNKNOWN, BrokerState.BLOCKED),
        (BrokerState.DISCONNECTED, BrokerState.CONNECTING),
        (BrokerState.DISCONNECTED, BrokerState.RECONNECTING),
        (BrokerState.DISCONNECTED, BrokerState.TWO_FACTOR_REQUIRED),
        (BrokerState.DISCONNECTED, BrokerState.AUTH_FAILED),
        (BrokerState.DISCONNECTED, BrokerState.BLOCKED),
        (BrokerState.CONNECTING, BrokerState.CONNECTED_UNVERIFIED),
        (BrokerState.CONNECTING, BrokerState.DISCONNECTED),
        (BrokerState.CONNECTING, BrokerState.TWO_FACTOR_REQUIRED),
        (BrokerState.CONNECTING, BrokerState.AUTH_FAILED),
        (BrokerState.RECONNECTING, BrokerState.CONNECTED_UNVERIFIED),
        (BrokerState.RECONNECTING, BrokerState.DISCONNECTED),
        (BrokerState.RECONNECTING, BrokerState.TWO_FACTOR_REQUIRED),
        (BrokerState.RECONNECTING, BrokerState.AUTH_FAILED),
        (BrokerState.RECONNECTING, BrokerState.BLOCKED),
        (BrokerState.CONNECTED_UNVERIFIED, BrokerState.RECONCILIATION_REQUIRED),
        (BrokerState.CONNECTED_UNVERIFIED, BrokerState.BLOCKED),
        (BrokerState.TWO_FACTOR_REQUIRED, BrokerState.RECONCILIATION_REQUIRED),
        (BrokerState.TWO_FACTOR_REQUIRED, BrokerState.AUTH_FAILED),
        (BrokerState.TWO_FACTOR_REQUIRED, BrokerState.BLOCKED),
        (BrokerState.AUTH_FAILED, BrokerState.CONNECTING),
        (BrokerState.AUTH_FAILED, BrokerState.RECONNECTING),
        (BrokerState.AUTH_FAILED, BrokerState.BLOCKED),
        (BrokerState.RECONCILIATION_REQUIRED, BrokerState.READY),
        (BrokerState.RECONCILIATION_REQUIRED, BrokerState.BLOCKED),
        (BrokerState.READY, BrokerState.DISCONNECTED),
        (BrokerState.READY, BrokerState.CONNECTING),
        (BrokerState.READY, BrokerState.RECONNECTING),
        (BrokerState.READY, BrokerState.CONNECTED_UNVERIFIED),
        (BrokerState.READY, BrokerState.TWO_FACTOR_REQUIRED),
        (BrokerState.READY, BrokerState.AUTH_FAILED),
        (BrokerState.READY, BrokerState.RECONCILIATION_REQUIRED),
        (BrokerState.READY, BrokerState.BLOCKED),
        (BrokerState.BLOCKED, BrokerState.CONNECTING),
        (BrokerState.BLOCKED, BrokerState.RECONNECTING),
        (BrokerState.BLOCKED, BrokerState.RECONCILIATION_REQUIRED),
    }
)

ALLOWED_EXECUTION_EDGES = frozenset(
    {
        (ExecutionState.IDLE, ExecutionState.LOCK_ACQUIRED),
        (ExecutionState.IDLE, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.LOCK_ACQUIRED, ExecutionState.DECISION_PENDING),
        (ExecutionState.LOCK_ACQUIRED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.LOCK_ACQUIRED, ExecutionState.IDLE),
        (ExecutionState.DECISION_PENDING, ExecutionState.DECISION_FROZEN),
        (ExecutionState.DECISION_PENDING, ExecutionState.RISK_BLOCKED),
        (ExecutionState.DECISION_PENDING, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.DECISION_PENDING, ExecutionState.IDLE),
        (ExecutionState.DECISION_FROZEN, ExecutionState.RISK_GATE_PENDING),
        (ExecutionState.DECISION_FROZEN, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.DECISION_FROZEN, ExecutionState.IDLE),
        (ExecutionState.RISK_GATE_PENDING, ExecutionState.ORDER_PENDING_SUBMIT),
        (ExecutionState.RISK_GATE_PENDING, ExecutionState.RISK_BLOCKED),
        (ExecutionState.RISK_GATE_PENDING, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.RISK_BLOCKED, ExecutionState.IDLE),
        (ExecutionState.RISK_BLOCKED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_PENDING_SUBMIT, ExecutionState.ORDER_ACKNOWLEDGED),
        (ExecutionState.ORDER_PENDING_SUBMIT, ExecutionState.ORDER_SUBMIT_UNKNOWN),
        (ExecutionState.ORDER_PENDING_SUBMIT, ExecutionState.ORDER_REJECTED),
        (ExecutionState.ORDER_PENDING_SUBMIT, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_ACKNOWLEDGED),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_WORKING),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_PARTIALLY_FILLED),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_FILLED),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_REJECTED),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.ORDER_STATE_UNCERTAIN),
        (ExecutionState.ORDER_SUBMIT_UNKNOWN, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_WORKING),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_PARTIALLY_FILLED),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_FILLED),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_CANCEL_PENDING),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_REJECTED),
        (ExecutionState.ORDER_ACKNOWLEDGED, ExecutionState.ORDER_STATE_UNCERTAIN),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_PARTIALLY_FILLED),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_FILLED),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_CANCEL_PENDING),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_CANCELLED),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_REJECTED),
        (ExecutionState.ORDER_WORKING, ExecutionState.ORDER_STATE_UNCERTAIN),
        (ExecutionState.ORDER_WORKING, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_PARTIALLY_FILLED, ExecutionState.ORDER_FILLED),
        (ExecutionState.ORDER_PARTIALLY_FILLED, ExecutionState.ORDER_CANCEL_PENDING),
        (ExecutionState.ORDER_PARTIALLY_FILLED, ExecutionState.ORDER_CANCELLED),
        (ExecutionState.ORDER_PARTIALLY_FILLED, ExecutionState.ORDER_STATE_UNCERTAIN),
        (ExecutionState.ORDER_PARTIALLY_FILLED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_FILLED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.ORDER_CANCELLED),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.ORDER_FILLED),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.ORDER_PARTIALLY_FILLED),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.ORDER_REJECTED),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.ORDER_STATE_UNCERTAIN),
        (ExecutionState.ORDER_CANCEL_PENDING, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_CANCELLED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_REJECTED, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.ORDER_STATE_UNCERTAIN, ExecutionState.RECONCILIATION_REQUIRED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.IDLE),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_ACKNOWLEDGED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_WORKING),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_PARTIALLY_FILLED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_FILLED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_CANCELLED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_REJECTED),
        (ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.ORDER_STATE_UNCERTAIN),
    }
)

ALLOWED_KILL_EDGES = frozenset(
    {
        (KillSwitchState.CLEAR, KillSwitchState.TRIGGERED),
        (KillSwitchState.TRIGGERED, KillSwitchState.RECOVERY_REVIEW),
        (KillSwitchState.RECOVERY_REVIEW, KillSwitchState.CLEAR),
        (KillSwitchState.RECOVERY_REVIEW, KillSwitchState.TRIGGERED),
    }
)


@dataclass(frozen=True)
class TransitionReceipt:
    accepted: bool
    fail_closed: bool
    reason: str


class TransitionGuard:
    def __init__(self, events: EventRepository):
        self.events = events
        self.edges = {
            "system": ALLOWED_SYSTEM_EDGES,
            "broker": ALLOWED_BROKER_EDGES,
            "execution": ALLOWED_EXECUTION_EDGES,
            "kill_switch": ALLOWED_KILL_EDGES,
        }

    def _preconditions(
        self, machine: str, target: Enum, context: Mapping[str, bool]
    ) -> bool:
        if machine == "system" and target == SystemState.READY:
            return bool(context.get("all_preflight_gates_pass"))
        if machine == "broker" and target == BrokerState.READY:
            return bool(context.get("full_reconciliation_passed"))
        if machine == "kill_switch" and target == KillSwitchState.CLEAR:
            return bool(
                context.get("owner_reset_authorized")
                and context.get("all_preflight_gates_pass")
                and context.get("execution_lock_verified")
            )
        if machine == "execution" and target == ExecutionState.ORDER_PENDING_SUBMIT:
            return bool(context.get("execution_lock_verified"))
        return True

    def transition(
        self,
        machine: str,
        current: Enum,
        target: Enum,
        context: Mapping[str, bool],
    ) -> TransitionReceipt:
        if machine not in self.edges or (current, target) not in self.edges[machine]:
            receipt = TransitionReceipt(False, True, "TRANSITION_NOT_ALLOWED")
        elif not self._preconditions(machine, target, context):
            receipt = TransitionReceipt(False, True, "PRECONDITION_FAILED")
        else:
            receipt = TransitionReceipt(True, False, "ACCEPTED")
        self.events.append(
            "STATE_TRANSITION",
            {
                "machine": machine,
                "from": str(current.value),
                "to": str(target.value),
                "accepted": receipt.accepted,
                "reason": receipt.reason,
            },
        )
        return receipt
