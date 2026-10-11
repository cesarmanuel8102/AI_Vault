from __future__ import annotations

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.multi_universe_transition import (
    MultiUniverseTransitionCoordinator,
    MultiUniverseTransitionError,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


OLD_HEAD = "1" * 40
NEW_HEAD = "2" * 40
SECOND_HEAD = "4" * 40


def _target() -> TransitionTarget:
    return TransitionTarget(
        transition_id="transition-runtime-release",
        predecessor_epoch_id="AUTONOMY_EPOCH_1",
        successor_epoch_id="AUTONOMY_EPOCH_2",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head=OLD_HEAD,
        account_identity_sha256="3" * 64,
        clock_authority_sha256="4" * 64,
        regular_sleeve_authority_sha256="5" * 64,
        continuous_sleeve_authority_sha256="6" * 64,
        economic_risk_authorization_sha256="7" * 64,
        certified_family_set_sha256="8" * 64,
        canary_authorization_sha256="9" * 64,
        writer_binding_sha256="a" * 64,
    )


def _phase_evidence(phase: TransitionPhase) -> dict[str, object]:
    evidence: dict[str, object] = {"phase_evidence_sha256": "b" * 64}
    if phase is TransitionPhase.PREDECESSOR_RETIRED:
        evidence.update(
            retirement_status="PASS",
            retirement_tombstone_sha256="c" * 64,
        )
    if phase is TransitionPhase.SUCCESSOR_COMMITTED:
        evidence["successor_commit_sha256"] = "d" * 64
    if phase is TransitionPhase.SUPERVISION_BOUND:
        evidence.update(
            reconciliation_status="PASS",
            inherited_position_projection_sha256="e" * 64,
            ownership_projection_sha256="f" * 64,
            writer_binding_sha256="a" * 64,
            new_entry_authority=False,
        )
    return evidence


def _release_evidence(**updates: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "owner_authorized": True,
        "owner_sid": "S-1-5-21-1001",
        "current_head": NEW_HEAD,
        "account_identity_sha256": "3" * 64,
        "paper_port_4002_listening": True,
        "live_port_4001_listening": False,
        "authenticated_paper": True,
        "broker_reconciliation_status": "PASS",
        "broker_state_certain": True,
        "tracked_tree_clean": True,
        "writer_count": 0,
        "open_order_count": 0,
        "new_execution_count": 0,
        "broker_write_count": 0,
        "release_artifact_sha256": "0" * 64,
    }
    evidence.update(updates)
    return evidence


def _coordinator(tmp_path):
    db = Database.open(tmp_path / "state.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    coordinator = MultiUniverseTransitionCoordinator(db)
    target = _target()
    coordinator.prepare(target)
    for phase in (
        TransitionPhase.PREDECESSOR_QUIESCED,
        TransitionPhase.PREDECESSOR_RETIRED,
        TransitionPhase.SUCCESSOR_COMMITTED,
    ):
        coordinator.advance(phase, _phase_evidence(phase))
    return db, coordinator, target


def test_runtime_release_preserves_phase_history_and_changes_effective_head(
    tmp_path,
) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        receipt = coordinator.authorize_runtime_release(
            target,
            approved_git_head=NEW_HEAD,
            evidence=_release_evidence(),
        )
        recovered = coordinator.recover(target)

        assert receipt["status"] == "PASS"
        assert receipt["previous_approved_git_head"] == OLD_HEAD
        assert receipt["approved_git_head"] == NEW_HEAD
        assert coordinator.effective_approved_git_head(target) == NEW_HEAD
        assert recovered.phase is TransitionPhase.SUCCESSOR_COMMITTED
        assert [
            row[0]
            for row in db.execute(
                "SELECT phase FROM successor_transition_events "
                "WHERE event_type='PHASE_COMMITTED' ORDER BY sequence"
            )
        ] == [
            "PREPARED",
            "PREDECESSOR_QUIESCED",
            "PREDECESSOR_RETIRED",
            "SUCCESSOR_COMMITTED",
        ]
    finally:
        db.close()


def test_runtime_release_is_idempotent_only_for_exact_same_release(tmp_path) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        first = coordinator.authorize_runtime_release(
            target,
            approved_git_head=NEW_HEAD,
            evidence=_release_evidence(),
        )
        retry = coordinator.authorize_runtime_release(
            target,
            approved_git_head=NEW_HEAD,
            evidence=_release_evidence(),
        )

        assert retry["event_sha256"] == first["event_sha256"]
        assert first["idempotent"] is False
        assert retry["idempotent"] is True
        assert (
            db.execute(
                "SELECT COUNT(*) FROM successor_transition_events "
                "WHERE event_type='RUNTIME_RELEASE_AUTHORIZED'"
            ).fetchone()[0]
            == 1
        )
    finally:
        db.close()


def test_runtime_release_appends_a_verified_head_chain(tmp_path) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        first = coordinator.authorize_runtime_release(
            target,
            approved_git_head=NEW_HEAD,
            evidence=_release_evidence(),
        )
        second_evidence = _release_evidence(current_head=SECOND_HEAD)
        second = coordinator.authorize_runtime_release(
            target,
            approved_git_head=SECOND_HEAD,
            evidence=second_evidence,
        )
        retry = coordinator.authorize_runtime_release(
            target,
            approved_git_head=SECOND_HEAD,
            evidence=second_evidence,
        )

        assert first["previous_approved_git_head"] == OLD_HEAD
        assert second["previous_approved_git_head"] == NEW_HEAD
        assert second["idempotent"] is False
        assert retry["event_sha256"] == second["event_sha256"]
        assert retry["idempotent"] is True
        assert coordinator.effective_approved_git_head(target) == SECOND_HEAD
        assert (
            db.execute(
                "SELECT COUNT(*) FROM successor_transition_events "
                "WHERE event_type='RUNTIME_RELEASE_AUTHORIZED'"
            ).fetchone()[0]
            == 2
        )
    finally:
        db.close()


def test_runtime_release_blocks_after_supervision_binding(tmp_path) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        coordinator.advance(
            TransitionPhase.SUPERVISION_BOUND,
            _phase_evidence(TransitionPhase.SUPERVISION_BOUND),
        )

        try:
            coordinator.authorize_runtime_release(
                target,
                approved_git_head=NEW_HEAD,
                evidence=_release_evidence(),
            )
        except MultiUniverseTransitionError as exc:
            assert str(exc) == "RUNTIME_RELEASE_PHASE_INVALID"
        else:
            raise AssertionError("release must block after supervision binding")
    finally:
        db.close()


def test_runtime_release_blocks_unsafe_broker_or_host_evidence(tmp_path) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        unsafe = (
            ({"live_port_4001_listening": True}, "POSSIBLE_LIVE_CONNECTION"),
            ({"writer_count": 1}, "RUNTIME_RELEASE_WRITER_ACTIVE"),
            ({"open_order_count": 1}, "RUNTIME_RELEASE_BROKER_NOT_FLAT"),
            ({"broker_state_certain": False}, "BROKER_STATE_UNCERTAIN"),
            ({"tracked_tree_clean": False}, "TRACKED_TREE_DIRTY"),
            ({"owner_authorized": False}, "OWNER_AUTHORIZATION_REQUIRED"),
            ({"current_head": OLD_HEAD}, "RUNTIME_RELEASE_HEAD_MISMATCH"),
        )
        for updates, reason in unsafe:
            try:
                coordinator.authorize_runtime_release(
                    target,
                    approved_git_head=NEW_HEAD,
                    evidence=_release_evidence(**updates),
                )
            except MultiUniverseTransitionError as exc:
                assert str(exc) == reason
            else:
                raise AssertionError(reason)
    finally:
        db.close()


def test_runtime_release_chain_can_advance_to_supervision_bound(tmp_path) -> None:
    db, coordinator, target = _coordinator(tmp_path)
    try:
        coordinator.authorize_runtime_release(
            target,
            approved_git_head=NEW_HEAD,
            evidence=_release_evidence(),
        )

        result = coordinator.advance(
            TransitionPhase.SUPERVISION_BOUND,
            _phase_evidence(TransitionPhase.SUPERVISION_BOUND),
        )

        assert result.phase is TransitionPhase.SUPERVISION_BOUND
        assert coordinator.effective_approved_git_head(target) == NEW_HEAD
        assert coordinator.recover(target).phase is TransitionPhase.SUPERVISION_BOUND
    finally:
        db.close()
