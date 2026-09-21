from __future__ import annotations

import os
import socket
import threading
import json

import pytest

if os.name != "nt":
    pytest.skip(
        "Windows named-mutex execution lock tests",
        allow_module_level=True,
    )

from ibkr_paper_30d.execution_lock import ExecutionLock, LockOwner
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.types import new_uuid7


def owner(pid: int, start: str, owner_id: str | None = None) -> LockOwner:
    return LockOwner(
        owner_id=owner_id or str(new_uuid7()),
        pid=pid,
        process_start=start,
        host_fingerprint=socket.gethostname(),
        boot_session_id="boot-test",
    )


def test_second_thread_cannot_acquire_same_named_mutex(tmp_path) -> None:
    path = tmp_path / "lock.sqlite3"
    name = rf"Local\CodexIbkrPaperTest-{new_uuid7()}"
    with Database.open(path) as first_db:
        first_lock = ExecutionLock(first_db, mutex_name=name)
        first = first_lock.acquire(owner(os.getpid(), "first"))
        result = []

        def contend() -> None:
            with Database.open(path) as second_db:
                result.append(
                    ExecutionLock(second_db, mutex_name=name).acquire(
                        owner(os.getpid(), "second")
                    )
                )

        thread = threading.Thread(target=contend)
        thread.start()
        thread.join(timeout=5)

        assert first.acquired is True
        assert result[0].acquired is False
        assert result[0].reason == "OS_MUTEX_HELD"
        first_lock.release(first)


def test_clean_release_allows_next_generation(tmp_path) -> None:
    path = tmp_path / "lock.sqlite3"
    name = rf"Local\CodexIbkrPaperTest-{new_uuid7()}"
    with Database.open(path) as db:
        lock = ExecutionLock(db, mutex_name=name)
        first = lock.acquire(owner(os.getpid(), "first"))
        assert lock.release(first).released is True
        second = lock.acquire(owner(os.getpid(), "second"))

        assert second.acquired is True
        assert second.generation == first.generation + 1
        lock.release(second)


def test_pid_reuse_does_not_prove_same_owner(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        lock = ExecutionLock(db, mutex_name=rf"Local\Test-{new_uuid7()}")
        stale = owner(pid=100, start="A")
        observed = owner(pid=100, start="B")

        result = lock.recover_stale(stale, observed, mutex_is_free=True)

        assert result.state == "EXECUTION_LOCK_AMBIGUOUS"
        assert result.recovered is False


def test_confirmed_dead_owner_enters_recovery_without_authority(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        lock = ExecutionLock(db, mutex_name=rf"Local\Test-{new_uuid7()}")
        stale = owner(pid=100, start="A")

        result = lock.recover_stale(stale, observed=None, mutex_is_free=True)

        assert result.state == "SYSTEM_RECOVERING"
        assert result.recovered is True
        assert result.order_authority is False


def test_active_database_owner_blocks_even_when_mutex_is_free(tmp_path) -> None:
    path = tmp_path / "lock.sqlite3"
    name = rf"Local\CodexIbkrPaperTest-{new_uuid7()}"
    with Database.open(path) as db:
        payload = json.dumps(
            {
                "state": "ACTIVE",
                "owner_id": "stale-owner",
                "pid": 999999,
                "process_start": "old",
                "generation": 1,
            },
            sort_keys=True,
        )
        db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES('EXECUTION_LOCK_V1',1,?,'fixture','2026-09-20T00:00:00Z')",
            (payload,),
        )

    with Database.open(path) as db:
        second = ExecutionLock(db, mutex_name=name).acquire(
            owner(os.getpid(), "second")
        )

    assert second.acquired is False
    assert second.reason == "LOCK_RECORD_ACTIVE"
    assert second.recovery_required is True


def test_wrong_owner_cannot_heartbeat_or_release(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        lock = ExecutionLock(db, mutex_name=rf"Local\Test-{new_uuid7()}")
        receipt = lock.acquire(owner(os.getpid(), "first"))
        forged = receipt.model_copy(update={"owner_id": "forged"})

        assert lock.heartbeat(forged).accepted is False
        assert lock.release(forged).released is False
        assert lock.release(receipt).released is True
