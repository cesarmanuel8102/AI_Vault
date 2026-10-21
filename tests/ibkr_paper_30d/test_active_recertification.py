from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.multi_universe_models import TransitionPhase
from ibkr_paper_30d.multi_universe_transition import (
    MultiUniverseTransitionCoordinator,
    MultiUniverseTransitionError,
    current_cash_classifications,
)
from test_multi_universe_transition import _open, _target, _evidence, PHASES
from test_canary_execution import _request, _evidence as canary_evidence
from ibkr_paper_30d.canary_execution import CanaryExecutionAdapter


def active(db, target=None):
    coordinator = MultiUniverseTransitionCoordinator(db)
    target = target or _target()
    coordinator.prepare(target)
    for phase in PHASES[1:]:
        coordinator.advance(phase, _evidence(phase))
    return coordinator, target


def release_evidence(coordinator, target):
    return {**_evidence(TransitionPhase.ACTIVE), "owner_authorized": True,
        "owner_sid": "S-1-5-21-1001", "current_head": "f" * 40,
        "account_identity_sha256": target.account_identity_sha256,
        "paper_port_4002_listening": True, "live_port_4001_listening": False,
        "authenticated_paper": True, "broker_reconciliation_status": "PASS",
        "broker_state_certain": True, "tracked_tree_clean": True, "writer_count": 0,
        "open_order_count": 0, "new_execution_count": 0, "broker_write_count": 0,
        "release_artifact_sha256": "0" * 64,
        "transition_phase": "ACTIVE", "phase_event_sha256": coordinator.recover(target).phase_event_sha256,
        "recertification_required": True, "current_adapter_sha256": "d" * 64}


def test_active_release_preserves_history_and_binds_recertification(tmp_path):
    with _open(tmp_path / "active.sqlite3") as db:
        coordinator, target = active(db)
        before = db.execute("select * from successor_transition_events order by sequence").fetchall()
        result = coordinator.authorize_runtime_release(target, approved_git_head="f" * 40,
                                                       evidence=release_evidence(coordinator, target))
        assert coordinator.recover(target).phase is TransitionPhase.ACTIVE
        assert db.execute("select * from successor_transition_events order by sequence limit ?", (len(before),)).fetchall() == before
        assert coordinator.active_recertification_release_sha256(
            target.account_identity_sha256, "f" * 40, "d" * 64) == result["event_sha256"]
        for account, head, adapter in [("0" * 64, "f" * 40, "d" * 64),
                                      (target.account_identity_sha256, "0" * 40, "d" * 64),
                                      (target.account_identity_sha256, "f" * 40, "0" * 64)]:
            assert coordinator.active_recertification_release_sha256(account, head, adapter) is None


def test_active_release_refreshes_changed_broker_evidence_under_same_head(tmp_path):
    with _open(tmp_path / "active-refresh.sqlite3") as db:
        coordinator, target = active(db)
        first_evidence = release_evidence(coordinator, target)
        first = coordinator.authorize_runtime_release(
            target,
            approved_git_head="f" * 40,
            evidence=first_evidence,
        )
        refreshed_evidence = release_evidence(coordinator, target)
        refreshed_classifications = {
            "classified_canary_currency_balances": [],
            "classified_non_experiment_currency_balances": [
                {
                    "currency": "USD",
                    "amount": "253880.18",
                    "provenance_sha256": "9" * 64,
                }
            ],
        }
        refreshed_evidence.update(
            {
                **refreshed_classifications,
                "cash_classification_sha256": sha256_json(
                    refreshed_classifications
                ),
                "cash_rounding_quantum_usd": "0.01",
                "raw_usd_cash_snapshot_sha256": "8" * 64,
                "broker_readonly_report_sha256": "7" * 64,
                "observed_at_utc": "2026-10-21T13:43:38Z",
            }
        )

        refreshed = coordinator.authorize_runtime_release(
            target,
            approved_git_head="f" * 40,
            evidence=refreshed_evidence,
        )
        retry = coordinator.authorize_runtime_release(
            target,
            approved_git_head="f" * 40,
            evidence=refreshed_evidence,
        )

        assert refreshed["idempotent"] is False
        assert refreshed["previous_approved_git_head"] == "f" * 40
        assert refreshed["event_sha256"] != first["event_sha256"]
        assert retry["idempotent"] is True
        assert retry["event_sha256"] == refreshed["event_sha256"]
        assert current_cash_classifications(db) == {
            **refreshed_classifications,
            "cash_rounding_reference": {
                "quantum_usd": "0.01",
                "provenance_sha256": "8" * 64,
            },
        }


@pytest.mark.parametrize("field,value", [("recertification_required", False),
    ("phase_event_sha256", "0" * 64), ("current_adapter_sha256", "invalid"),
    ("cash_classification_sha256", "0" * 64), ("writer_count", 1), ("open_order_count", 1)])
def test_active_release_blocks_unbound_or_unsafe_evidence(tmp_path, field, value):
    with _open(tmp_path / "unsafe.sqlite3") as db:
        coordinator, target = active(db)
        evidence = release_evidence(coordinator, target)
        evidence[field] = value
        with pytest.raises(MultiUniverseTransitionError):
            coordinator.authorize_runtime_release(target, approved_git_head="f" * 40, evidence=evidence)


def test_active_canary_requires_verified_maintenance_authority():
    request = _request()
    adapter = CanaryExecutionAdapter(begin_write=lambda key: True, now_utc=lambda: datetime.now(timezone.utc))
    evidence = canary_evidence(request, transition_phase="ACTIVE")
    assert "CANARY_EXCLUSIVE_REQUIRED" in adapter._authority_reasons(request, evidence)
    evidence["active_recertification_authorized"] = True
    evidence["active_recertification_release_sha256"] = "e" * 64
    assert "CANARY_EXCLUSIVE_REQUIRED" not in adapter._authority_reasons(request, evidence)


@pytest.mark.parametrize("token_valid,open_orders,positions", [(True, 0, 0), (False, 0, 0), (True, 1, 0), (True, 0, 1)])
def test_active_recertification_requires_database_authority_and_flat_family(tmp_path, token_valid, open_orders, positions):
    from datetime import timedelta
    from ibkr_paper_30d.product_capability import ProductFamilyCertificationStore, ProductCapabilityError
    from test_product_capability import _family, _transmit_only_with_adapter_a, ACCOUNT, ADAPTER, SUCCESSOR
    with _open(tmp_path / "capability.sqlite3") as db:
        coordinator, target = active(db, _target(account_identity_sha256=ACCOUNT, successor_definition_sha256=SUCCESSOR))
        family = _family("CRYPTO", "PAXOS")
        original = ProductFamilyCertificationStore(db, current_adapter_sha256=ADAPTER)
        _transmit_only_with_adapter_a(db, original, family)
        released = coordinator.authorize_runtime_release(target, approved_git_head="f" * 40,
                                                        evidence=release_evidence(coordinator, target))
        changed = ProductFamilyCertificationStore(db, current_adapter_sha256="d" * 64)
        authority = {"allow_generation_restart": True, "account_sha256": ACCOUNT,
            "successor_definition_sha256": SUCCESSOR, "approved_git_head": "f" * 40,
            "transition_phase": "ACTIVE", "reconciliation_status": "PASS",
            "family_open_orders": open_orders, "family_positions": positions,
            "active_recertification_release_sha256": released["event_sha256"] if token_valid else "0" * 64}
        now = datetime.now(timezone.utc)
        def record():
            return changed.record_read_only_candidate_evidence(family, evidence_sha256="e" * 64,
                account_sha256=ACCOUNT, adapter_sha256="d" * 64, observed_at_utc=now,
                expires_at_utc=now + timedelta(days=1), paper_limitations=("PAPER_SIMULATION_ONLY",),
                runtime_authorization=authority)
        if token_valid and open_orders == positions == 0:
            record()
            assert changed.projection(family).adapter_sha256 == "d" * 64
            assert not changed.projection(family).executable
        else:
            with pytest.raises(ProductCapabilityError, match="CANARY_RECERTIFICATION_UNSAFE"):
                record()
