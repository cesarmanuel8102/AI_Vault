from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.physical_canary import (
    PhysicalCanaryDirective,
    PhysicalCanaryError,
    PhysicalCanaryState,
    PhysicalCanaryStore,
)
from ibkr_paper_30d.repositories import EventRepository


NOW = datetime(2026, 11, 13, 19, 45, tzinfo=timezone.utc)
HEAD = "3" * 40
AUTHORIZATION = "a" * 64


def directive(canary_id: str = "regular-e2e-1") -> PhysicalCanaryDirective:
    return PhysicalCanaryDirective(
        canary_id=canary_id,
        capital_sleeve=CapitalSleeve.REGULAR_SLEEVE,
        owner_authorization_sha256=AUTHORIZATION,
        requested_at_utc=NOW,
        approved_head=HEAD,
    )


def test_request_is_append_only_idempotent_and_one_shot_per_sleeve(tmp_path):
    path = tmp_path / "physical-canary.sqlite3"
    with Database.open(path) as db:
        store = PhysicalCanaryStore(db)
        first = store.request(directive())
        replay = store.request(directive())

        assert first == replay
        assert first.state is PhysicalCanaryState.REQUESTED
        assert store.active() == first
        assert db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type='PHYSICAL_CANARY_REQUESTED'"
        ).fetchone()[0] == 1

        with pytest.raises(
            PhysicalCanaryError, match="PHYSICAL_CANARY_ACTIVE_CONFLICT"
        ):
            store.request(directive("regular-e2e-conflict"))

    with Database.open(path) as db:
        restarted = PhysicalCanaryStore(db).active()

    assert restarted is not None
    assert restarted.directive == directive()
    assert restarted.state is PhysicalCanaryState.REQUESTED


def test_transitions_are_monotonic_and_survive_restart(tmp_path):
    path = tmp_path / "physical-canary.sqlite3"
    with Database.open(path) as db:
        store = PhysicalCanaryStore(db)
        store.request(directive())
        store.append_transition(
            "regular-e2e-1",
            PhysicalCanaryState.ENTRY_SELECTED,
            capital_sleeve=CapitalSleeve.REGULAR_SLEEVE,
            evidence={"invocation_id": "inv-1"},
        )
        current = store.append_transition(
            "regular-e2e-1",
            PhysicalCanaryState.ISSUED_PRE_SEND,
            capital_sleeve=CapitalSleeve.REGULAR_SLEEVE,
            evidence={"order_ref": "physical-regular-e2e-1"},
        )

        assert current.state is PhysicalCanaryState.ISSUED_PRE_SEND
        with pytest.raises(
            PhysicalCanaryError, match="PHYSICAL_CANARY_TRANSITION_INVALID"
        ):
            store.append_transition(
                "regular-e2e-1",
                PhysicalCanaryState.ENTRY_SELECTED,
                capital_sleeve=CapitalSleeve.REGULAR_SLEEVE,
            )

    with Database.open(path) as db:
        restarted = PhysicalCanaryStore(db).projection("regular-e2e-1")

    assert restarted is not None
    assert restarted.state is PhysicalCanaryState.ISSUED_PRE_SEND


def test_projection_rejects_cross_sleeve_event_chain(tmp_path):
    with Database.open(tmp_path / "physical-canary.sqlite3") as db:
        store = PhysicalCanaryStore(db)
        store.request(directive())
        EventRepository(db).append(
            "PHYSICAL_CANARY_ENTRY_SELECTED",
            {
                "canary_id": "regular-e2e-1",
                "capital_sleeve": "CONTINUOUS_SLEEVE",
                "from_state": "REQUESTED",
                "evidence": {},
            },
        )

        with pytest.raises(
            PhysicalCanaryError, match="PHYSICAL_CANARY_SLEEVE_MISMATCH"
        ):
            store.projection("regular-e2e-1")
