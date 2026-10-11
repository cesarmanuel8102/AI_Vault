from __future__ import annotations

from datetime import datetime, timezone

from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
from tools.prepare_supervision_pilot import _host_evidence, _refresh_config_payload


NOW = datetime(2026, 10, 11, 16, 30, tzinfo=timezone.utc)
RELEASED_HEAD = "d" * 40


def _target() -> TransitionTarget:
    return TransitionTarget(
        transition_id="transition-1",
        predecessor_epoch_id="AUTONOMY_EPOCH_2",
        successor_epoch_id="AUTONOMY_EPOCH_3",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head="a" * 40,
        account_identity_sha256="3" * 64,
        clock_authority_sha256="4" * 64,
        regular_sleeve_authority_sha256="5" * 64,
        continuous_sleeve_authority_sha256="6" * 64,
        economic_risk_authorization_sha256="7" * 64,
        certified_family_set_sha256="8" * 64,
        canary_authorization_sha256="9" * 64,
        writer_binding_sha256="b" * 64,
    )


def test_host_evidence_uses_observed_release_head(monkeypatch) -> None:
    monkeypatch.setattr("tools.prepare_supervision_pilot._port_open", lambda port: port == 4002)
    monkeypatch.setattr("tools.prepare_supervision_pilot._writer_process_count", lambda: 1)

    evidence = _host_evidence(
        target=_target(),
        phase_evidence={"phase_evidence_sha256": "e" * 64},
        now=NOW,
        current_head=RELEASED_HEAD,
    )

    assert evidence.current_head == RELEASED_HEAD


def test_refresh_config_rebinds_effective_release_head() -> None:
    original = {
        "approved_head": "a" * 40,
        "requested_phase": TransitionPhase.SUCCESSOR_COMMITTED.value,
        "now_utc": "2026-10-10T00:00:00Z",
        "preserved": {"value": 1},
    }

    refreshed = _refresh_config_payload(
        original,
        phase=TransitionPhase.SUPERVISION_BOUND,
        now=NOW,
        current_head=RELEASED_HEAD,
    )

    assert refreshed["approved_head"] == RELEASED_HEAD
    assert refreshed["requested_phase"] == TransitionPhase.SUPERVISION_BOUND.value
    assert refreshed["now_utc"] == "2026-10-11T16:30:00Z"
    assert refreshed["preserved"] == {"value": 1}
    assert original["approved_head"] == "a" * 40
