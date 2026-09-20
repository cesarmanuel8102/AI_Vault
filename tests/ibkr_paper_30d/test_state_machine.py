from __future__ import annotations

from itertools import product

import pytest

from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.state_machine import (
    ALLOWED_BROKER_EDGES,
    ALLOWED_EXECUTION_EDGES,
    ALLOWED_KILL_EDGES,
    ALLOWED_SYSTEM_EDGES,
    TransitionGuard,
)
from ibkr_paper_30d.types import (
    BrokerState,
    ExecutionState,
    KillSwitchState,
    SystemState,
)


def valid_context() -> dict[str, bool]:
    return {
        "all_preflight_gates_pass": True,
        "full_reconciliation_passed": True,
        "owner_reset_authorized": True,
        "execution_lock_verified": True,
    }


def forbidden_pairs(enum_type, allowed):
    return [pair for pair in product(enum_type, repeat=2) if pair not in allowed]


@pytest.fixture
def guard(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        yield TransitionGuard(EventRepository(db))


@pytest.mark.parametrize(
    "machine,allowed",
    [
        ("system", ALLOWED_SYSTEM_EDGES),
        ("broker", ALLOWED_BROKER_EDGES),
        ("execution", ALLOWED_EXECUTION_EDGES),
        ("kill_switch", ALLOWED_KILL_EDGES),
    ],
)
def test_every_allowed_transition_is_accepted(machine, allowed, guard) -> None:
    for source, target in allowed:
        receipt = guard.transition(machine, source, target, valid_context())
        assert receipt.accepted is True, (machine, source, target, receipt.reason)
        assert receipt.fail_closed is False


@pytest.mark.parametrize(
    "machine,enum_type,allowed",
    [
        ("system", SystemState, ALLOWED_SYSTEM_EDGES),
        ("broker", BrokerState, ALLOWED_BROKER_EDGES),
        ("execution", ExecutionState, ALLOWED_EXECUTION_EDGES),
        ("kill_switch", KillSwitchState, ALLOWED_KILL_EDGES),
    ],
)
def test_every_unlisted_transition_fails_closed(
    machine, enum_type, allowed, guard
) -> None:
    pairs = forbidden_pairs(enum_type, allowed)
    assert pairs
    for source, target in pairs:
        receipt = guard.transition(machine, source, target, valid_context())
        assert receipt.accepted is False, (machine, source, target)
        assert receipt.fail_closed is True
        assert receipt.reason == "TRANSITION_NOT_ALLOWED"


def test_system_ready_requires_all_preflight_gates(guard) -> None:
    context = valid_context()
    context["all_preflight_gates_pass"] = False

    receipt = guard.transition(
        "system", SystemState.PREFLIGHT, SystemState.READY, context
    )

    assert receipt.accepted is False
    assert receipt.reason == "PRECONDITION_FAILED"


def test_broker_ready_requires_full_reconciliation(guard) -> None:
    context = valid_context()
    context["full_reconciliation_passed"] = False

    receipt = guard.transition(
        "broker",
        BrokerState.RECONCILIATION_REQUIRED,
        BrokerState.READY,
        context,
    )

    assert receipt.accepted is False
    assert receipt.reason == "PRECONDITION_FAILED"


def test_kill_switch_clear_requires_owner_reset_and_verified_lock(guard) -> None:
    context = valid_context()
    context["owner_reset_authorized"] = False

    receipt = guard.transition(
        "kill_switch",
        KillSwitchState.RECOVERY_REVIEW,
        KillSwitchState.CLEAR,
        context,
    )

    assert receipt.accepted is False
    assert receipt.reason == "PRECONDITION_FAILED"


def test_transition_attempts_are_persisted(guard) -> None:
    guard.transition(
        "system", SystemState.BOOTING, SystemState.PREFLIGHT, valid_context()
    )
    guard.transition(
        "system", SystemState.BOOTING, SystemState.READY, valid_context()
    )

    assert guard.events.count() == 2
