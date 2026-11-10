from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.capital_amendment import (
    CapitalAmendmentError,
    amend_two_sleeve_capital,
)
from ibkr_paper_30d import day1_launch as launch_module
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.contract_ownership import ContractOwnershipStore
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.measurement_segment import latest_segment
from ibkr_paper_30d.multi_universe_authority import MultiUniverseAuthorityStore
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
    SleeveAuthorityDefinition,
    TransitionTarget,
)
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import (
    CurrencyBalance,
    RegularCarryForward,
    SleeveLedgerStore,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

NOW = datetime.now(timezone.utc).replace(microsecond=0)
OLD_HEAD = "a" * 40
NEW_HEAD = "b" * 40


def _open_initialized(path):
    fixture_now = datetime.now(timezone.utc).replace(microsecond=0)
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
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
        issued_at_utc=NOW - timedelta(days=1),
        expires_at_utc=NOW + timedelta(days=1),
    )
    target = TransitionTarget(
        transition_id="transition-capital-test",
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
    MultiUniverseAuthorityStore(db).bind(
        target=target,
        sleeve_authorities=(regular, continuous),
        economic_authorization=economic,
    )
    ledger = SleeveLedgerStore(db)
    ledger.bootstrap_regular(
        RegularCarryForward(
            allocation_usd=Decimal("500"),
            currency_balances=(
                CurrencyBalance(currency="USD", amount=Decimal("514.23")),
            ),
            positions=(),
            open_order_count=0,
            fill_count=3,
            fees_usd=Decimal("1.00"),
            realized_pnl_usd=Decimal("15.23"),
            unrealized_pnl_usd=Decimal("0"),
            historical_event_sha256=("c" * 64,),
            source_ledger_sha256="f" * 64,
        ),
        regular.sha256,
    )
    ledger.bootstrap_continuous(continuous.sha256)
    ledger.append(
        CapitalSleeve.CONTINUOUS_SLEEVE,
        "CURRENCY_DEBIT",
        {"currency": "USD", "amount": "36.78"},
    )
    ledger.append(
        CapitalSleeve.CONTINUOUS_SLEEVE,
        "REALIZED_PNL",
        {"amount_usd": "-36.78"},
    )
    ledger.reconcile_broker_snapshot(
        {"positions": [], "open_orders": [], "executions": []},
        ContractOwnershipStore(db).projection(),
    )
    ExperimentClockStore(db).initialize_or_load(
        requested_start_utc=fixture_now - timedelta(days=1),
        duration_days=30,
        initial_allocation=Decimal("500"),
    )
    return db


def test_amend_two_sleeve_capital_preserves_pnl_and_is_idempotent(tmp_path) -> None:
    db = _open_initialized(tmp_path / "capital.sqlite3")
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        ledger = SleeveLedgerStore(db)
        before = ledger.project_all()
        clock_before = ExperimentClockStore(db).load_legacy()

        first = amend_two_sleeve_capital(
            db,
            target_principal_usd=Decimal("10000"),
            amendment_id="owner-capital-10k-20261110",
            now_utc=now,
            expires_at_utc=now + timedelta(days=20),
            previous_head=OLD_HEAD,
            new_head=NEW_HEAD,
        )
        retry = amend_two_sleeve_capital(
            db,
            target_principal_usd=Decimal("10000"),
            amendment_id="owner-capital-10k-20261110",
            now_utc=now + timedelta(minutes=5),
            expires_at_utc=now + timedelta(days=20),
            previous_head=OLD_HEAD,
            new_head=NEW_HEAD,
        )
        with pytest.raises(
            CapitalAmendmentError, match="CAPITAL_TARGET_STATE_AMBIGUOUS"
        ):
            amend_two_sleeve_capital(
                db,
                target_principal_usd=Decimal("10000"),
                amendment_id="different-amendment-id",
                now_utc=now + timedelta(minutes=4),
                expires_at_utc=now + timedelta(days=20),
                previous_head=OLD_HEAD,
                new_head=NEW_HEAD,
            )
        after = ledger.project_all()
        clock_after = ExperimentClockStore(db).load_legacy()

        assert first["status"] == retry["status"] == "PASS"
        assert first["idempotent"] is False
        assert retry["idempotent"] is True
        assert after.regular.allocation_usd == Decimal("10000.00")
        assert after.continuous.allocation_usd == Decimal("10000.00")
        assert after.regular.balance("USD") == before.regular.balance("USD") + Decimal(
            "9500"
        )
        assert after.continuous.balance("USD") == before.continuous.balance(
            "USD"
        ) + Decimal("9500")
        assert after.regular.realized_pnl_usd == before.regular.realized_pnl_usd
        assert after.continuous.realized_pnl_usd == before.continuous.realized_pnl_usd
        assert after.regular.fees_usd == before.regular.fees_usd
        assert clock_after == clock_before
        authority = MultiUniverseAuthorityStore(db)
        assert authority.sleeve_authority(
            CapitalSleeve.REGULAR_SLEEVE
        ).authorized_principal_usd == Decimal("10000")
        assert authority.economic_authorization().regular_allocation_usd == Decimal(
            "10000"
        )
        segment = latest_segment(db)
        assert Decimal(
            segment["sleeves"][CapitalSleeve.REGULAR_SLEEVE.value]["allocation_usd"]
        ) == Decimal("10000")
        assert Decimal(
            segment["sleeves"][CapitalSleeve.REGULAR_SLEEVE.value][
                "cumulative_pnl_vs_allocation_usd"
            ]
        ) == Decimal("14.23")
        assert (
            db.execute(
                "SELECT COUNT(*) FROM sleeve_ledger_events WHERE event_type='CAPITAL_CONTRIBUTION'"
            ).fetchone()[0]
            == 2
        )
    finally:
        db.close()


def test_amend_two_sleeve_capital_rejects_any_other_target(tmp_path) -> None:
    db = _open_initialized(tmp_path / "unauthorized-target.sqlite3")
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with pytest.raises(
            CapitalAmendmentError, match="UNAUTHORIZED_TARGET_PRINCIPAL"
        ):
            amend_two_sleeve_capital(
                db,
                target_principal_usd=Decimal("20000"),
                amendment_id="owner-capital-20k",
                now_utc=now,
                expires_at_utc=now + timedelta(days=20),
                previous_head=OLD_HEAD,
                new_head=NEW_HEAD,
            )
    finally:
        db.close()


def test_amend_two_sleeve_capital_rolls_back_when_a_sleeve_is_not_flat(
    tmp_path,
) -> None:
    db = _open_initialized(tmp_path / "blocked.sqlite3")
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        ledger = SleeveLedgerStore(db)
        ledger.append(CapitalSleeve.REGULAR_SLEEVE, "ORDER_OPENED", {})
        before = ledger.project_all()

        with pytest.raises(CapitalAmendmentError, match="SLEEVE_NOT_FLAT"):
            amend_two_sleeve_capital(
                db,
                target_principal_usd=Decimal("10000"),
                amendment_id="blocked",
                now_utc=now,
                expires_at_utc=now + timedelta(days=20),
                previous_head=OLD_HEAD,
                new_head=NEW_HEAD,
            )

        after = ledger.project_all()
        assert after.regular.allocation_usd == before.regular.allocation_usd
        assert after.continuous.allocation_usd == before.continuous.allocation_usd
        assert (
            db.execute(
                "SELECT COUNT(*) FROM sleeve_ledger_events WHERE event_type='CAPITAL_CONTRIBUTION'"
            ).fetchone()[0]
            == 0
        )
    finally:
        db.close()


def test_launch_bindings_accept_current_amendment_and_preserve_target_roots(
    tmp_path,
) -> None:
    from ibkr_paper_30d.multi_universe_models import TransitionPhase

    db = _open_initialized(tmp_path / "launch.sqlite3")
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        store = MultiUniverseAuthorityStore(db)
        roots = store.authority_lineage_roots()
        target = TransitionTarget(
            transition_id="transition-capital-test",
            predecessor_epoch_id="AUTONOMY_EPOCH_1",
            successor_epoch_id="AUTONOMY_EPOCH_2",
            successor_definition_sha256="1" * 64,
            owner_authorization_sha256="2" * 64,
            approved_git_head="3" * 40,
            account_identity_sha256="4" * 64,
            clock_authority_sha256="5" * 64,
            regular_sleeve_authority_sha256=roots[CapitalSleeve.REGULAR_SLEEVE.value],
            continuous_sleeve_authority_sha256=roots[
                CapitalSleeve.CONTINUOUS_SLEEVE.value
            ],
            economic_risk_authorization_sha256=roots["ECONOMIC"],
            certified_family_set_sha256="9" * 64,
            canary_authorization_sha256="a" * 64,
            writer_binding_sha256="b" * 64,
        )
        amend_two_sleeve_capital(
            db,
            target_principal_usd=Decimal("10000"),
            amendment_id="owner-capital-10k-20261110",
            now_utc=now,
            expires_at_utc=now + timedelta(days=20),
            previous_head=OLD_HEAD,
            new_head=NEW_HEAD,
        )

        bindings = launch_module._multi_universe_authority_bindings(
            db, target, TransitionPhase.SUPERVISION_BOUND
        )

        assert bindings["continuity_gap"] is False
        assert (
            bindings["regular_sleeve_authority_sha256"]
            != roots[CapitalSleeve.REGULAR_SLEEVE.value]
        )
        assert (
            bindings["regular_sleeve_authority_sha256"]
            == bindings["expected_regular_sleeve_authority_sha256"]
        )
        assert (
            bindings["economic_risk_authorization_sha256"]
            == bindings["expected_economic_risk_authorization_sha256"]
        )
    finally:
        db.close()
