from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_maintenance import (
    MaintenanceConfig,
    MaintenanceEvidence,
    apply_next_phase,
    validate_maintenance,
)
from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.multi_universe_transition import MultiUniverseTransitionCoordinator
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


NOW = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


def _target() -> TransitionTarget:
    return TransitionTarget(
        transition_id="transition-1",
        predecessor_epoch_id="AUTONOMY_EPOCH_2",
        successor_epoch_id="AUTONOMY_EPOCH_3",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head=HEAD,
        account_identity_sha256="3" * 64,
        clock_authority_sha256="4" * 64,
        regular_sleeve_authority_sha256="5" * 64,
        continuous_sleeve_authority_sha256="6" * 64,
        economic_risk_authorization_sha256="7" * 64,
        certified_family_set_sha256="8" * 64,
        canary_authorization_sha256="9" * 64,
        writer_binding_sha256="b" * 64,
    )


def _setup(tmp_path: Path, phase=TransitionPhase.PREPARED):
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / "state.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    authority = repo / "owner.json"
    authority.write_text("owner-authority", encoding="utf-8")
    config = MaintenanceConfig(
        repo_root=repo,
        database_path=db_path,
        backup_directory=repo / "backup",
        authority_file_paths=(authority,),
        approved_head=HEAD,
        target=_target(),
        requested_phase=phase,
        now_utc=NOW,
    )
    evidence = MaintenanceEvidence(
        observed_at_utc=NOW - timedelta(seconds=5),
        current_head=HEAD,
        tracked_tree_clean=True,
        paper_port_4002_listening=True,
        live_port_4001_listening=False,
        authenticated_paper=True,
        account_identity_sha256="3" * 64,
        broker_state_certain=True,
        writer_count=1,
        writer_binding_sha256="b" * 64,
        receipt_sha256=("2" * 64, "9" * 64, "1" * 64),
        phase_evidence={"target_sha256": _target().sha256},
    )
    return config, evidence


def test_validate_only_is_zero_mutation(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    before = hashlib.sha256(config.database_path.read_bytes()).hexdigest()
    before_files = sorted(str(path.relative_to(config.repo_root)) for path in config.repo_root.rglob("*"))

    result = validate_maintenance(config, evidence)

    after = hashlib.sha256(config.database_path.read_bytes()).hexdigest()
    after_files = sorted(str(path.relative_to(config.repo_root)) for path in config.repo_root.rglob("*"))
    assert result.status == "PASS"
    assert result.mutation_performed is False
    assert before == after
    assert before_files == after_files


def test_validate_blocks_every_unsafe_host_fact(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    changes = [
        ({"current_head": "f" * 40}, "APPROVED_HEAD_MISMATCH"),
        ({"tracked_tree_clean": False}, "TRACKED_TREE_DIRTY"),
        ({"live_port_4001_listening": True}, "POSSIBLE_LIVE_CONNECTION"),
        ({"paper_port_4002_listening": False}, "PAPER_PORT_UNAVAILABLE"),
        ({"writer_count": 2}, "DUPLICATE_WRITER_ACTIVE"),
        ({"broker_state_certain": False}, "BROKER_STATE_UNCERTAIN"),
        ({"observed_at_utc": NOW - timedelta(minutes=10)}, "MAINTENANCE_EVIDENCE_STALE"),
        ({"receipt_sha256": ()}, "MAINTENANCE_RECEIPTS_INCOMPLETE"),
    ]
    for update, reason in changes:
        result = validate_maintenance(config, evidence.model_copy(update=update))
        assert result.status == "BLOCK", reason
        assert reason in result.reason_codes


def test_apply_creates_verified_backup_then_advances_exactly_one_phase(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)

    first = apply_next_phase(config, evidence)

    assert first.status == "PASS"
    assert first.phase is TransitionPhase.PREPARED
    assert first.mutation_performed is True
    assert first.backup_manifest_sha256 is not None
    assert (config.backup_directory / "backup_manifest.json").is_file()
    with Database.open(config.database_path) as db:
        versions = [row[0] for row in db.execute("SELECT version FROM schema_versions ORDER BY version")]
        rows = db.execute("SELECT phase FROM successor_transition_events ORDER BY sequence").fetchall()
    assert versions == [1, 2, 3, 4]
    assert rows == [("PREPARED",)]


def test_exact_retry_is_idempotent_changed_retry_conflicts(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    first = apply_next_phase(config, evidence)
    retry = apply_next_phase(config, evidence)
    changed_target = config.target.model_copy(
        update={"owner_authorization_sha256": "f" * 64}
    )
    changed = apply_next_phase(
        config.model_copy(update={"target": changed_target}), evidence
    )

    assert first.status == retry.status == "PASS"
    assert retry.idempotent is True
    assert retry.mutation_performed is False
    assert changed.status == "BLOCK"
    assert "TRANSITION_TARGET_CONFLICT" in changed.reason_codes


def test_illegal_phase_jump_blocks_without_mutation(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path, TransitionPhase.CANARY_EXCLUSIVE)
    before = hashlib.sha256(config.database_path.read_bytes()).hexdigest()

    result = apply_next_phase(config, evidence)

    assert result.status == "BLOCK"
    assert "TRANSITION_PHASE_ORDER_INVALID" in result.reason_codes
    assert hashlib.sha256(config.database_path.read_bytes()).hexdigest() == before


def test_backup_failure_blocks_before_schema_install(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    missing = config.repo_root / "missing-authority.json"
    broken = config.model_copy(update={"authority_file_paths": (missing,)})

    result = apply_next_phase(broken, evidence)

    assert result.status == "BLOCK"
    assert "MAINTENANCE_BACKUP_FAILED" in result.reason_codes
    with Database.open(config.database_path) as db:
        versions = [row[0] for row in db.execute("SELECT version FROM schema_versions ORDER BY version")]
    assert versions == [1, 2, 3]


def test_apply_advances_only_the_requested_next_phase(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    assert apply_next_phase(config, evidence).phase is TransitionPhase.PREPARED
    next_config = config.model_copy(
        update={"requested_phase": TransitionPhase.PREDECESSOR_QUIESCED}
    )
    next_evidence = evidence.model_copy(
        update={"phase_evidence": {"phase_evidence_sha256": "c" * 64}}
    )

    result = apply_next_phase(next_config, next_evidence)

    assert result.status == "PASS"
    assert result.phase is TransitionPhase.PREDECESSOR_QUIESCED
    with Database.open(config.database_path) as db:
        phases = [
            row[0]
            for row in db.execute(
                "SELECT phase FROM successor_transition_events ORDER BY sequence"
            )
        ]
    assert phases == ["PREPARED", "PREDECESSOR_QUIESCED"]


def test_validate_accepts_authorized_runtime_release_head(tmp_path: Path) -> None:
    config, evidence = _setup(tmp_path)
    released_head = "d" * 40
    release_evidence = {
        "owner_authorized": True,
        "owner_sid": "S-1-5-21-test",
        "account_identity_sha256": config.target.account_identity_sha256,
        "current_head": released_head,
        "live_port_4001_listening": False,
        "paper_port_4002_listening": True,
        "authenticated_paper": True,
        "broker_reconciliation_status": "PASS",
        "broker_state_certain": True,
        "tracked_tree_clean": True,
        "writer_count": 0,
        "open_order_count": 0,
        "new_execution_count": 0,
        "broker_write_count": 0,
        "release_artifact_sha256": "e" * 64,
    }
    with Database.open(config.database_path) as db:
        install_multi_universe_schema_v4(db)
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(config.target)
        for phase in (
            TransitionPhase.PREDECESSOR_QUIESCED,
            TransitionPhase.PREDECESSOR_RETIRED,
            TransitionPhase.SUCCESSOR_COMMITTED,
        ):
            phase_evidence = {"phase_evidence_sha256": "c" * 64}
            if phase is TransitionPhase.PREDECESSOR_RETIRED:
                phase_evidence.update(
                    retirement_status="PASS",
                    retirement_tombstone_sha256="f" * 64,
                )
            if phase is TransitionPhase.SUCCESSOR_COMMITTED:
                phase_evidence["successor_commit_sha256"] = "a" * 64
            coordinator.advance(phase, phase_evidence)
        coordinator.authorize_runtime_release(
            config.target,
            approved_git_head=released_head,
            evidence=release_evidence,
        )
    released_config = config.model_copy(
        update={
            "approved_head": released_head,
            "requested_phase": TransitionPhase.SUCCESSOR_COMMITTED,
        }
    )
    released_evidence = evidence.model_copy(update={"current_head": released_head})

    result = validate_maintenance(released_config, released_evidence)

    assert result.status == "PASS"
    assert "TRANSITION_HEAD_MISMATCH" not in result.reason_codes
