from __future__ import annotations

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.multi_universe_transition import (
    MultiUniverseTransitionCoordinator,
    MultiUniverseTransitionError,
    require_predecessor_retired,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.successor_authorization import (
    SuccessorAuthorizationError,
    validate_transition_target_authorization,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


PHASES = tuple(TransitionPhase)


def _target(**overrides) -> TransitionTarget:
    values = {
        "transition_id": "transition-v4-1",
        "predecessor_epoch_id": "AUTONOMY_EPOCH_2",
        "successor_epoch_id": "AUTONOMY_EPOCH_3",
        "successor_definition_sha256": "1" * 64,
        "owner_authorization_sha256": "2" * 64,
        "approved_git_head": "3" * 40,
        "account_identity_sha256": "4" * 64,
        "clock_authority_sha256": "5" * 64,
        "regular_sleeve_authority_sha256": "6" * 64,
        "continuous_sleeve_authority_sha256": "7" * 64,
        "economic_risk_authorization_sha256": "8" * 64,
        "certified_family_set_sha256": "9" * 64,
        "canary_authorization_sha256": "a" * 64,
        "writer_binding_sha256": "b" * 64,
    }
    values.update(overrides)
    return TransitionTarget(**values)


def _open(path):
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    return db


def _evidence(phase: TransitionPhase) -> dict[str, object]:
    evidence: dict[str, object] = {
        "phase_evidence_sha256": phase.value.lower().encode().hex().ljust(64, "0")[:64],
        "canary_flat": True,
        "continuity_exact": True,
        "broker_write_count": 0,
    }
    if phase is TransitionPhase.CANARY_PASS:
        evidence["canary_status"] = "PASS"
    if phase is TransitionPhase.PREDECESSOR_RETIRED:
        evidence.update(
            {
                "retirement_status": "PASS",
                "retirement_tombstone_sha256": "c" * 64,
            }
        )
    if phase is TransitionPhase.SUCCESSOR_COMMITTED:
        evidence["successor_commit_sha256"] = "d" * 64
    if phase is TransitionPhase.SUPERVISION_BOUND:
        evidence.update(
            {
                "reconciliation_status": "PASS",
                "inherited_position_projection_sha256": "1" * 64,
                "ownership_projection_sha256": "2" * 64,
                "writer_binding_sha256": "b" * 64,
                "new_entry_authority": False,
            }
        )
    if phase is TransitionPhase.RUNTIME_BOUND:
        evidence["writer_binding_sha256"] = "b" * 64
    if phase is TransitionPhase.ACTIVE:
        classifications = {
            "classified_canary_currency_balances": [],
            "classified_non_experiment_currency_balances": [
                {
                    "currency": "USD",
                    "amount": "999000",
                    "provenance_sha256": "e" * 64,
                }
            ],
        }
        evidence.update(
            {
                "reconciliation_status": "PASS",
                **classifications,
                "cash_classification_sha256": sha256_json(classifications),
            }
        )
    return evidence


def test_only_ordered_phases_are_legal_and_exact_retries_are_idempotent(tmp_path):
    with _open(tmp_path / "ordered.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        prepared = coordinator.prepare(_target())
        retry = coordinator.prepare(_target())
        assert prepared.phase is TransitionPhase.PREPARED
        assert retry.idempotent is True

        for phase in PHASES[1:]:
            first = coordinator.advance(phase, _evidence(phase))
            second = coordinator.advance(phase, _evidence(phase))
            assert first.phase is phase
            assert second.idempotent is True

        count = db.execute(
            "SELECT COUNT(*) FROM successor_transition_events"
        ).fetchone()[0]
    assert count == len(PHASES)


def test_active_phase_requires_hash_bound_external_cash_classification(tmp_path):
    with _open(tmp_path / "cash-classification.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        for phase in PHASES[1:-1]:
            coordinator.advance(phase, _evidence(phase))
        invalid = _evidence(TransitionPhase.ACTIVE)
        invalid.pop("cash_classification_sha256")

        with pytest.raises(
            MultiUniverseTransitionError,
            match="ACTIVE_CASH_CLASSIFICATION_REQUIRED",
        ):
            coordinator.advance(TransitionPhase.ACTIVE, invalid)


@pytest.mark.parametrize(
    "skipped_phase_name",
    (
        "PREDECESSOR_QUIESCED",
        "PREDECESSOR_RETIRED",
        "SUCCESSOR_COMMITTED",
        "SUPERVISION_BOUND",
        "CANARY_PASS",
    ),
)
def test_transition_cannot_skip_required_phase(tmp_path, skipped_phase_name):
    skipped_phase = getattr(TransitionPhase, skipped_phase_name)
    with _open(tmp_path / f"skip-{skipped_phase.value}.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        desired = PHASES[PHASES.index(skipped_phase) + 1]
        with pytest.raises(MultiUniverseTransitionError, match="PHASE_ORDER"):
            coordinator.advance(desired, _evidence(desired))


def test_different_target_or_changed_evidence_blocks(tmp_path):
    with _open(tmp_path / "conflict.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        with pytest.raises(MultiUniverseTransitionError, match="TARGET_CONFLICT"):
            coordinator.prepare(_target(successor_definition_sha256="f" * 64))
        coordinator.advance(
            TransitionPhase.PREDECESSOR_QUIESCED,
            _evidence(TransitionPhase.PREDECESSOR_QUIESCED),
        )
        changed = _evidence(TransitionPhase.PREDECESSOR_QUIESCED)
        changed["broker_write_count"] = 1
        with pytest.raises(MultiUniverseTransitionError, match="RETRY_CONFLICT"):
            coordinator.advance(TransitionPhase.PREDECESSOR_QUIESCED, changed)


def test_retirement_and_canary_require_positive_hash_bound_evidence(tmp_path):
    with _open(tmp_path / "evidence.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        coordinator.advance(
            TransitionPhase.PREDECESSOR_QUIESCED,
            _evidence(TransitionPhase.PREDECESSOR_QUIESCED),
        )
        invalid_retirement = _evidence(TransitionPhase.PREDECESSOR_RETIRED)
        invalid_retirement.pop("retirement_tombstone_sha256")
        with pytest.raises(MultiUniverseTransitionError, match="RETIREMENT_EVIDENCE"):
            coordinator.advance(TransitionPhase.PREDECESSOR_RETIRED, invalid_retirement)
        coordinator.advance(
            TransitionPhase.PREDECESSOR_RETIRED,
            _evidence(TransitionPhase.PREDECESSOR_RETIRED),
        )
        invalid_commit = _evidence(TransitionPhase.SUCCESSOR_COMMITTED)
        invalid_commit.pop("successor_commit_sha256")
        with pytest.raises(MultiUniverseTransitionError, match="SUCCESSOR_COMMIT_EVIDENCE"):
            coordinator.advance(TransitionPhase.SUCCESSOR_COMMITTED, invalid_commit)
        coordinator.advance(
            TransitionPhase.SUCCESSOR_COMMITTED,
            _evidence(TransitionPhase.SUCCESSOR_COMMITTED),
        )
        coordinator.advance(
            TransitionPhase.SUPERVISION_BOUND,
            _evidence(TransitionPhase.SUPERVISION_BOUND),
        )
        coordinator.advance(
            TransitionPhase.CANARY_EXCLUSIVE,
            _evidence(TransitionPhase.CANARY_EXCLUSIVE),
        )
        invalid_canary = _evidence(TransitionPhase.CANARY_PASS)
        invalid_canary.pop("canary_status")
        with pytest.raises(MultiUniverseTransitionError, match="CANARY_EVIDENCE"):
            coordinator.advance(TransitionPhase.CANARY_PASS, invalid_canary)


def test_successor_supervision_precedes_canary(tmp_path):
    with _open(tmp_path / "supervision-first.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        for phase in (
            TransitionPhase.PREDECESSOR_QUIESCED,
            TransitionPhase.PREDECESSOR_RETIRED,
            TransitionPhase.SUCCESSOR_COMMITTED,
        ):
            coordinator.advance(phase, _evidence(phase))

        with pytest.raises(MultiUniverseTransitionError, match="PHASE_ORDER"):
            coordinator.advance(
                TransitionPhase.CANARY_EXCLUSIVE,
                _evidence(TransitionPhase.CANARY_EXCLUSIVE),
            )
        bound = coordinator.advance(
            TransitionPhase.SUPERVISION_BOUND,
            _evidence(TransitionPhase.SUPERVISION_BOUND),
        )
        assert bound.next_phase is TransitionPhase.CANARY_EXCLUSIVE


def test_supervision_binding_requires_exact_reconciliation_and_projection(tmp_path):
    with _open(tmp_path / "supervision-evidence.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        for phase in (
            TransitionPhase.PREDECESSOR_QUIESCED,
            TransitionPhase.PREDECESSOR_RETIRED,
            TransitionPhase.SUCCESSOR_COMMITTED,
        ):
            coordinator.advance(phase, _evidence(phase))

        invalid = _evidence(TransitionPhase.SUPERVISION_BOUND)
        invalid.pop("inherited_position_projection_sha256")
        with pytest.raises(
            MultiUniverseTransitionError,
            match="SUPERVISION_BINDING_EVIDENCE_INVALID",
        ):
            coordinator.advance(TransitionPhase.SUPERVISION_BOUND, invalid)


def test_successor_commit_guard_requires_exact_retired_target(tmp_path):
    target = _target()
    with _open(tmp_path / "commit-guard.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(target)
        with pytest.raises(
            MultiUniverseTransitionError,
            match="PREDECESSOR_RETIREMENT_NOT_PROVEN",
        ):
            require_predecessor_retired(
                db,
                transition_id=target.transition_id,
                target_sha256=target.sha256,
            )
        for phase in PHASES[1 : PHASES.index(TransitionPhase.PREDECESSOR_RETIRED) + 1]:
            coordinator.advance(phase, _evidence(phase))

        event_sha = require_predecessor_retired(
            db,
            transition_id=target.transition_id,
            target_sha256=target.sha256,
        )

        coordinator.advance(
            TransitionPhase.SUCCESSOR_COMMITTED,
            _evidence(TransitionPhase.SUCCESSOR_COMMITTED),
        )
        assert require_predecessor_retired(
            db,
            transition_id=target.transition_id,
            target_sha256=target.sha256,
        ) == event_sha

    assert len(event_sha) == 64


def test_transition_target_requires_exact_owner_authorization_binding():
    target = _target()
    receipt = {
        "receipt_sha256": target.owner_authorization_sha256,
        "definition_sha256": target.successor_definition_sha256,
        "approved_git_head": target.approved_git_head,
    }

    assert validate_transition_target_authorization(target, receipt) == receipt
    with pytest.raises(
        SuccessorAuthorizationError,
        match="SUCCESSOR_AUTHORIZATION_BINDING_MISMATCH",
    ):
        validate_transition_target_authorization(
            target,
            {**receipt, "approved_git_head": "f" * 40},
        )


@pytest.mark.parametrize("crash_phase", PHASES)
def test_recovery_after_every_durable_phase_never_duplicates_or_reauthorizes(
    tmp_path, crash_phase
):
    with _open(tmp_path / f"recover-{crash_phase.value}.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        for phase in PHASES[1 : PHASES.index(crash_phase) + 1]:
            coordinator.advance(phase, _evidence(phase))
        before = db.execute(
            "SELECT COUNT(*) FROM successor_transition_events"
        ).fetchone()[0]

        recovered = MultiUniverseTransitionCoordinator(db).recover(_target())
        after = db.execute(
            "SELECT COUNT(*) FROM successor_transition_events"
        ).fetchone()[0]

    assert after == before
    assert recovered.phase is crash_phase
    assert recovered.resume_successor is (
        PHASES.index(crash_phase) >= PHASES.index(TransitionPhase.PREDECESSOR_RETIRED)
    )
    assert recovered.predecessor_may_resume is (
        PHASES.index(crash_phase) < PHASES.index(TransitionPhase.PREDECESSOR_RETIRED)
    )


def test_post_retirement_recovery_never_resumes_predecessor(tmp_path):
    with _open(tmp_path / "irreversible-retirement.sqlite3") as db:
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(_target())
        coordinator.advance(
            TransitionPhase.PREDECESSOR_QUIESCED,
            _evidence(TransitionPhase.PREDECESSOR_QUIESCED),
        )
        coordinator.advance(
            TransitionPhase.PREDECESSOR_RETIRED,
            _evidence(TransitionPhase.PREDECESSOR_RETIRED),
        )

        recovered = MultiUniverseTransitionCoordinator(db).recover(_target())

    assert recovered.resume_successor is True
    assert recovered.predecessor_may_resume is False
