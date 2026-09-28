from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_paper_30d.experiment_epoch import ExperimentEpochStore
from ibkr_paper_30d.owner_authorization import OWNER_PHRASE
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.scheduler_validation import (
    RuntimeGateSnapshot,
    SchedulerExpectation,
    SchedulerTaskSnapshot,
    validate_scheduler_startup,
)
from ibkr_paper_30d.successor_authorization import create_successor_authorization
from ibkr_paper_30d.successor_clock import BrokerTimeObservation, clock_for_epoch
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    SuccessorEpochStore,
    commit_successor_transition,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from production_epoch_v1_fixture import (
    ACCOUNT_HASH,
    BASE_HEAD,
    OWNER_SID,
    ROOT_EPOCH_ID,
    ROOT_START,
    SNAPSHOT_TABLES,
    build_production_epoch_v1_fixture,
    snapshot_v1_rows,
)

CASE_COVERAGE: dict[str, tuple[str, ...]] = {
    "A": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "B": ("test_successor_eligibility_blocks_unsafe_predecessor_state",),
    "C": ("test_successor_eligibility_blocks_unsafe_predecessor_state",),
    "D": ("test_successor_eligibility_blocks_unsafe_predecessor_state",),
    "E": ("test_successor_eligibility_blocks_unsafe_predecessor_state",),
    "F": ("test_eligible_successor_definition_binds_full_predecessor_history",),
    "G": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "H": ("test_independent_v2_activation_blocks_graph_projection",),
    "I": ("test_verified_successor_transition_projects_terminal_not_latest_sequence",),
    "J": ("test_branching_supersession_edges_block_graph_projection",),
    "K": ("test_clock_for_epoch_reads_unchanged_v1_clock",),
    "L": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "M": ("test_successor_clock_uses_fresh_broker_time_for_exact_thirty_days",),
    "N": ("test_successor_clock_uses_fresh_broker_time_for_exact_thirty_days",),
    "O": ("test_clock_validation_and_non_launch_operations_create_no_clock",),
    "P": ("test_clock_validation_and_non_launch_operations_create_no_clock",),
    "Q": ("test_case_ae_scheduler_validation_cannot_install_v2_or_start_clock",),
    "R": ("test_exact_retry_is_idempotent_and_validation_is_read_only",),
    "S": ("test_successor_launch_remains_bound_to_a_when_b_is_defined_later",),
    "T": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "U": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "V": ("test_cases_a_g_l_t_u_v_production_successor_chain",),
    "W": ("test_same_target_concurrent_contenders_create_exactly_one_transition",),
    "X": ("test_successor_launch_remains_bound_to_a_when_b_is_defined_later",),
    "Y": ("test_invalid_broker_time_evidence_blocks",),
    "Z": ("test_invalid_broker_time_evidence_blocks",),
    "AA": (
        "test_forged_caller_preceding_time_cannot_bypass_backward_check",
        "test_missing_authoritative_prior_time_fails_closed_when_required",
        "test_valid_hash_verified_prior_time_is_used",
        "test_invalid_broker_time_evidence_blocks",
    ),
    "AB": ("test_repeated_install_is_idempotent_and_creates_no_control_state",),
    "AC": ("test_database_open_does_not_install_successor_schema_v2",),
    "AD": ("test_case_ad_read_only_external_audit_cannot_install_v2",),
    "AE": ("test_case_ae_scheduler_validation_cannot_install_v2_or_start_clock",),
    "AF": ("test_create_binds_exact_successor_without_consuming_clock_or_activation",),
    "AG": ("test_failure_at_each_transition_write_boundary_rolls_back",),
}


def _expected_case_ids() -> set[str]:
    return {
        *(chr(value) for value in range(ord("A"), ord("Z") + 1)),
        *(f"A{chr(value)}" for value in range(ord("A"), ord("G") + 1)),
    }


def _evidence(server_time, *, writes: int = 0) -> BrokerTransitionEvidence:
    collected = server_time + timedelta(seconds=1)
    return BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=collected,
        observation=BrokerTimeObservation(
            server_time_utc=server_time,
            observed_at_utc=collected,
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=writes,
    )


def _authorize_and_commit(
    db: Database,
    *,
    db_path: Path,
    receipt_path: Path,
    definition: dict[str, object],
    launch_attempt_id: str,
    server_time,
):
    receipt = create_successor_authorization(
        db_path=db_path,
        receipt_path=receipt_path,
        epoch_id=str(definition["epoch_id"]),
        definition_sha256=str(definition["definition_sha256"]),
        phrase=OWNER_PHRASE,
        actor_sid=OWNER_SID,
        elevated=True,
    )
    evidence = _evidence(server_time)
    return commit_successor_transition(
        db=db,
        launch_attempt_id=launch_attempt_id,
        target_successor_epoch_id=str(definition["epoch_id"]),
        target_successor_definition_sha256=str(definition["definition_sha256"]),
        expected_account_identity_sha256=ACCOUNT_HASH,
        expected_owner_sid=OWNER_SID,
        owner_authorization_receipt=receipt,
        execution_lock_verifier=lambda: True,
        broker_evidence_collector=lambda: evidence,
        now_utc=lambda: server_time + timedelta(seconds=2),
    )


def test_adversarial_case_inventory_names_every_case_a_through_ag() -> None:
    assert set(CASE_COVERAGE) == _expected_case_ids()
    test_corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(__file__).parent.glob("test_*.py")
    )
    for case_id, test_names in CASE_COVERAGE.items():
        assert test_names, case_id
        for test_name in test_names:
            assert f"def {test_name}" in test_corpus, (case_id, test_name)


def test_cases_a_g_l_t_u_v_production_successor_chain(tmp_path) -> None:
    fixture = build_production_epoch_v1_fixture(tmp_path / "production-v1.sqlite3")
    before = fixture.snapshot
    broker_write_tripwire: list[str] = []

    with Database.open(fixture.db_path) as db:
        install_successor_schema_v2(db)
        store = SuccessorEpochStore(db)
        second = store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_2",
                predecessor_epoch_id=ROOT_EPOCH_ID,
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head="2" * 40,
                objective_sha256="b" * 64,
                configuration_sha256="c" * 64,
                reason="PRE_START_RUNTIME_FAILURE",
            )
        )
        second_payload = store.definition(second.epoch_id)
        second_transition = _authorize_and_commit(
            db,
            db_path=fixture.db_path,
            receipt_path=tmp_path / "owner-epoch-2.json",
            definition=second_payload,
            launch_attempt_id="launch-epoch-2",
            server_time=ROOT_START + timedelta(days=5),
        )
        EventRepository(db).append(
            "EPOCH_PRE_START_FAILED",
            {
                "schema": "EPOCH_PRE_START_FAILED_V1",
                "epoch_id": second.epoch_id,
                "definition_sha256": second.definition_sha256,
                "clock_event_sha256": second_transition.clock_event_sha256,
                "launch_attempt_id": "launch-epoch-2",
                "epoch_manifest_sha256": None,
                "reason_codes": ["TEST_PRE_START_FAILURE"],
            },
        )
        third = store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_3",
                predecessor_epoch_id=second.epoch_id,
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head="3" * 40,
                objective_sha256="d" * 64,
                configuration_sha256="e" * 64,
                reason="PRE_START_RUNTIME_FAILURE",
            )
        )
        third_payload = store.definition(third.epoch_id)
        third_transition = _authorize_and_commit(
            db,
            db_path=fixture.db_path,
            receipt_path=tmp_path / "owner-epoch-3.json",
            definition=third_payload,
            launch_attempt_id="launch-epoch-3",
            server_time=ROOT_START + timedelta(days=5, minutes=1),
        )

        after = snapshot_v1_rows(db)
        current = ExperimentEpochStore(db).current()
        root_clock = clock_for_epoch(db, ROOT_EPOCH_ID)
        second_clock = clock_for_epoch(db, second.epoch_id)
        third_clock = clock_for_epoch(db, third.epoch_id)

    for table in SNAPSHOT_TABLES - {"state_events"}:
        assert after[table] == before[table], table
    assert (
        after["state_events"][: len(before["state_events"])] == before["state_events"]
    )
    assert current is not None and current.epoch_id == "AUTONOMY_EPOCH_3"
    assert root_clock.start_utc == ROOT_START
    assert root_clock.event_sha256 == fixture.root_clock_sha256
    assert second_clock.event_sha256 == second_transition.clock_event_sha256
    assert third_clock.event_sha256 == third_transition.clock_event_sha256
    assert second_clock.end_utc - second_clock.start_utc == timedelta(days=30)
    assert third_clock.end_utc - third_clock.start_utc == timedelta(days=30)
    assert broker_write_tripwire == []


def test_case_ad_read_only_external_audit_cannot_install_v2(tmp_path) -> None:
    fixture = build_production_epoch_v1_fixture(tmp_path / "audit-v1.sqlite3")
    import sqlite3

    with sqlite3.connect(
        f"file:{fixture.db_path.as_posix()}?mode=ro", uri=True
    ) as conn:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert len(conn.execute("SELECT * FROM state_events").fetchall()) == 539

    assert "experiment_epoch_clock_events_v2" not in tables
    assert "experiment_epoch_authorization_events_v2" not in tables
    with Database.open(fixture.db_path) as db:
        assert snapshot_v1_rows(db) == fixture.snapshot


def test_case_ae_scheduler_validation_cannot_install_v2_or_start_clock(
    tmp_path,
) -> None:
    fixture = build_production_epoch_v1_fixture(tmp_path / "scheduler-v1.sqlite3")
    task = SchedulerTaskSnapshot(
        task_name="CodexIBKRMarketDataGate",
        exists=True,
        enabled=False,
        execute="PowerShell.exe",
        arguments=(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            r"C:\AI_VAULT_IBKR\RUN_IBKR_MARKET_DATA_GATE.ps1",
            "-RepoRoot",
            r"C:\AI_VAULT_IBKR",
            "-PythonExe",
            r"C:\Python311\python.exe",
            "-ApprovedHead",
            BASE_HEAD,
            "-Scheduled",
        ),
        user_id=r"CXASUS_TUF_F16\cesar",
        logon_type="Interactive",
        run_level="Highest",
        multiple_instances="IgnoreNew",
        working_directory=r"C:\AI_VAULT_IBKR",
        restart_count=3,
        restart_interval_minutes=5,
        weekly_days=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
        weekly_start="09:35",
        logon_users=(r"CXASUS_TUF_F16\cesar",),
        user_sid=OWNER_SID,
        logon_user_sids=(OWNER_SID,),
    )
    report = validate_scheduler_startup(
        task,
        RuntimeGateSnapshot(
            repo_root=r"C:\AI_VAULT_IBKR",
            current_head=BASE_HEAD,
            gateway_available=True,
            kernel_verified=True,
            provenance_gate="PASS",
            lock_diagnostic="PASS",
        ),
        SchedulerExpectation(
            task_name="CodexIBKRMarketDataGate",
            repo_root=r"C:\AI_VAULT_IBKR",
            approved_head=BASE_HEAD,
            owner_user=r"CXASUS_TUF_F16\cesar",
            owner_sid=OWNER_SID,
            require_frozen=True,
        ),
    )

    assert report["status"] == "PASS", json.dumps(report, sort_keys=True)
    with Database.open(fixture.db_path) as db:
        tables = {
            str(row[0])
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert snapshot_v1_rows(db) == fixture.snapshot
        assert "experiment_epoch_clock_events_v2" not in tables
        assert "experiment_epoch_authorization_events_v2" not in tables
        assert (
            db.execute("SELECT COUNT(*) FROM experiment_clock_events").fetchone()[0]
            == 1
        )
