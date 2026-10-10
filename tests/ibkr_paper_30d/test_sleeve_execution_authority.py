from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.coordinated_model_executor import ModelExecutionOperation
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.contract_ownership import canonical_contract_identity
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_execution_authority import (
    SleeveAuthorityReservationStore,
    SleeveAuthoritySnapshot,
    SleeveExecutionAuthorityValidator,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from test_model_execution_engine import _request


NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


def _v4_request(
    operation: ModelExecutionOperation = ModelExecutionOperation.NEW_TRADE,
):
    legacy = _request(operation)
    family = "f" * 64
    portfolio = {
        "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
        "sleeves": {"regular": {}, "extended": {}},
    }
    ownership = {"projection_sha256": "d" * 64, "contract_sleeves": {}}
    bundle = legacy.input_bundle.model_copy(
        update={
            "multi_sleeve_portfolio": portfolio,
            "contract_ownership_snapshot": ownership,
            "product_capability_snapshot": {"families": []},
        }
    )
    payload = legacy.payload.model_copy(
        update={
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "product_family_sha256": family,
        }
    )
    data = legacy.model_dump()
    data.update(
        {
            "payload": payload,
            "payload_sha256": sha256_json(payload),
            "input_bundle": bundle,
            "input_bundle_sha256": bundle.sha256,
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "sleeve_authority_sha256": sha256_json(portfolio),
            "ownership_projection_sha256": "d" * 64,
            "product_family_sha256": family,
        }
    )
    return legacy.__class__.model_validate(data)


def _claim_contract(db, request) -> None:
    evidence = _broker(request)
    contract = canonical_contract_identity(evidence["canonical_contract"])
    from ibkr_paper_30d.contract_ownership import ContractOwnershipStore

    ContractOwnershipStore(db).claim(
        request.capital_sleeve,
        contract,
        side="BUY",
        group_id="existing-position",
    )


def _snapshot(request, **changes):
    values = {
        "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
        "sleeve_authority_sha256": request.sleeve_authority_sha256,
        "ownership_projection_sha256": request.ownership_projection_sha256,
        "product_family_sha256": request.product_family_sha256,
        "economic_authorization_sha256": "e" * 64,
        "transition_target_sha256": "a" * 64,
        "epoch_id": request.epoch_id,
        "approved_head": request.approved_head,
        "account_identity_sha256": request.account_identity_sha256,
        "transition_phase": "ACTIVE",
        "paper_only": True,
        "family_executable": True,
        "capability_fresh": True,
        "ownership_conflict": False,
        "equity_usd": Decimal("500"),
        "reserved_liability_usd": Decimal("0"),
        "proposed_maximum_loss_usd": Decimal("1"),
        "continuity_required": False,
        "continuity_plan_sha256": None,
    }
    values.update(changes)
    return SleeveAuthoritySnapshot(**values)


def _broker(request, **changes):
    contract = canonical_contract_identity(
        {
            "conId": 756733,
            "secType": "STK",
            "currency": "USD",
            "exchange": "SMART",
            "primaryExchange": "ARCA",
            "localSymbol": "SPY",
            "tradingClass": "SPY",
        }
    )
    value = {
        "paper_only": True,
        "fresh": True,
        "account_identity_sha256": request.account_identity_sha256,
        "contract_identity_sha256": contract.sha256,
        "canonical_contract": contract.model_dump(mode="json"),
        "observed_at_utc": NOW,
    }
    value.update(changes)
    return value


def _bag_broker(request, **changes):
    parent = canonical_contract_identity(
        {
            "conId": 9000,
            "secType": "BAG",
            "currency": "USD",
            "exchange": "SMART",
            "comboLegs": [
                {"conId": 9001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
                {"conId": 9002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
            ],
        }
    )
    leg_one = canonical_contract_identity(
        {
            "conId": 9001,
            "secType": "OPT",
            "currency": "USD",
            "exchange": "SMART",
            "localSymbol": "SPY  C9001",
            "tradingClass": "SPY",
            "multiplier": "100",
        }
    )
    leg_two = canonical_contract_identity(
        {
            "conId": 9002,
            "secType": "OPT",
            "currency": "USD",
            "exchange": "SMART",
            "localSymbol": "SPY  C9002",
            "tradingClass": "SPY",
            "multiplier": "100",
        }
    )
    value = _broker(
        request,
        contract_identity_sha256=parent.sha256,
        canonical_contract=parent.model_dump(mode="json"),
        ownership_contracts=[
            parent.model_dump(mode="json"),
            leg_one.model_dump(mode="json"),
            leg_two.model_dump(mode="json"),
        ],
    )
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"family_executable": False}, "PRODUCT_FAMILY_NOT_EXECUTABLE"),
        ({"capability_fresh": False}, "PRODUCT_CAPABILITY_STALE"),
        ({"ownership_conflict": True}, "CONTRACT_OWNERSHIP_CONFLICT"),
        ({"external_capital_offset_detected": True}, "CROSS_SLEEVE_OR_EXTERNAL_OFFSET_FORBIDDEN"),
        ({"unbounded_liability": True}, "MAXIMUM_LOSS_UNBOUNDED"),
        ({"economic_authorization_valid": False}, "OWNER_ECONOMIC_RISK_AUTHORIZATION_INVALID"),
        ({"paper_only": False}, "NON_PAPER_AUTHORITY"),
        ({"approved_head": "9" * 40}, "APPROVED_HEAD_MISMATCH"),
        ({"epoch_id": "wrong"}, "EPOCH_MISMATCH"),
        ({"transition_phase": "CANARY_PASS"}, "SUCCESSOR_NOT_ACTIVE"),
        ({"proposed_maximum_loss_usd": Decimal("501")}, "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED"),
        ({"reserved_liability_usd": Decimal("500")}, "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED"),
    ],
)
def test_gate_matrix_blocks_each_independent_authority_failure(changes, reason):
    request = _v4_request()
    receipt = SleeveExecutionAuthorityValidator.validate(
        request, _broker(request), _snapshot(request, **changes)
    )
    assert receipt.status == "BLOCK"
    assert reason in receipt.reason_codes


def test_non_paper_or_wrong_account_broker_evidence_blocks() -> None:
    request = _v4_request()
    for evidence, reason in (
        (_broker(request, paper_only=False), "BROKER_NOT_PAPER"),
        (_broker(request, fresh=False), "BROKER_EVIDENCE_STALE"),
        (_broker(request, account_identity_sha256="d" * 64), "BROKER_ACCOUNT_MISMATCH"),
    ):
        receipt = SleeveExecutionAuthorityValidator.validate(
            request, evidence, _snapshot(request)
        )
        assert reason in receipt.reason_codes


def test_missing_continuity_plan_blocks_when_snapshot_requires_it() -> None:
    request = _v4_request()
    receipt = SleeveExecutionAuthorityValidator.validate(
        request,
        _broker(request),
        _snapshot(request, continuity_required=True),
    )
    assert "CONTINUITY_PLAN_REQUIRED" in receipt.reason_codes


def test_reservation_rereads_inside_transaction_and_is_exactly_idempotent(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "authority.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    store = SleeveAuthorityReservationStore(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    SleeveLedgerStore(db).bootstrap_extended()
    calls = []

    def reader():
        calls.append(db.connection.in_transaction)
        return _snapshot(request)

    try:
        first = store.reserve(request, _broker(request), reader)
        second = store.reserve(request, _broker(request), reader)
        assert first.status == second.status == "PASS"
        assert second.idempotent is True
        assert calls == [True]
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM sleeve_ledger_events WHERE event_type='LIABILITY_RESERVED'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM contract_ownership_events").fetchone()[0] == 1
    finally:
        db.close()


def test_db_state_change_after_broker_collection_blocks_without_reservation(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "race.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    store = SleeveAuthorityReservationStore(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    SleeveLedgerStore(db).bootstrap_extended()
    try:
        receipt = store.reserve(
            request,
            _broker(request),
            lambda: _snapshot(request, ownership_projection_sha256="e" * 64),
        )
        assert receipt.status == "BLOCK"
        assert "OWNERSHIP_PROJECTION_MISMATCH" in receipt.reason_codes
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 0
    finally:
        db.close()


def test_distinct_request_cannot_reuse_stale_sleeve_capacity(tmp_path) -> None:
    first = _v4_request()
    second = first.model_copy(
        update={
            "request_id": "second-request",
            "execution_key": "second-execution",
            "durable_sequence": first.durable_sequence + 1,
        }
    )
    db = Database.open(tmp_path / "stale-capacity.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    SleeveLedgerStore(db).bootstrap_extended()
    store = SleeveAuthorityReservationStore(db)
    try:
        assert store.reserve(first, _broker(first), lambda: _snapshot(first)).status == "PASS"
        blocked = store.reserve(second, _broker(second), lambda: _snapshot(second))
        assert blocked.status == "BLOCK"
        assert "SLEEVE_LEDGER_RESERVATION_MISMATCH" in blocked.reason_codes
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM sleeve_ledger_events WHERE event_type='LIABILITY_RESERVED'").fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "operation",
    (
        ModelExecutionOperation.OPEN_ORDER_ACTION,
        ModelExecutionOperation.POSITION_ACTION,
    ),
)
def test_existing_exposure_action_does_not_reclaim_or_reserve_liability(
    tmp_path, operation
) -> None:
    request = _v4_request(operation)
    db = Database.open(tmp_path / f"{operation.value}.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    _claim_contract(db, request)
    store = SleeveAuthorityReservationStore(db)
    try:
        receipt = store.reserve(
            request,
            _broker(request),
            lambda: _snapshot(
                request,
                proposed_maximum_loss_usd=Decimal("0"),
            ),
        )

        assert receipt.status == "PASS"
        assert db.execute(
            "SELECT COUNT(*) FROM contract_ownership_events"
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_ledger_events "
            "WHERE event_type='LIABILITY_RESERVED'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_authority_events"
        ).fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "operation",
    (
        ModelExecutionOperation.OPEN_ORDER_ACTION,
        ModelExecutionOperation.POSITION_ACTION,
    ),
)
def test_existing_exposure_action_requires_same_sleeve_ownership(
    tmp_path, operation
) -> None:
    request = _v4_request(operation)
    db = Database.open(tmp_path / f"missing-{operation.value}.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    store = SleeveAuthorityReservationStore(db)
    try:
        receipt = store.reserve(
            request,
            _broker(request),
            lambda: _snapshot(
                request,
                proposed_maximum_loss_usd=Decimal("0"),
            ),
        )

        assert receipt.status == "BLOCK"
        assert receipt.reason_codes == ("CONTRACT_OWNERSHIP_REQUIRED",)
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_authority_events"
        ).fetchone()[0] == 0
    finally:
        db.close()


def test_terminal_reconciliation_requires_two_observations_then_releases(
    tmp_path,
) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "terminal-release.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.contract_ownership import ContractOwnershipStore
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    store = SleeveAuthorityReservationStore(db)
    flat = {
        "positions": [],
        "open_orders": [],
        "pending_execution_contract_sha256": [],
        "fill_ambiguity": False,
        "fresh": True,
    }
    try:
        assert store.reserve(
            request, _broker(request), lambda: _snapshot(request)
        ).status == "PASS"

        first = store.finalize_terminal_reservations(
            flat,
            observation_id="1" * 64,
        )
        assert first == {"released": (), "pending_confirmation": (request.execution_key,)}
        assert SleeveLedgerStore(db).project(
            CapitalSleeve.EXTENDED_SLEEVE
        ).reserved_liability_usd == Decimal("1")

        second = store.finalize_terminal_reservations(
            flat,
            observation_id="2" * 64,
        )
        assert second == {"released": (request.execution_key,), "pending_confirmation": ()}
        assert SleeveLedgerStore(db).project(
            CapitalSleeve.EXTENDED_SLEEVE
        ).reserved_liability_usd == Decimal("0")
        ownership = ContractOwnershipStore(db).projection()
        assert ownership.active_contracts == ()
        assert len(ownership.released_contracts) == 1

        retry = store.finalize_terminal_reservations(
            flat,
            observation_id="3" * 64,
        )
        assert retry == {"released": (), "pending_confirmation": ()}
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_ledger_events "
            "WHERE event_type='LIABILITY_RELEASED'"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_terminal_reconciliation_releases_every_reservation_for_same_contract(
    tmp_path,
) -> None:
    first_request = _v4_request()
    second_request = first_request.model_copy(
        update={
            "request_id": "second-request",
            "execution_key": "second-execution",
            "durable_sequence": first_request.durable_sequence + 1,
        }
    )
    db = Database.open(tmp_path / "terminal-multiple-reservations.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.contract_ownership import ContractOwnershipStore
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    ledger = SleeveLedgerStore(db)
    ledger.bootstrap_extended()
    store = SleeveAuthorityReservationStore(db)
    flat = {
        "positions": [],
        "open_orders": [],
        "pending_execution_contract_sha256": [],
        "fill_ambiguity": False,
        "fresh": True,
    }
    try:
        assert store.reserve(
            first_request,
            _broker(first_request),
            lambda: _snapshot(first_request),
        ).status == "PASS"
        assert store.reserve(
            second_request,
            _broker(second_request),
            lambda: _snapshot(
                second_request,
                reserved_liability_usd=Decimal("1"),
            ),
        ).status == "PASS"
        assert ledger.project(
            CapitalSleeve.EXTENDED_SLEEVE
        ).reserved_liability_usd == Decimal("2")

        first = store.finalize_terminal_reservations(
            flat,
            observation_id="1" * 64,
        )
        assert first == {
            "released": (),
            "pending_confirmation": (
                first_request.execution_key,
                second_request.execution_key,
            ),
        }

        second = store.finalize_terminal_reservations(
            flat,
            observation_id="2" * 64,
        )
        assert second == {
            "released": (
                first_request.execution_key,
                second_request.execution_key,
            ),
            "pending_confirmation": (),
        }
        assert ledger.project(
            CapitalSleeve.EXTENDED_SLEEVE
        ).reserved_liability_usd == Decimal("0")
        ownership = ContractOwnershipStore(db).projection()
        assert ownership.active_contracts == ()
        assert len(ownership.released_contracts) == 1
        assert db.execute(
            "SELECT COUNT(*) FROM sleeve_ledger_events "
            "WHERE event_type='LIABILITY_RELEASED'"
        ).fetchone()[0] == 2

        retry = store.finalize_terminal_reservations(
            flat,
            observation_id="3" * 64,
        )
        assert retry == {"released": (), "pending_confirmation": ()}
    finally:
        db.close()


def test_terminal_reconciliation_never_releases_visible_exposure(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "active-exposure.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    store = SleeveAuthorityReservationStore(db)
    contract_hash = _broker(request)["contract_identity_sha256"]
    active = {
        "positions": [
            {"contract_identity_sha256": contract_hash, "quantity": "1"}
        ],
        "open_orders": [],
        "pending_execution_contract_sha256": [],
        "fill_ambiguity": False,
        "fresh": True,
    }
    try:
        store.reserve(request, _broker(request), lambda: _snapshot(request))
        for index in range(1, 4):
            result = store.finalize_terminal_reservations(
                active,
                observation_id=str(index) * 64,
            )
            assert result == {"released": (), "pending_confirmation": ()}
        assert SleeveLedgerStore(db).project(
            CapitalSleeve.EXTENDED_SLEEVE
        ).reserved_liability_usd == Decimal("1")
    finally:
        db.close()


def test_bag_entry_atomically_reserves_parent_and_every_leg(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "bag-reservation.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.contract_ownership import ContractOwnershipStore
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    try:
        receipt = SleeveAuthorityReservationStore(db).reserve(
            request,
            _bag_broker(request),
            lambda: _snapshot(request),
        )

        assert receipt.status == "PASS"
        projection = ContractOwnershipStore(db).projection()
        assert len(projection.active_contracts) == 3
        assert {item.contract.con_id for item in projection.active_contracts} == {
            9000,
            9001,
            9002,
        }
        assert len({item.group_id for item in projection.active_contracts}) == 1

        flat = {
            "positions": [],
            "open_orders": [],
            "pending_execution_contract_sha256": [],
            "fill_ambiguity": False,
            "fresh": True,
        }
        store = SleeveAuthorityReservationStore(db)
        store.finalize_terminal_reservations(flat, observation_id="1" * 64)
        store.finalize_terminal_reservations(flat, observation_id="2" * 64)
        terminal = ContractOwnershipStore(db).projection()
        assert terminal.active_contracts == ()
        assert len(terminal.released_contracts) == 3
    finally:
        db.close()


def test_bag_entry_blocks_if_any_leg_identity_is_missing(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "bag-incomplete.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

    SleeveLedgerStore(db).bootstrap_extended()
    evidence = _bag_broker(request)
    evidence["ownership_contracts"] = evidence["ownership_contracts"][:-1]
    try:
        receipt = SleeveAuthorityReservationStore(db).reserve(
            request,
            evidence,
            lambda: _snapshot(request),
        )
        assert receipt.status == "BLOCK"
        assert receipt.reason_codes == ("BAG_OWNERSHIP_EVIDENCE_INCOMPLETE",)
        assert db.execute(
            "SELECT COUNT(*) FROM contract_ownership_events"
        ).fetchone()[0] == 0
    finally:
        db.close()
