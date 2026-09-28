from __future__ import annotations

import os
import socket
import threading
import json
from datetime import datetime, timedelta, timezone

import pytest

if os.name != "nt":
    pytest.skip(
        "Windows named-mutex execution lock tests",
        allow_module_level=True,
    )

from ibkr_paper_30d.execution_lock import (
    ExecutionLock,
    LockIntegrityError,
    LockOwner,
    ObservedProcess,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
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


NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class Observer:
    def __init__(
        self,
        observed: ObservedProcess | None,
        *,
        active_authority: bool | None = False,
        boot_session_id: str = "boot-test",
    ) -> None:
        self.observed = observed
        self.active_authority = active_authority
        self.boot_session_id = boot_session_id

    def observe(self, pid: int):
        assert pid > 0
        return self.observed

    def has_other_execution_authority(self, *, excluding_pid: int):
        return self.active_authority

    def current_boot_session_id(self):
        return self.boot_session_id


def seed_active_lock(
    db: Database,
    *,
    stale_owner: LockOwner,
    heartbeat_at: datetime,
    generation: int = 11,
    order_authority: bool = False,
) -> None:
    payload = {
        "state": "ACTIVE",
        **stale_owner.model_dump(),
        "generation": generation,
        "acquired_at_utc": heartbeat_at.isoformat().replace("+00:00", "Z"),
        "heartbeat_at_utc": heartbeat_at.isoformat().replace("+00:00", "Z"),
        "order_authority": order_authority,
    }
    db.execute(
        "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
        "VALUES(?,?,?,?,?)",
        (
            "EXECUTION_LOCK_V1",
            1,
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            heartbeat_at.isoformat().replace("+00:00", "Z"),
        ),
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


def test_legacy_recovery_api_cannot_mutate_without_full_inspection(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        lock = ExecutionLock(db, mutex_name=rf"Local\Test-{new_uuid7()}")
        stale = owner(pid=100, start="A")

        result = lock.recover_stale(stale, observed=None, mutex_is_free=True)

        assert result.state == "EXECUTION_LOCK_AMBIGUOUS"
        assert result.recovered is False
        assert result.order_authority is False
        assert result.reason == "LEGACY_RECOVERY_API_DISABLED"


def test_active_database_owner_blocks_even_when_mutex_is_free(tmp_path) -> None:
    path = tmp_path / "lock.sqlite3"
    name = rf"Local\CodexIbkrPaperTest-{new_uuid7()}"
    with Database.open(path) as db:
        projection = {
            "state": "ACTIVE",
            "owner_id": "stale-owner",
            "pid": 999999,
            "process_start": "old",
            "generation": 1,
        }
        payload = json.dumps(projection, sort_keys=True)
        db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES('EXECUTION_LOCK_V1',1,?,?,'2026-09-20T00:00:00Z')",
            (payload, sha256_json(projection)),
        )

    with Database.open(path) as db:
        second = ExecutionLock(db, mutex_name=name).acquire(
            owner(os.getpid(), "second")
        )

    assert second.acquired is False
    assert second.reason == "LOCK_STATE_AMBIGUOUS"
    assert second.recovery_required is True


def test_wrong_owner_cannot_heartbeat_or_release(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        lock = ExecutionLock(db, mutex_name=rf"Local\Test-{new_uuid7()}")
        receipt = lock.acquire(owner(os.getpid(), "first"))
        forged = receipt.model_copy(update={"owner_id": "forged"})

        assert lock.heartbeat(forged).accepted is False
        assert lock.release(forged).released is False
        assert lock.release(receipt).released is True


def test_dead_pid_and_stale_heartbeat_recover_and_acquire_new_generation(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "2026-09-20T00:00:00Z", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "2026-09-27T11:59:00Z", "new"))

        assert receipt.acquired is True
        assert receipt.generation == 12
        events = [row[0] for row in db.execute(
            "SELECT event_type FROM execution_lock_events ORDER BY sequence"
        ).fetchall()]
        assert events == ["STALE_OWNER_RECOVERED", "ACQUIRED"]
        assert lock.release(receipt).released is True


def test_fresh_heartbeat_with_dead_pid_is_ambiguous(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "2026-09-27T11:59:00Z", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(seconds=20))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is False
        assert receipt.reason == "LOCK_STATE_AMBIGUOUS"
        assert receipt.recovery_required is True


def test_pid_reused_by_unrelated_process_is_safely_recoverable(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(4242, "2026-09-20T00:00:00Z", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        observed = ObservedProcess(
            pid=4242,
            process_start="2026-09-27T10:00:00Z",
            host_fingerprint=stale.host_fingerprint,
            boot_session_id=stale.boot_session_id,
        )
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(observed),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is True
        assert receipt.generation == 12
        assert lock.release(receipt).released is True


@pytest.mark.parametrize("active_authority", [True, None])
def test_recovery_blocks_when_execution_authority_scan_is_positive_or_ambiguous(
    tmp_path, active_authority
) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "old", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None, active_authority=active_authority),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is False
        assert receipt.reason == "LOCK_STATE_AMBIGUOUS"


def test_reboot_identity_allows_stale_dead_owner_recovery(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(4242, "old", "stale").model_copy(update={"boot_session_id": "old-boot"})
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(days=1))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None, boot_session_id="new-boot"),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is True
        assert lock.release(receipt).released is True


def test_recovery_transaction_rolls_back_if_event_append_is_interrupted(tmp_path, monkeypatch) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "old", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )
        original = lock._append_event

        def interrupted(generation, event_type, payload):
            if event_type == "ACQUIRED":
                raise RuntimeError("simulated crash")
            return original(generation, event_type, payload)

        monkeypatch.setattr(lock, "_append_event", interrupted)

        with pytest.raises(RuntimeError, match="simulated crash"):
            lock.acquire(owner(os.getpid(), "new", "new"))

        projection = lock._projection()
        assert projection is not None
        assert projection[1]["owner_id"] == "stale"
        assert db.execute("SELECT COUNT(*) FROM execution_lock_events").fetchone()[0] == 0


def test_old_generation_cannot_heartbeat_after_recovery(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "old", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )
        replacement = lock.acquire(owner(os.getpid(), "new", "new"))
        old_receipt = replacement.model_copy(update={"owner_id": "stale", "generation": 11})

        assert lock.heartbeat(old_receipt).accepted is False
        assert lock.release(replacement).released is True


def test_live_recorded_owner_with_free_mutex_is_ambiguous(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(4242, "2026-09-20T00:00:00Z", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))
        observed = ObservedProcess(**stale.model_dump(exclude={"owner_id"}))
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(observed),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is False
        assert receipt.reason == "LOCK_STATE_AMBIGUOUS"


def test_stale_projection_with_order_authority_never_auto_recovers(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        stale = owner(999999, "old", "stale")
        seed_active_lock(
            db,
            stale_owner=stale,
            heartbeat_at=NOW - timedelta(minutes=10),
            order_authority=True,
        )
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is False
        assert receipt.reason == "LOCK_STATE_AMBIGUOUS"


def test_two_recovery_contenders_produce_only_one_new_generation(tmp_path) -> None:
    path = tmp_path / "lock.sqlite3"
    mutex_name = rf"Local\Test-{new_uuid7()}"
    with Database.open(path) as db:
        stale = owner(999999, "old", "stale")
        seed_active_lock(db, stale_owner=stale, heartbeat_at=NOW - timedelta(minutes=10))

    barrier = threading.Barrier(2)
    release_winner = threading.Event()
    results = []

    def contend(index: int) -> None:
        with Database.open(path) as db:
            lock = ExecutionLock(
                db,
                mutex_name=mutex_name,
                process_observer=Observer(None),
                now_utc=lambda: NOW,
            )
            barrier.wait(timeout=5)
            receipt = lock.acquire(owner(os.getpid(), f"new-{index}", f"new-{index}"))
            results.append(receipt)
            if receipt.acquired:
                release_winner.wait(timeout=5)
                lock.release(receipt)

    threads = [threading.Thread(target=contend, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    while len(results) < 2 and any(thread.is_alive() for thread in threads):
        threading.Event().wait(0.01)
    release_winner.set()
    for thread in threads:
        thread.join(timeout=5)

    assert sum(receipt.acquired for receipt in results) == 1
    assert sorted(receipt.generation for receipt in results) == [0, 12]
    with Database.open(path) as db:
        acquired = db.execute(
            "SELECT COUNT(*) FROM execution_lock_events WHERE event_type='ACQUIRED' AND generation=12"
        ).fetchone()[0]
    assert acquired == 1


def test_recovery_refuses_projection_with_invalid_hash(tmp_path) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        payload = {
            "state": "ACTIVE",
            **owner(999999, "old", "stale").model_dump(),
            "generation": 11,
            "heartbeat_at_utc": "2026-09-20T00:00:00Z",
            "order_authority": False,
        }
        db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES(?,?,?,?,?)",
            (
                "EXECUTION_LOCK_V1",
                1,
                canonical_bytes(payload).decode("utf-8"),
                "0" * 64,
                "2026-09-20T00:00:00Z",
            ),
        )
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )

        with pytest.raises(LockIntegrityError, match="projection hash"):
            lock.acquire(owner(os.getpid(), "new", "new"))


@pytest.mark.parametrize("state", ["RECOVERY_REQUIRED", "UNKNOWN"])
def test_nonterminal_nonactive_projection_never_grants_a_new_generation(
    tmp_path, state
) -> None:
    with Database.open(tmp_path / "lock.sqlite3") as db:
        payload = {
            "state": state,
            "generation": 11,
            "order_authority": False,
        }
        db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES(?,?,?,?,?)",
            (
                "EXECUTION_LOCK_V1",
                1,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                "2026-09-20T00:00:00Z",
            ),
        )
        lock = ExecutionLock(
            db,
            mutex_name=rf"Local\Test-{new_uuid7()}",
            process_observer=Observer(None),
            now_utc=lambda: NOW,
        )

        receipt = lock.acquire(owner(os.getpid(), "new", "new"))

        assert receipt.acquired is False
        assert receipt.reason == "LOCK_STATE_AMBIGUOUS"
