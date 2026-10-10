from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.canary_authority import CanaryLifecycleRecorder
from ibkr_paper_30d.multi_universe_models import ProductFamilyKey
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.product_capability import (
    CERTIFICATION_SEQUENCE,
    ExtendedAvailabilityGate,
    ProductCapabilityError,
    ProductCapabilityEvidence,
    ProductFamilyCertificationStatus,
    ProductFamilyCertificationStore,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
ACCOUNT = "a" * 64
ADAPTER = "b" * 64


def _family(sec_type="STK", venue="SMART"):
    return ProductFamilyKey(
        security_type=sec_type,
        venue_or_routing=venue,
        quantity_semantics="UNITS",
        order_representation="LIMIT",
        lifecycle_behavior="CASH_SETTLED",
    )


def _store(tmp_path, *, adapter=ADAPTER):
    db = Database.open(tmp_path / "capability.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    return db, ProductFamilyCertificationStore(db, current_adapter_sha256=adapter)


def _record(store, family, step):
    return store.record_step(
        family,
        step,
        (step.lower().encode().hex() + "0" * 64)[:64],
        account_sha256=ACCOUNT,
        adapter_sha256=ADAPTER,
        observed_at_utc=NOW,
        expires_at_utc=NOW + timedelta(days=1),
        paper_limitations=("PAPER_SIMULATION_ONLY",),
    )


def _full(store, family):
    for step in (
        "CONTRACT_QUALIFIED",
        "PERMISSIONS_VERIFIED",
        "MARKET_DATA_VERIFIED",
        "ORDER_SEMANTICS_VERIFIED",
        "BOUNDED_ECONOMICS_VERIFIED",
        "ORDER_TRANSMIT_VERIFIED",
        "ENTRY_FILL_VERIFIED",
        "POSITION_VISIBLE",
        "MANAGEMENT_OBSERVED",
        "CLOSING_FILL_VERIFIED",
        "FLAT_STATE_VERIFIED",
        "ECONOMICS_RECONCILED",
    ):
        _record(store, family, step)


def test_research_discovery_does_not_imply_execution_authority() -> None:
    evidence = ProductCapabilityEvidence(
        candidate={"symbol": "ARBITRARY", "secType": "FUT", "exchange": "GLOBEX"},
        paper_account_sha256=ACCOUNT,
        contract_qualified=True,
        permissions_verified=False,
        market_data_verified=True,
        order_semantics_verified=False,
        quantity_semantics_verified=False,
        bounded_economics_verified=False,
        paper_limitations=("PAPER_SIMULATION_ONLY",),
        observed_at_utc=NOW,
        expires_at_utc=NOW + timedelta(hours=1),
    )
    assert evidence.research_visible is True
    assert evidence.execution_ready is False


def test_no_fill_terminal_order_reaches_transmit_only(tmp_path) -> None:
    db, store = _store(tmp_path)
    family = _family()
    try:
        for step in (
            "CONTRACT_QUALIFIED",
            "PERMISSIONS_VERIFIED",
            "MARKET_DATA_VERIFIED",
            "ORDER_SEMANTICS_VERIFIED",
            "BOUNDED_ECONOMICS_VERIFIED",
            "ORDER_TRANSMIT_VERIFIED",
            "ORDER_TERMINAL_NO_FILL",
        ):
            _record(store, family, step)
        projection = store.projection(family)
        assert projection.status is ProductFamilyCertificationStatus.ORDER_TRANSMIT_VERIFIED
        with pytest.raises(ProductCapabilityError, match="FULL_LIFECYCLE_REQUIRED"):
            store.assert_executable(family, NOW, ACCOUNT)
    finally:
        db.close()


def test_only_ordered_full_lifecycle_reaches_full_certification(tmp_path) -> None:
    db, store = _store(tmp_path)
    family = _family()
    try:
        with pytest.raises(ProductCapabilityError, match="CERTIFICATION_STEP_OUT_OF_ORDER"):
            _record(store, family, "ENTRY_FILL_VERIFIED")
        _full(store, family)
        projection = store.projection(family)
        assert projection.status is ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED
        assert store.assert_executable(family, NOW, ACCOUNT).executable is True
        assert projection.paper_only is True
        assert "PAPER_SIMULATION_ONLY" in projection.paper_limitations
    finally:
        db.close()


def test_full_canary_projection_completes_family_but_no_fill_cannot(tmp_path) -> None:
    db, store = _store(tmp_path)
    family = _family("FUT", "GLOBEX")
    try:
        for step in CERTIFICATION_SEQUENCE[:6]:
            _record(store, family, step)
        recorder = CanaryLifecycleRecorder("canary-1", family.sha256, "c" * 64)
        recorder.record_submit("1" * 64)
        recorder.record_bind("2" * 64)
        no_fill = recorder.record_terminal_no_fill("3" * 64)
        with pytest.raises(ProductCapabilityError, match="CANARY_FULL_LIFECYCLE_REQUIRED"):
            store.record_canary_lifecycle(
                family,
                no_fill,
                account_sha256=ACCOUNT,
                adapter_sha256=ADAPTER,
                observed_at_utc=NOW,
                expires_at_utc=NOW + timedelta(days=1),
                paper_limitations=("PAPER_SIMULATION_ONLY",),
            )

        complete = CanaryLifecycleRecorder("canary-2", family.sha256, "c" * 64)
        complete.record_submit("1" * 64)
        complete.record_bind("2" * 64)
        complete.record_entry_fill("3" * 64)
        complete.record_position("4" * 64)
        complete.record_management("5" * 64)
        complete.record_exit_fill("6" * 64)
        complete.record_flat_state("7" * 64, open_orders=0, positions=0)
        projection = complete.record_economics("8" * 64, reconciled=True)
        certified = store.record_canary_lifecycle(
            family,
            projection,
            account_sha256=ACCOUNT,
            adapter_sha256=ADAPTER,
            observed_at_utc=NOW,
            expires_at_utc=NOW + timedelta(days=1),
            paper_limitations=("PAPER_SIMULATION_ONLY",),
        )

        assert certified.status is ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED
    finally:
        db.close()


def test_family_scope_account_adapter_staleness_and_revocation_are_local(tmp_path) -> None:
    db, store = _store(tmp_path)
    stock = _family()
    future = _family("FUT", "GLOBEX")
    try:
        _full(store, stock)
        assert store.projection(future).status is ProductFamilyCertificationStatus.RESEARCH_ONLY
        with pytest.raises(ProductCapabilityError, match="FAMILY_NOT_CERTIFIED"):
            store.assert_executable(future, NOW, ACCOUNT)
        with pytest.raises(ProductCapabilityError, match="ACCOUNT_MISMATCH"):
            store.assert_executable(stock, NOW, "c" * 64)
        with pytest.raises(ProductCapabilityError, match="CERTIFICATION_STALE"):
            store.assert_executable(stock, NOW + timedelta(days=2), ACCOUNT)

        changed = ProductFamilyCertificationStore(db, current_adapter_sha256="d" * 64)
        with pytest.raises(ProductCapabilityError, match="ADAPTER_MISMATCH"):
            changed.assert_executable(stock, NOW, ACCOUNT)

        store.revoke(stock, reason="ADAPTER_RETIRED")
        assert store.projection(stock).status is ProductFamilyCertificationStatus.REVOKED
        assert store.projection(future).status is ProductFamilyCertificationStatus.RESEARCH_ONLY
    finally:
        db.close()


def test_store_enumerates_each_durable_family_once(tmp_path) -> None:
    db, store = _store(tmp_path)
    stock = _family()
    future = _family("FUT", "GLOBEX")
    try:
        _record(store, stock, "CONTRACT_QUALIFIED")
        _record(store, future, "CONTRACT_QUALIFIED")

        projections = store.projections()

        assert {item.family_sha256 for item in projections} == {
            stock.sha256,
            future.sha256,
        }
    finally:
        db.close()


def test_initial_activation_requires_full_family_available_within_24_hours(tmp_path) -> None:
    db, store = _store(tmp_path)
    family = _family()
    try:
        _full(store, family)
        certification = store.projection(family)
        blocked = ExtendedAvailabilityGate.evaluate_initial_activation(
            [certification],
            {family.sha256: {"authenticated": True, "tradable_now": False, "next_open_utc": NOW + timedelta(hours=25)}},
            NOW,
        )
        passed = ExtendedAvailabilityGate.evaluate_initial_activation(
            [certification],
            {family.sha256: {"authenticated": True, "tradable_now": False, "next_open_utc": NOW + timedelta(hours=23)}},
            NOW,
        )
        assert blocked.status == "BLOCK"
        assert passed.status == "PASS"
    finally:
        db.close()


def test_ordinary_restart_on_holiday_preserves_supervision_and_idle(tmp_path) -> None:
    db, store = _store(tmp_path)
    family = _family()
    try:
        _full(store, family)
        certification = store.projection(family)
        idle = ExtendedAvailabilityGate.evaluate_runtime_session(
            [certification],
            {family.sha256: {"authenticated": True, "tradable_now": False, "next_open_utc": NOW + timedelta(days=3)}},
            {"exact_continuity_action_due": False},
            NOW,
        )
        due = ExtendedAvailabilityGate.evaluate_runtime_session(
            [certification],
            {},
            {"exact_continuity_action_due": True},
            NOW,
        )
        assert idle.status == "MARKET_CLOSED_IDLE"
        assert idle.reconciliation_enabled and idle.watchdog_enabled
        assert idle.position_supervision_enabled and idle.open_order_supervision_enabled
        assert idle.extended_entries_enabled is False
        assert idle.regular_decisions_enabled and idle.exits_enabled
        assert due.status == "CONTINUITY_ACTION_DUE"
        assert due.continuity_actions_enabled is True
    finally:
        db.close()
