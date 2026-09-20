from __future__ import annotations

import sqlite3

import pytest

from ibkr_paper_30d.evidence import (
    EvidenceFreezer,
    ImmutableRecordError,
    MissingPredecessorError,
)
from ibkr_paper_30d.persistence import Database


@pytest.fixture
def database(tmp_path):
    with Database.open(tmp_path / "evidence.sqlite3") as db:
        yield db


@pytest.fixture
def freezer(database):
    return EvidenceFreezer(database)


def test_freeze_commits_and_reads_back_same_hash(freezer) -> None:
    receipt = freezer.freeze({"decision_id": "d1", "value": "x"})

    assert receipt.durable is True
    assert freezer.verify(receipt).valid is True
    assert freezer.read("d1").payload == {"decision_id": "d1", "value": "x"}


def test_frozen_record_cannot_be_overwritten(freezer) -> None:
    freezer.freeze({"decision_id": "d1", "value": "x"})

    with pytest.raises(ImmutableRecordError):
        freezer.freeze({"decision_id": "d1", "value": "y"})


def test_correction_requires_versioned_successor(freezer) -> None:
    freezer.freeze({"decision_id": "d1", "value": "x"})

    successor = freezer.freeze(
        {"decision_id": "d2", "predecessor_id": "d1", "value": "y"}
    )

    assert successor.durable is True
    assert freezer.read("d1").payload["value"] == "x"
    assert freezer.read("d2").payload["value"] == "y"


def test_missing_predecessor_is_rejected(freezer) -> None:
    with pytest.raises(MissingPredecessorError):
        freezer.freeze(
            {"decision_id": "d2", "predecessor_id": "missing", "value": "y"}
        )


@pytest.mark.parametrize("phase", ["BEFORE_COMMIT", "DURING_TRANSACTION"])
def test_crash_before_commit_rolls_back(database, phase) -> None:
    def crash(observed_phase: str) -> None:
        if observed_phase == phase:
            raise RuntimeError(f"crash at {phase}")

    freezer = EvidenceFreezer(database, phase_hook=crash)

    with pytest.raises(RuntimeError, match="crash"):
        freezer.freeze({"decision_id": "d1", "value": "x"})

    assert freezer.exists("d1") is False


def test_crash_after_commit_preserves_record(database) -> None:
    def crash(phase: str) -> None:
        if phase == "AFTER_COMMIT":
            raise RuntimeError("crash after commit")

    freezer = EvidenceFreezer(database, phase_hook=crash)

    with pytest.raises(RuntimeError, match="after commit"):
        freezer.freeze({"decision_id": "d1", "value": "x"})

    stored = freezer.read("d1")
    assert stored.payload["value"] == "x"
    assert freezer.verify(stored.receipt).valid is True


def test_verify_detects_payload_tampering(database, freezer) -> None:
    receipt = freezer.freeze({"decision_id": "d1", "value": "x"})
    database.execute("DROP TRIGGER decision_records_no_update")
    database.execute(
        "UPDATE decision_records SET payload_json='{}' WHERE decision_id='d1'"
    )

    result = freezer.verify(receipt)

    assert result.valid is False
    assert result.reason == "HASH_MISMATCH"
