from __future__ import annotations

from contextlib import contextmanager

import pytest

from ibkr_paper_30d.orchestrator import (
    BrokerEvent,
    HeartbeatMonitor,
    OrchestrationBlocked,
    PaperOrchestrator,
    RecoveryEvidence,
)
from ibkr_paper_30d.types import BrokerState, SystemState


class FakeAlerts:
    def __init__(self, trace):
        self.trace = trace
        self.events = []

    def raise_event(self, event_type, *, owner_action_required=False):
        self.trace.append(f"alert:{event_type}")
        receipt = type(
            "AlertReceipt",
            (),
            {
                "event_type": event_type,
                "owner_action_required": owner_action_required,
            },
        )()
        self.events.append(receipt)
        return receipt


class FakeLock:
    def __init__(self, trace, *, acquired=True):
        self.trace = trace
        self.acquired = acquired

    @contextmanager
    def hold(self):
        self.trace.append("execution_lock")
        if not self.acquired:
            raise OrchestrationBlocked("EXECUTION_LOCK_AMBIGUOUS")
        yield "lock-receipt"


class FakeTrader:
    def __init__(self, trace):
        self.trace = trace
        self.calls = 0

    def invoke(self, trigger, bundle):
        self.trace.append("trader")
        self.calls += 1
        return {"decision": "NO_TRADE", "bundle": bundle}


def passing_gate(name, trace):
    def gate():
        trace.append(name)
        return True

    return gate


def build(*, gate_overrides=None, lock_acquired=True):
    trace = []
    alerts = FakeAlerts(trace)
    lock = FakeLock(trace, acquired=lock_acquired)
    trader = FakeTrader(trace)
    gates = {
        name: passing_gate(name, trace)
        for name in (
            "kill_switch",
            "paper_identity",
            "reconciliation",
            "heartbeat",
            "subledger",
            "market_data",
        )
    }
    gates.update(gate_overrides or {})

    def freeze(trigger):
        trace.append("freeze_bundle")
        return {"trigger": trigger}

    subject = PaperOrchestrator(
        alerts=alerts,
        execution_lock=lock,
        trader=trader,
        gates=gates,
        freeze_bundle=freeze,
        heartbeat=HeartbeatMonitor(timeout_seconds=10, initial_monotonic=100),
    )
    subject.system_state = SystemState.READY
    subject.broker_state = BrokerState.READY
    return subject, alerts, trader, trace


def full_recovery(**updates):
    values = {
        "broker_reconciliation_passed": True,
        "execution_lock_verified": True,
        "database_integrity": True,
        "subledger_matches": True,
        "heartbeats_fresh": True,
    }
    values.update(updates)
    return RecoveryEvidence(**values)


def test_orchestrator_exposes_no_order_write_methods_or_adapter() -> None:
    subject, _, _, _ = build()

    assert not hasattr(subject, "submit_order")
    assert not hasattr(subject, "cancel_order")
    assert not hasattr(subject, "modify_order")
    assert "broker" not in vars(subject)


def test_2fa_requires_owner_and_full_reconciliation() -> None:
    subject, alerts, _, _ = build()

    subject.handle(BrokerEvent.TWO_FACTOR_REQUIRED)

    assert subject.system_state == SystemState.PAUSED
    assert subject.broker_state == BrokerState.TWO_FACTOR_REQUIRED
    assert subject.last_alert.owner_action_required is True

    subject.handle(BrokerEvent.AUTHENTICATED)
    assert subject.broker_state == BrokerState.RECONCILIATION_REQUIRED
    assert subject.system_state == SystemState.PAUSED

    subject.handle(
        BrokerEvent.RECONCILIATION_COMPLETED,
        recovery=full_recovery(subledger_matches=False),
    )
    assert subject.broker_state == BrokerState.BLOCKED
    assert subject.system_state == SystemState.BLOCKED
    assert alerts.events[-1].event_type == "RECOVERY_GATE_FAILURE"


def test_2fa_returns_to_ready_only_after_every_recovery_gate() -> None:
    subject, _, _, _ = build()
    subject.handle(BrokerEvent.TWO_FACTOR_REQUIRED)
    subject.handle(BrokerEvent.AUTHENTICATED)

    subject.handle(BrokerEvent.RECONCILIATION_COMPLETED, recovery=full_recovery())

    assert subject.broker_state == BrokerState.READY
    assert subject.system_state == SystemState.READY


def test_auth_failure_pauses_and_alerts() -> None:
    subject, _, _, _ = build()

    subject.handle(BrokerEvent.AUTH_FAILED)

    assert subject.system_state == SystemState.PAUSED
    assert subject.broker_state == BrokerState.AUTH_FAILED
    assert subject.last_alert.event_type == "BROKER_AUTH_FAILED"


def test_heartbeat_timeout_freezes_authority_and_alerts() -> None:
    subject, _, _, _ = build()

    result = subject.evaluate_heartbeat(now_monotonic=111)

    assert result == "TIMEOUT"
    assert subject.system_state == SystemState.PAUSED
    assert subject.last_alert.event_type == "BROKER_HEARTBEAT_TIMEOUT"


def test_fresh_heartbeat_does_not_change_ready_state() -> None:
    subject, _, _, _ = build()
    subject.record_heartbeat(now_monotonic=105)

    assert subject.evaluate_heartbeat(now_monotonic=114) == "FRESH"
    assert subject.system_state == SystemState.READY


def test_cycle_gate_order_is_fixed_and_contains_no_execution() -> None:
    subject, _, trader, trace = build()

    result = subject.evaluate_cycle("SCHEDULED")

    assert result["decision"] == "NO_TRADE"
    assert trader.calls == 1
    assert trace == [
        "execution_lock",
        "kill_switch",
        "paper_identity",
        "reconciliation",
        "heartbeat",
        "subledger",
        "market_data",
        "freeze_bundle",
        "trader",
    ]


def test_failed_gate_pauses_before_bundle_or_trader_invocation() -> None:
    trace = []

    def blocked_market():
        trace.append("market_data")
        return False

    subject, _, trader, actual_trace = build(
        gate_overrides={"market_data": blocked_market}
    )

    with pytest.raises(OrchestrationBlocked, match="MARKET_DATA_GATE_BLOCKED"):
        subject.evaluate_cycle("SCHEDULED")

    assert subject.system_state == SystemState.PAUSED
    assert trader.calls == 0
    assert "freeze_bundle" not in actual_trace


def test_restart_never_restores_ready_without_reconciliation() -> None:
    subject, _, _, _ = build()

    subject.handle(BrokerEvent.RUNTIME_RESTARTED)

    assert subject.system_state == SystemState.RECOVERING
    assert subject.broker_state == BrokerState.RECONCILIATION_REQUIRED


def test_kill_switch_event_pauses_and_alerts() -> None:
    subject, _, _, _ = build()

    subject.handle(BrokerEvent.KILL_SWITCH_TRIGGERED)

    assert subject.system_state == SystemState.PAUSED
    assert subject.last_alert.event_type == "KILL_SWITCH_TRIGGERED"
