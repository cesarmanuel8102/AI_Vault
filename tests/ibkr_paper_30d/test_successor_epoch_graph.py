from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.experiment_epoch import (
    EpochError,
    ExperimentEpochStore,
    activation_receipt,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.owner_authorization import OWNER_PHRASE
from ibkr_paper_30d.successor_authorization import create_successor_authorization
from ibkr_paper_30d.successor_clock import (
    BrokerTimeObservation,
    SuccessorClockStore,
    clock_for_epoch,
)
from ibkr_paper_30d.successor_epoch import (
    SUCCESSOR_DEFINITION_SCHEMA,
    SuccessorEpochError,
    SuccessorEpochStore,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

UTC = timezone.utc
START = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
SUCCESSOR_START = datetime(2026, 9, 28, 16, 30, tzinfo=UTC)
HEAD_1 = "1" * 40
HEAD_2 = "2" * 40
OWNER_SHA = "a" * 64
OBJECTIVE_SHA = "b" * 64
CONFIG_SHA = "c" * 64


def _insert_v1_authorization(db: Database) -> None:
    payload = {"actor": "owner", "state": "AUTHORIZED"}
    raw = canonical_bytes(payload).decode("utf-8")
    db.execute(
        "INSERT INTO experiment_authorization_events("
        "event_id,experiment_id,state,clock_event_sha256,payload_json,"
        "payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?)",
        (
            "owner-v1",
            "ibkr-paper-30d",
            "AUTHORIZED",
            "d" * 64,
            raw,
            sha256_json(payload),
            "2026-09-23T13:25:00Z",
        ),
    )


def _root(db: Database) -> tuple[dict[str, object], str]:
    clock = ExperimentClockStore(db).initialize_or_load(
        requested_start_utc=START,
        duration_days=30,
        initial_allocation=Decimal("500"),
    )
    store = ExperimentEpochStore(db)
    preview = store.preview(
        epoch_id="AUTONOMY_EPOCH_1",
        start_utc=START,
        duration_days=30,
        initial_allocation=Decimal("500"),
        approved_git_head=HEAD_1,
        owner_authorization_event_id="owner-v1",
        owner_authorization_receipt_sha256=OWNER_SHA,
        objective_sha256=OBJECTIVE_SHA,
        configuration_sha256=CONFIG_SHA,
    )
    definition = store.define(preview)
    _insert_v1_authorization(db)
    receipt = activation_receipt(
        epoch_id=definition.epoch_id,
        definition_sha256=definition.definition_sha256,
        owner_authorization_event_id="owner-v1",
        approved_git_head=HEAD_1,
        owner_authorization_receipt_sha256=OWNER_SHA,
        issued_at_utc=START - timedelta(minutes=1),
    )
    store.activate(definition.epoch_id, receipt)
    events = EventRepository(db)
    events.append(
        "DAY1_LAUNCH_ATTEMPT_ACCEPTED",
        {"epoch_id": definition.epoch_id, "launch_attempt_id": "attempt-v1"},
    )
    events.append(
        "EPOCH_MANIFEST_CREATED",
        {
            "epoch_id": definition.epoch_id,
            "manifest_sha256": "e" * 64,
            "definition_sha256": definition.definition_sha256,
        },
    )
    return preview, clock.event_sha256


def _preview(
    db: Database,
    *,
    epoch_id: str = "AUTONOMY_EPOCH_2",
    predecessor_epoch_id: str = "AUTONOMY_EPOCH_1",
):
    return SuccessorEpochStore(db).preview(
        epoch_id=epoch_id,
        predecessor_epoch_id=predecessor_epoch_id,
        duration_days=30,
        initial_allocation=Decimal("500"),
        approved_git_head=HEAD_2,
        objective_sha256=OBJECTIVE_SHA,
        configuration_sha256=CONFIG_SHA,
        reason="PRE_START_RUNTIME_FAILURE",
    )


def _event_row(db: Database, event_type: str, epoch_id: str):
    for row in db.execute(
        "SELECT payload_json,event_sha256 FROM state_events "
        "WHERE event_type=? ORDER BY sequence",
        (event_type,),
    ):
        payload = json.loads(str(row[0]))
        if payload.get("epoch_id") == epoch_id:
            return payload, str(row[1])
    raise AssertionError(f"missing {event_type} for {epoch_id}")


def _append_transition(
    db: Database,
    definition: dict[str, object],
    *,
    predecessor_definition_sha256: str | None = None,
    owner_receipt_sha256: str | None = None,
    activation_receipt_sha256: str | None = None,
) -> None:
    db_path = Path(str(db.execute("PRAGMA database_list").fetchone()[2]))
    authorization = create_successor_authorization(
        db_path=db_path,
        receipt_path=db_path.with_name(
            f"{db_path.stem}-{definition['epoch_id']}-owner.json"
        ),
        epoch_id=str(definition["epoch_id"]),
        definition_sha256=str(definition["definition_sha256"]),
        phrase=OWNER_PHRASE,
        actor_sid="S-1-5-21-test-owner",
        elevated=True,
    )
    clock = SuccessorClockStore(db).start(
        epoch_id=str(definition["epoch_id"]),
        definition_sha256=str(definition["definition_sha256"]),
        predecessor_epoch_id=str(definition["predecessor_epoch_id"]),
        predecessor_clock_event_sha256=str(
            definition["predecessor_clock_event_sha256"]
        ),
        observation=BrokerTimeObservation(
            server_time_utc=SUCCESSOR_START,
            observed_at_utc=SUCCESSOR_START + timedelta(seconds=1),
            authenticated=True,
            paper_session=True,
        ),
        duration_days=30,
        initial_allocation=Decimal("500"),
        approved_git_head=HEAD_2,
        owner_authorization_event_id=str(authorization["authorization_event_id"]),
        owner_authorization_receipt_sha256=str(authorization["receipt_sha256"]),
    )
    events = EventRepository(db)
    supersession = {
        "schema": "AUTONOMY_EXPERIMENT_EPOCH_SUPERSESSION_V2",
        "predecessor_epoch_id": definition["predecessor_epoch_id"],
        "predecessor_definition_sha256": predecessor_definition_sha256
        or definition["predecessor_definition_sha256"],
        "predecessor_activation_event_sha256": definition[
            "predecessor_activation_event_sha256"
        ],
        "predecessor_activation_receipt_sha256": definition[
            "predecessor_activation_receipt_sha256"
        ],
        "predecessor_clock_event_sha256": definition["predecessor_clock_event_sha256"],
        "successor_epoch_id": definition["epoch_id"],
        "successor_definition_sha256": definition["definition_sha256"],
        "successor_clock_event_sha256": clock.event_sha256,
        "reason": "PRE_START_RUNTIME_FAILURE",
        "approved_git_head": definition["approved_git_head"],
        "owner_authorization_event_id": authorization["authorization_event_id"],
        "owner_authorization_receipt_sha256": owner_receipt_sha256
        or authorization["receipt_sha256"],
    }
    events.append("EXPERIMENT_EPOCH_SUPERSEDED", supersession)
    supersession_row = db.execute(
        "SELECT event_sha256 FROM state_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    computed_activation_receipt_sha256 = sha256_json(
        {
            "definition_sha256": definition["definition_sha256"],
            "clock_event_sha256": clock.event_sha256,
            "supersession_event_sha256": str(supersession_row[0]),
            "owner_authorization_receipt_sha256": owner_receipt_sha256
            or authorization["receipt_sha256"],
        }
    )
    events.append(
        "EXPERIMENT_EPOCH_ACTIVATED",
        {
            "schema": "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2",
            "epoch_id": definition["epoch_id"],
            "status": "ACTIVE",
            "definition_sha256": definition["definition_sha256"],
            "clock_event_sha256": clock.event_sha256,
            "predecessor_epoch_id": definition["predecessor_epoch_id"],
            "supersession_event_sha256": str(supersession_row[0]),
            "approved_git_head": HEAD_2,
            "owner_authorization_event_id": authorization["authorization_event_id"],
            "owner_authorization_receipt_sha256": owner_receipt_sha256
            or authorization["receipt_sha256"],
            "activation_receipt_sha256": activation_receipt_sha256
            or computed_activation_receipt_sha256,
            "activated_at_utc": "2026-09-28T16:30:00Z",
        },
    )


def test_eligible_successor_definition_binds_full_predecessor_history(tmp_path) -> None:
    with Database.open(tmp_path / "successor.sqlite3") as db:
        root, clock_sha = _root(db)
        install_successor_schema_v2(db)
        before = [tuple(row) for row in db.execute("SELECT * FROM state_events")]

        preview = _preview(db)

        after = [tuple(row) for row in db.execute("SELECT * FROM state_events")]
        current = ExperimentEpochStore(db).current()

    assert preview["schema"] == SUCCESSOR_DEFINITION_SCHEMA
    assert "start_utc" not in preview and "end_utc" not in preview
    assert preview["predecessor_definition_sha256"] == root["definition_sha256"]
    assert preview["predecessor_clock_event_sha256"] == clock_sha
    assert preview["predecessor_manifest_present"] is True
    assert preview["predecessor_manifest_sha256"] == "e" * 64
    assert preview["clock_start_policy"] == "BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH"
    assert preview["history_event_count"] == len(before)
    assert before == after
    assert current is not None and current.epoch_id == "AUTONOMY_EPOCH_1"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("started", "SUCCESSOR_NOT_ALLOWED_AFTER_EPOCH_STARTED"),
        ("write", "SUCCESSOR_BROKER_WRITES_PRESENT"),
        ("position", "SUCCESSOR_OPEN_POSITION_PRESENT"),
        ("order", "SUCCESSOR_OPEN_ORDER_PRESENT"),
        ("cycle", "SUCCESSOR_RUNTIME_ACTIVITY_PRESENT"),
        ("ledger", "SUCCESSOR_RUNTIME_ACTIVITY_PRESENT"),
    ],
)
def test_successor_eligibility_blocks_unsafe_predecessor_state(
    tmp_path, mutation, reason
) -> None:
    with Database.open(tmp_path / f"{mutation}.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        if mutation == "started":
            EventRepository(db).append(
                "EPOCH_STARTED", {"epoch_id": "AUTONOMY_EPOCH_1"}
            )
        elif mutation == "write":
            payload = {"lifecycle_event": "SUBMIT_ATTEMPT"}
            db.execute(
                "INSERT INTO experiment_order_registry(registry_id,order_ref,action,quantity,"
                "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                (
                    "r1",
                    "ref",
                    "BUY",
                    "1",
                    canonical_bytes(payload).decode(),
                    sha256_json(payload),
                    "2026-09-28T00:00:00Z",
                ),
            )
        elif mutation == "position":
            payload = {"positions": [{"account": "DUHASH", "position": "1"}]}
            db.execute(
                "INSERT INTO positions_snapshots(snapshot_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?)",
                (
                    "p1",
                    canonical_bytes(payload).decode(),
                    sha256_json(payload),
                    "2026-09-28T00:00:00Z",
                ),
            )
        elif mutation == "order":
            decision = {"decision": "test"}
            db.execute(
                "INSERT INTO decision_records(decision_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?)",
                (
                    "d1",
                    canonical_bytes(decision).decode(),
                    sha256_json(decision),
                    "2026-09-28T00:00:00Z",
                ),
            )
            db.execute(
                "INSERT INTO orders(order_id,decision_id,idempotency_key,client_order_id,order_ref,status,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                ("o1", "d1", "i1", "c1", "ref1", "Submitted", "2026-09-28T00:00:00Z"),
            )
        elif mutation == "cycle":
            payload = {}
            db.execute(
                "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    "b1",
                    "c1",
                    canonical_bytes(payload).decode(),
                    sha256_json(payload),
                    "2026-09-28T00:00:00Z",
                ),
            )
        else:
            payload = {}
            db.execute(
                "INSERT INTO autonomous_ledger_events(event_id,event_type,payload_json,payload_sha256,event_sha256,created_at_utc) VALUES(?,?,?,?,?,?)",
                (
                    "l1",
                    "TEST",
                    canonical_bytes(payload).decode(),
                    sha256_json(payload),
                    "7" * 64,
                    "2026-09-28T00:00:00Z",
                ),
            )

        with pytest.raises(SuccessorEpochError, match=reason):
            _preview(db)


def test_define_is_clock_free_preserves_v1_bytes_and_does_not_change_current(
    tmp_path,
) -> None:
    with Database.open(tmp_path / "define.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        before = {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            for table in (
                "state_events",
                "experiment_clock_events",
                "experiment_authorization_events",
            )
        }
        definition = SuccessorEpochStore(db).define(_preview(db))

        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2"
            ).fetchone()[0]
            == 0
        )
        assert ExperimentEpochStore(db).current().epoch_id == "AUTONOMY_EPOCH_1"
        assert definition.epoch_id == "AUTONOMY_EPOCH_2"
        after = {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            for table in before
        }
        assert (
            after["state_events"][: len(before["state_events"])]
            == before["state_events"]
        )
        assert after["experiment_clock_events"] == before["experiment_clock_events"]
        assert (
            after["experiment_authorization_events"]
            == before["experiment_authorization_events"]
        )


def test_verified_successor_transition_projects_terminal_not_latest_sequence(
    tmp_path,
) -> None:
    with Database.open(tmp_path / "graph.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        definition = SuccessorEpochStore(db).define(_preview(db))
        payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", definition.epoch_id)
        _append_transition(db, payload)
        EventRepository(db).append(
            "UNRELATED_LATER_EVENT", {"epoch_id": "AUTONOMY_EPOCH_1"}
        )

        current = ExperimentEpochStore(db).current()

    assert current is not None
    assert current.epoch_id == "AUTONOMY_EPOCH_2"
    assert current.start_utc == SUCCESSOR_START


def test_broken_predecessor_binding_blocks_graph_projection(tmp_path) -> None:
    with Database.open(tmp_path / "broken.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        definition = SuccessorEpochStore(db).define(_preview(db))
        payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", definition.epoch_id)
        _append_transition(db, payload, predecessor_definition_sha256="0" * 64)

        with pytest.raises(EpochError, match="SUCCESSOR_PREDECESSOR_HASH_MISMATCH"):
            ExperimentEpochStore(db).current()


@pytest.mark.parametrize(
    "override",
    ["owner_authorization_receipt", "activation_receipt"],
)
def test_broken_successor_authority_binding_blocks_graph_projection(
    tmp_path, override
) -> None:
    with Database.open(tmp_path / f"broken-{override}.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        definition = SuccessorEpochStore(db).define(_preview(db))
        payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", definition.epoch_id)
        _append_transition(
            db,
            payload,
            owner_receipt_sha256=(
                "0" * 64 if override == "owner_authorization_receipt" else None
            ),
            activation_receipt_sha256=(
                "0" * 64 if override == "activation_receipt" else None
            ),
        )

        with pytest.raises(EpochError, match="SUCCESSOR_CHAIN_INVALID"):
            ExperimentEpochStore(db).current()


def test_independent_v2_activation_blocks_graph_projection(tmp_path) -> None:
    with Database.open(tmp_path / "independent.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        EventRepository(db).append(
            "EXPERIMENT_EPOCH_ACTIVATED",
            {
                "schema": "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2",
                "epoch_id": "AUTONOMY_EPOCH_X",
                "definition_sha256": "0" * 64,
                "supersession_event_sha256": "1" * 64,
            },
        )

        with pytest.raises(EpochError, match="SUCCESSOR_CHAIN_INVALID"):
            ExperimentEpochStore(db).current()


def test_activation_without_supersession_edge_blocks_graph_projection(tmp_path) -> None:
    with Database.open(tmp_path / "missing-edge.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        definition = SuccessorEpochStore(db).define(_preview(db))
        payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", definition.epoch_id)
        clock = SuccessorClockStore(db).start(
            epoch_id=definition.epoch_id,
            definition_sha256=definition.definition_sha256,
            predecessor_epoch_id="AUTONOMY_EPOCH_1",
            predecessor_clock_event_sha256=str(
                payload["predecessor_clock_event_sha256"]
            ),
            observation=BrokerTimeObservation(
                server_time_utc=SUCCESSOR_START,
                observed_at_utc=SUCCESSOR_START + timedelta(seconds=1),
                authenticated=True,
                paper_session=True,
            ),
            duration_days=30,
            initial_allocation=Decimal("500"),
            approved_git_head=HEAD_2,
            owner_authorization_event_id="owner-v2",
            owner_authorization_receipt_sha256="f" * 64,
        )
        EventRepository(db).append(
            "EXPERIMENT_EPOCH_ACTIVATED",
            {
                "schema": "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2",
                "epoch_id": definition.epoch_id,
                "definition_sha256": definition.definition_sha256,
                "clock_event_sha256": clock.event_sha256,
                "supersession_event_sha256": "1" * 64,
            },
        )

        with pytest.raises(EpochError, match="SUCCESSOR_CHAIN_INVALID"):
            ExperimentEpochStore(db).current()


def test_branching_supersession_edges_block_graph_projection(tmp_path) -> None:
    with Database.open(tmp_path / "branch.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        definition = SuccessorEpochStore(db).define(_preview(db))
        payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", definition.epoch_id)
        _append_transition(db, payload)
        EventRepository(db).append(
            "EXPERIMENT_EPOCH_SUPERSEDED",
            {
                "schema": "AUTONOMY_EXPERIMENT_EPOCH_SUPERSESSION_V2",
                "predecessor_epoch_id": "AUTONOMY_EPOCH_1",
                "successor_epoch_id": "AUTONOMY_EPOCH_BRANCH",
            },
        )

        with pytest.raises(EpochError, match="SUCCESSOR_CHAIN_INVALID"):
            ExperimentEpochStore(db).current()


def test_repeated_explicit_successor_chaining_reaches_one_terminal(tmp_path) -> None:
    with Database.open(tmp_path / "chain.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        second = SuccessorEpochStore(db).define(_preview(db))
        second_payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", second.epoch_id)
        _append_transition(db, second_payload)

        third = SuccessorEpochStore(db).define(
            _preview(
                db,
                epoch_id="AUTONOMY_EPOCH_3",
                predecessor_epoch_id="AUTONOMY_EPOCH_2",
            )
        )
        third_payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", third.epoch_id)
        _append_transition(db, third_payload)

        current = ExperimentEpochStore(db).current()

    assert current is not None and current.epoch_id == "AUTONOMY_EPOCH_3"


def test_next_successor_binds_v2_epoch_manifest_hash(tmp_path) -> None:
    with Database.open(tmp_path / "v2-manifest-chain.sqlite3") as db:
        _root(db)
        install_successor_schema_v2(db)
        second = SuccessorEpochStore(db).define(_preview(db))
        second_payload, _ = _event_row(db, "EXPERIMENT_EPOCH_DEFINED", second.epoch_id)
        _append_transition(db, second_payload)
        EventRepository(db).append(
            "EPOCH_MANIFEST_CREATED",
            {
                "schema": "EPOCH_MANIFEST_CREATED_V1",
                "epoch_id": second.epoch_id,
                "definition_sha256": second.definition_sha256,
                "clock_event_sha256": clock_for_epoch(db, second.epoch_id).event_sha256,
                "epoch_manifest_sha256": "f" * 64,
            },
        )

        third = _preview(
            db,
            epoch_id="AUTONOMY_EPOCH_3",
            predecessor_epoch_id=second.epoch_id,
        )

    assert third["predecessor_manifest_present"] is True
    assert third["predecessor_manifest_sha256"] == "f" * 64
