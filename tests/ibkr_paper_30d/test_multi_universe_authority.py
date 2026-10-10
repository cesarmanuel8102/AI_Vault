from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_authority import (
    MultiUniverseAuthorityError,
    MultiUniverseAuthorityStore,
)
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
    SleeveAuthorityDefinition,
    TransitionTarget,
)
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.production_continuity_runtime import (
    _database_sleeve_authority_sha256,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


NOW = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)


def _authorities():
    regular = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=Decimal("493.98"),
        opening_pnl_usd=Decimal("-6.02"),
        source_state_sha256="d" * 64,
    )
    continuous = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=Decimal("500"),
        opening_pnl_usd=Decimal("0"),
        source_state_sha256="e" * 64,
    )
    economic = OwnerEconomicRiskAuthorization(
        authorization_id="owner-two-sleeve-risk-v1",
        owner_id="S-1-5-21-owner",
        policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        regular_allocation_usd=Decimal("500"),
        extended_allocation_usd=Decimal("500"),
        maximum_liability_ratio=Decimal("1.00"),
        daily_loss_limit_usd="DISABLED",
        drawdown_limit_usd="DISABLED",
        successor_definition_sha256="1" * 64,
        issued_at_utc=NOW,
        expires_at_utc=NOW + timedelta(days=30),
    )
    return regular, continuous, economic


def _target(regular, continuous, economic):
    return TransitionTarget(
        transition_id="transition-authority-1",
        predecessor_epoch_id="AUTONOMY_EPOCH_1",
        successor_epoch_id="AUTONOMY_EPOCH_2",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head="3" * 40,
        account_identity_sha256="4" * 64,
        clock_authority_sha256="5" * 64,
        regular_sleeve_authority_sha256=regular.sha256,
        continuous_sleeve_authority_sha256=continuous.sha256,
        economic_risk_authorization_sha256=economic.sha256,
        certified_family_set_sha256="9" * 64,
        canary_authorization_sha256="a" * 64,
        writer_binding_sha256="b" * 64,
    )


def _open(path):
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    return db


def test_exact_authorities_persist_and_recover_idempotently(tmp_path) -> None:
    regular, continuous, economic = _authorities()
    target = _target(regular, continuous, economic)
    with _open(tmp_path / "authority.sqlite3") as db:
        store = MultiUniverseAuthorityStore(db)
        first = store.bind(
            target=target,
            sleeve_authorities=(regular, continuous),
            economic_authorization=economic,
        )
        retry = store.bind(
            target=target,
            sleeve_authorities=(regular, continuous),
            economic_authorization=economic,
        )

        assert first.status == retry.status == "PASS"
        assert retry.idempotent is True
        assert store.sleeve_authority(CapitalSleeve.REGULAR_SLEEVE) == regular
        assert store.sleeve_authority(CapitalSleeve.CONTINUOUS_SLEEVE) == continuous
        assert store.economic_authorization() == economic
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 2
        assert db.execute(
            "SELECT COUNT(*) FROM owner_economic_risk_authorization_events"
        ).fetchone()[0] == 1


def test_changed_authority_conflicts_without_partial_append(tmp_path) -> None:
    regular, continuous, economic = _authorities()
    target = _target(regular, continuous, economic)
    changed = regular.model_copy(update={"opening_equity_usd": Decimal("490")})
    with _open(tmp_path / "conflict.sqlite3") as db:
        store = MultiUniverseAuthorityStore(db)
        store.bind(
            target=target,
            sleeve_authorities=(regular, continuous),
            economic_authorization=economic,
        )
        with pytest.raises(MultiUniverseAuthorityError, match="AUTHORITY_TARGET_MISMATCH"):
            store.bind(
                target=target,
                sleeve_authorities=(changed, continuous),
                economic_authorization=economic,
            )
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 2


def test_runtime_authority_hash_is_derived_from_database_not_caller(tmp_path) -> None:
    regular, continuous, economic = _authorities()
    target = _target(regular, continuous, economic)
    with _open(tmp_path / "runtime-authority.sqlite3") as db:
        MultiUniverseAuthorityStore(db).bind(
            target=target,
            sleeve_authorities=(regular, continuous),
            economic_authorization=economic,
        )

        actual = _database_sleeve_authority_sha256(
            db, CapitalSleeve.REGULAR_SLEEVE
        )

    assert actual == regular.sha256
    assert actual != "f" * 64
