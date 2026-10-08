from __future__ import annotations

from pathlib import Path

import pytest

from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.owner_authorization import (
    OWNER_PHRASE,
    OwnerAuthorizationError,
    create_owner_authorization,
    validate_owner_authorization,
)
from ibkr_paper_30d.persistence import Database


OWNER_SID = "S-1-5-21-test-owner"


def paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "autonomous.sqlite3", tmp_path / "owner_authorization_v1.json"


def create(tmp_path: Path, **updates):
    db_path, receipt_path = paths(tmp_path)
    arguments = {
        "db_path": db_path,
        "receipt_path": receipt_path,
        "phrase": OWNER_PHRASE,
        "actor_sid": OWNER_SID,
        "elevated": True,
    }
    arguments.update(updates)
    return create_owner_authorization(**arguments)


def test_create_requires_exact_owner_phrase_before_database_creation(tmp_path: Path):
    db_path, receipt_path = paths(tmp_path)

    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_PHRASE_INVALID"):
        create(tmp_path, phrase="almost")

    assert not db_path.exists()
    assert not receipt_path.exists()


def test_create_requires_elevated_owner_boundary(tmp_path: Path):
    db_path, receipt_path = paths(tmp_path)

    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_REQUIRES_ELEVATION"):
        create(tmp_path, elevated=False)

    assert not db_path.exists()
    assert not receipt_path.exists()


def test_validate_never_creates_missing_authorization(tmp_path: Path):
    db_path, receipt_path = paths(tmp_path)

    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_MISSING"):
        validate_owner_authorization(
            db_path=db_path,
            receipt_path=receipt_path,
            expected_actor_sid=OWNER_SID,
        )

    assert not db_path.exists()
    assert not receipt_path.exists()


def test_authorization_is_bound_to_exact_clock_owner_and_initial_clear(tmp_path: Path):
    db_path, receipt_path = paths(tmp_path)

    receipt = create(tmp_path)

    assert receipt["start_utc"] == "2026-09-23T13:30:00Z"
    assert receipt["end_utc"] == "2026-10-23T13:30:00Z"
    assert receipt["duration_days"] == 30
    assert receipt["initial_allocation"] == "500"
    assert receipt["authorization_state"] == "AUTHORIZED"
    assert receipt["actor_sid"] == OWNER_SID
    assert receipt_path.is_file()
    with Database.open(db_path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"
        assert db.execute("SELECT COUNT(*) FROM experiment_clock_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM experiment_authorization_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM kill_switch_events").fetchone()[0] == 1


def test_idempotent_create_does_not_append_control_events(tmp_path: Path):
    db_path, _ = paths(tmp_path)
    first = create(tmp_path)

    second = create(tmp_path)

    assert second == first
    with Database.open(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM experiment_clock_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM experiment_authorization_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM kill_switch_events").fetchone()[0] == 1


def test_existing_authorization_rejects_different_owner_sid(tmp_path: Path):
    create(tmp_path)

    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_OWNER_MISMATCH"):
        create(tmp_path, actor_sid="S-1-5-21-other-owner")


def test_owner_authorization_remains_valid_while_kill_switch_is_triggered(tmp_path: Path):
    db_path, receipt_path = paths(tmp_path)
    expected = create(tmp_path)
    with Database.open(db_path) as db:
        switch = KillSwitchStore(db)
        switch.set("KILL_SWITCH_TRIGGERED", reason="owner stop", actor=OWNER_SID)

    assert validate_owner_authorization(
        db_path=db_path,
        receipt_path=receipt_path,
        expected_actor_sid=OWNER_SID,
    ) == expected
