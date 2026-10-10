from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.experiment_epoch import ExperimentEpochStore
from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.multi_universe_transition import MultiUniverseTransitionCoordinator
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.successor_authorization import revoke_successor_authorization
from ibkr_paper_30d.successor_clock import BrokerTimeObservation
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    SuccessorEpochError,
    commit_successor_transition,
)
from successor_test_support import (
    ACCOUNT_HASH,
    OWNER_SID,
    SUCCESSOR_START,
    build_authorized_successor,
)


def _evidence(*, collected_at=SUCCESSOR_START + timedelta(seconds=1)):
    return BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=collected_at,
        observation=BrokerTimeObservation(
            server_time_utc=SUCCESSOR_START,
            observed_at_utc=collected_at,
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=0,
    )


def _setup(tmp_path):
    db_path = tmp_path / "transition.sqlite3"
    receipt_path = tmp_path / "owner-v2.json"
    definition, receipt = build_authorized_successor(db_path, receipt_path)
    return db_path, definition, receipt


def _commit(db, definition, receipt, **overrides):
    values = {
        "db": db,
        "launch_attempt_id": "launch-attempt-1",
        "target_successor_epoch_id": definition["epoch_id"],
        "target_successor_definition_sha256": definition["definition_sha256"],
        "expected_account_identity_sha256": ACCOUNT_HASH,
        "expected_owner_sid": OWNER_SID,
        "owner_authorization_receipt": receipt,
        "execution_lock_verifier": lambda: True,
        "broker_evidence_collector": lambda: _evidence(),
        "now_utc": lambda: SUCCESSOR_START + timedelta(seconds=2),
    }
    values.update(overrides)
    return commit_successor_transition(**values)


def _transition_evidence(phase: TransitionPhase) -> dict[str, object]:
    result: dict[str, object] = {
        "phase_evidence_sha256": sha256_json({"phase": phase.value}),
        "canary_flat": True,
        "continuity_exact": True,
        "broker_write_count": 0,
    }
    if phase is TransitionPhase.CANARY_PASS:
        result["canary_status"] = "PASS"
    if phase is TransitionPhase.PREDECESSOR_RETIRED:
        result["retirement_status"] = "PASS"
        result["retirement_tombstone_sha256"] = "f" * 64
    return result


def test_atomic_transition_writes_one_clock_supersession_and_activation(
    tmp_path,
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    with Database.open(db_path) as db:
        result = _commit(db, definition, receipt)
        current = ExperimentEpochStore(db).current()
        clock_payload = db.execute(
            "SELECT payload_json FROM experiment_epoch_clock_events_v2"
        ).fetchone()[0]
        supersession = db.execute(
            "SELECT payload_json,event_sha256 FROM state_events "
            "WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
        ).fetchone()
        activation = db.execute(
            "SELECT payload_json FROM state_events WHERE event_type='EXPERIMENT_EPOCH_ACTIVATED' "
            "AND json_extract(payload_json,'$.schema')='AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2'"
        ).fetchone()[0]

    import json

    clock_payload = json.loads(clock_payload)
    supersession_payload = json.loads(supersession[0])
    activation_payload = json.loads(activation)
    assert result.idempotent is False
    assert current is not None and current.epoch_id == "AUTONOMY_EPOCH_2"
    assert clock_payload["broker_evidence_sha256"] == result.broker_evidence_sha256
    assert clock_payload["launch_attempt_id"] == "launch-attempt-1"
    assert (
        supersession_payload["successor_clock_event_sha256"]
        == result.clock_event_sha256
    )
    assert activation_payload["supersession_event_sha256"] == supersession[1]
    assert (
        activation_payload["owner_authorization_receipt_sha256"]
        == receipt["receipt_sha256"]
    )
    with Database.open(db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 1
        )


def test_broker_collector_runs_after_lock_check_and_before_begin_immediate(
    tmp_path,
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    order = []
    with Database.open(db_path) as db:

        def lock_verifier():
            order.append(("lock", db.connection.in_transaction))
            return True

        def collect():
            order.append(("broker", db.connection.in_transaction))
            return _evidence()

        _commit(
            db,
            definition,
            receipt,
            execution_lock_verifier=lock_verifier,
            broker_evidence_collector=collect,
        )

    assert order[0] == ("lock", False)
    assert order[1] == ("broker", False)
    assert all(not in_transaction for _, in_transaction in order[:2])


def test_successor_commit_requires_exact_predecessor_retirement_when_v4_bound(
    tmp_path,
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    with Database.open(db_path) as db:
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        target = TransitionTarget(
            transition_id="successor-transition-v4",
            predecessor_epoch_id=definition["predecessor_epoch_id"],
            successor_epoch_id=definition["epoch_id"],
            successor_definition_sha256=definition["definition_sha256"],
            owner_authorization_sha256=receipt["receipt_sha256"],
            approved_git_head=definition["approved_git_head"],
            account_identity_sha256=ACCOUNT_HASH,
            clock_authority_sha256="1" * 64,
            regular_sleeve_authority_sha256="2" * 64,
            extended_sleeve_authority_sha256="3" * 64,
            economic_risk_authorization_sha256="4" * 64,
            certified_family_set_sha256="5" * 64,
            canary_authorization_sha256="6" * 64,
            writer_binding_sha256="7" * 64,
        )
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(target)

        with pytest.raises(SuccessorEpochError, match="RETIREMENT_NOT_PROVEN"):
            _commit(
                db,
                definition,
                receipt,
                multi_universe_transition_id=target.transition_id,
                multi_universe_target_sha256=target.sha256,
            )
        for phase in (
            TransitionPhase.PREDECESSOR_QUIESCED,
            TransitionPhase.CANARY_EXCLUSIVE,
            TransitionPhase.CANARY_PASS,
            TransitionPhase.PREDECESSOR_RETIRED,
        ):
            coordinator.advance(phase, _transition_evidence(phase))

        result = _commit(
            db,
            definition,
            receipt,
            multi_universe_transition_id=target.transition_id,
            multi_universe_target_sha256=target.sha256,
        )

    assert result.epoch_id == definition["epoch_id"]


@pytest.mark.parametrize(
    "mutation", ["started", "runtime", "revoked", "duplicate_definition"]
)
def test_database_changes_after_broker_collection_block_inside_transaction(
    tmp_path, mutation
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    with Database.open(db_path) as db:

        def mutate(_evidence):
            if mutation == "started":
                EventRepository(db).append(
                    "EPOCH_STARTED", {"epoch_id": "AUTONOMY_EPOCH_1"}
                )
            elif mutation == "runtime":
                payload = {}
                db.execute(
                    "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
                    (
                        "late",
                        "late",
                        canonical_bytes(payload).decode(),
                        sha256_json(payload),
                        "2026-09-28T16:30:01Z",
                    ),
                )
            elif mutation == "revoked":
                revoke_successor_authorization(
                    db_path=db_path,
                    epoch_id="AUTONOMY_EPOCH_2",
                    definition_sha256=definition["definition_sha256"],
                    actor_sid=OWNER_SID,
                )
            else:
                EventRepository(db).append("EXPERIMENT_EPOCH_DEFINED", definition)

        with pytest.raises(SuccessorEpochError):
            _commit(db, definition, receipt, after_evidence_collected=mutate)
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 0
        )


def test_broker_evidence_that_becomes_stale_before_commit_rolls_back(tmp_path) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    calls = [0]

    def advancing_now():
        calls[0] += 1
        if calls[0] < 4:
            return SUCCESSOR_START + timedelta(seconds=2)
        return SUCCESSOR_START + timedelta(minutes=2)

    with Database.open(db_path) as db:
        with pytest.raises(SuccessorEpochError, match="BROKER_EVIDENCE_STALE"):
            _commit(
                db,
                definition,
                receipt,
                now_utc=advancing_now,
            )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("write_number", [1, 2, 3])
def test_failure_at_each_transition_write_boundary_rolls_back(
    tmp_path, write_number
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    with Database.open(db_path) as db:
        original = db.execute
        writes = [0]

        def interrupted(sql, parameters=()):
            if sql.lstrip().startswith(
                "INSERT INTO experiment_epoch_clock_events_v2"
            ) or (
                sql.lstrip().startswith("INSERT INTO state_events")
                and db.connection.in_transaction
            ):
                writes[0] += 1
                if writes[0] == write_number:
                    raise RuntimeError("injected transition write failure")
            return original(sql, parameters)

        db.execute = interrupted
        with pytest.raises(RuntimeError, match="injected"):
            _commit(db, definition, receipt)
        db.execute = original
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE json_extract(payload_json,'$.schema')='AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2'"
            ).fetchone()[0]
            == 0
        )


def test_same_target_concurrent_contenders_create_exactly_one_transition(
    tmp_path,
) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def contender():
        try:
            with Database.open(db_path) as db:
                result = _commit(
                    db,
                    definition,
                    receipt,
                    after_evidence_collected=lambda _evidence: barrier.wait(),
                )
                results.append(result)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert len(results) == 2
    assert sum(not result.idempotent for result in results) == 1
    assert sum(result.idempotent for result in results) == 1
    with Database.open(db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_EPOCH_SUPERSEDED'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE json_extract(payload_json,'$.schema')='AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2'"
            ).fetchone()[0]
            == 1
        )


def test_different_target_cannot_become_idempotent_success(tmp_path) -> None:
    db_path, definition, receipt = _setup(tmp_path)
    with Database.open(db_path) as db:
        _commit(db, definition, receipt)
        with pytest.raises(SuccessorEpochError):
            commit_successor_transition(
                db=db,
                launch_attempt_id="different",
                target_successor_epoch_id="AUTONOMY_EPOCH_3",
                target_successor_definition_sha256="0" * 64,
                expected_account_identity_sha256=ACCOUNT_HASH,
                expected_owner_sid=OWNER_SID,
                owner_authorization_receipt=receipt,
                execution_lock_verifier=lambda: True,
                broker_evidence_collector=lambda: _evidence(),
                now_utc=lambda: SUCCESSOR_START + timedelta(seconds=2),
            )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 1
        )
