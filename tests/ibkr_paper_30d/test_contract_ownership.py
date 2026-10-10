from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.contract_ownership import (
    BrokerLineageEvidence,
    ContractOwnershipStore,
    OwnershipError,
    ReleaseEvidence,
    canonical_contract_identity,
)
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    ContractOwnershipGroup,
)
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _install(path) -> None:
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)


def _contract(con_id: int = 1001, *, sec_type: str = "STK"):
    return canonical_contract_identity(
        {
            "conId": con_id,
            "secType": sec_type,
            "currency": "USD",
            "exchange": "SMART",
            "primaryExchange": "NASDAQ",
            "localSymbol": "TEST",
            "tradingClass": "NMS",
            "multiplier": "1",
        }
    )


def test_canonical_identity_accepts_mapping_and_binds_bag_legs() -> None:
    bag = canonical_contract_identity(
        {"conId": 0, "secType": "BAG", "currency": "USD", "exchange": "SMART"},
        legs=(
            {"conId": 2001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
            {"conId": 2002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
        ),
    )
    changed = canonical_contract_identity(
        {"conId": 0, "secType": "BAG", "currency": "USD", "exchange": "SMART"},
        legs=(
            {"conId": 2001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
            {"conId": 2003, "ratio": 1, "action": "SELL", "exchange": "SMART"},
        ),
    )
    assert bag.sha256 != changed.sha256
    assert tuple(leg.con_id for leg in bag.bag_legs) == (2001, 2002)


def test_same_contract_and_opposite_side_cannot_cross_sleeves(tmp_path) -> None:
    path = tmp_path / "ownership.sqlite3"
    _install(path)
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        first = store.claim(CapitalSleeve.REGULAR_SLEEVE, _contract(), side="BUY")
        assert first.status == "CLAIMED"
        with pytest.raises(OwnershipError, match="CONTRACT_OWNED_BY_OTHER_SLEEVE"):
            store.claim(CapitalSleeve.EXTENDED_SLEEVE, _contract(), side="SELL")


def test_simultaneous_contenders_create_exactly_one_claim(tmp_path) -> None:
    path = tmp_path / "race.sqlite3"
    _install(path)
    barrier = Barrier(2)

    def contender(sleeve: CapitalSleeve) -> str:
        with Database.open(path) as db:
            barrier.wait()
            try:
                return ContractOwnershipStore(db).claim(sleeve, _contract()).status
            except OwnershipError as exc:
                return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                contender,
                (CapitalSleeve.REGULAR_SLEEVE, CapitalSleeve.EXTENDED_SLEEVE),
            )
        )
    assert sorted(results) == ["CLAIMED", "CONTRACT_OWNED_BY_OTHER_SLEEVE"]

    with Database.open(path) as db:
        assert len(ContractOwnershipStore(db).projection().active_contracts) == 1


def test_bag_parent_and_legs_reserve_one_group(tmp_path) -> None:
    path = tmp_path / "bag.sqlite3"
    _install(path)
    parent = canonical_contract_identity(
        {"conId": 3000, "secType": "BAG", "currency": "USD", "exchange": "SMART"},
        legs=(
            {"conId": 3001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
            {"conId": 3002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
        ),
    )
    leg1 = _contract(3001, sec_type="OPT")
    leg2 = _contract(3002, sec_type="OPT")
    group = ContractOwnershipGroup(
        group_id="spread-1",
        sleeve=CapitalSleeve.EXTENDED_SLEEVE,
        parent_contract=parent,
        member_contracts=(parent, leg1, leg2),
        generation=1,
    )
    with Database.open(path) as db:
        receipt = ContractOwnershipStore(db).reserve_group(group)
        projection = ContractOwnershipStore(db).projection()
        assert receipt.status == "GROUP_RESERVED"
        assert {item.group_id for item in projection.active_contracts} == {"spread-1"}
        assert {item.contract_identity_sha256 for item in projection.active_contracts} == {
            parent.sha256,
            leg1.sha256,
            leg2.sha256,
        }


def test_group_retry_requires_exact_generation_hash(tmp_path) -> None:
    path = tmp_path / "group-retry.sqlite3"
    _install(path)
    contract = _contract(3101)
    original = ContractOwnershipGroup(
        group_id="group-1",
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        parent_contract=contract,
        member_contracts=(contract,),
        generation=1,
    )
    changed = original.model_copy(update={"generation": 2})
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        store.reserve_group(original)
        with pytest.raises(OwnershipError, match="CONTRACT_GROUP_CONFLICT"):
            store.reserve_group(changed)


def test_currency_codes_are_nonexclusive_and_not_persisted(tmp_path) -> None:
    path = tmp_path / "currency.sqlite3"
    _install(path)
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        first = store.claim(CapitalSleeve.REGULAR_SLEEVE, "USD")
        second = store.claim(CapitalSleeve.EXTENDED_SLEEVE, "USD")
        assert first.status == second.status == "NON_EXCLUSIVE_CURRENCY_BALANCE"
        assert store.projection().active_contracts == ()


@pytest.mark.parametrize(
    "event_type",
    [
        "OPTION_EXERCISE",
        "OPTION_ASSIGNMENT",
        "EXPIRATION_SETTLEMENT",
        "FUTURES_SETTLEMENT",
        "SPLIT",
        "MERGER",
        "SPIN_OFF",
        "CONTRACT_REPLACEMENT",
        "BROKER_CORRECTION",
    ],
)
def test_verified_broker_descendants_inherit_source_sleeve(tmp_path, event_type) -> None:
    path = tmp_path / f"{event_type}.sqlite3"
    _install(path)
    source = _contract(4001, sec_type="OPT")
    descendant = _contract(5001)
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        store.claim(CapitalSleeve.REGULAR_SLEEVE, source)
        receipt = store.record_descendant(
            descendant=descendant,
            evidence=BrokerLineageEvidence(
                source_contract_sha256=source.sha256,
                descendant_contract_sha256=descendant.sha256,
                lineage_event=event_type,
                broker_event_id=f"event-{event_type}",
                broker_snapshot_sha256="e" * 64,
                observed_at_utc="2026-10-09T18:00:00Z",
            ),
        )
        assert receipt.status == "DESCENDANT_CLAIMED"
        record = store.projection().owner_of(descendant.sha256)
        assert record is not None
        assert record.sleeve is CapitalSleeve.REGULAR_SLEEVE


def test_unverified_descendant_is_unattributed_and_not_claimed(tmp_path) -> None:
    path = tmp_path / "unattributed.sqlite3"
    _install(path)
    with Database.open(path) as db:
        with pytest.raises(TypeError):
            ContractOwnershipStore(db).record_descendant(
                source_contract_sha256="a" * 64,
                descendant=_contract(6001),
                lineage_event="BROKER_CORRECTION",
                lineage_verified=True,
            )
        assert ContractOwnershipStore(db).projection().active_contracts == ()


def test_lineage_receipt_must_bind_exact_descendant(tmp_path) -> None:
    path = tmp_path / "lineage-mismatch.sqlite3"
    _install(path)
    source = _contract(4001, sec_type="OPT")
    descendant = _contract(5001)
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        store.claim(CapitalSleeve.REGULAR_SLEEVE, source)
        receipt = store.record_descendant(
            descendant=descendant,
            evidence=BrokerLineageEvidence(
                source_contract_sha256=source.sha256,
                descendant_contract_sha256="f" * 64,
                lineage_event="OPTION_ASSIGNMENT",
                broker_event_id="assignment-1",
                broker_snapshot_sha256="e" * 64,
                observed_at_utc="2026-10-09T18:00:00Z",
            ),
        )
        assert receipt.status == "BLOCK"
        assert receipt.reason_codes == ("LINEAGE_EVIDENCE_MISMATCH",)


def _release(**updates) -> ReleaseEvidence:
    base = ReleaseEvidence(
        position_quantity=Decimal("0"),
        open_order_count=0,
        pending_execution_count=0,
        child_position_count=0,
        fill_ambiguity=False,
        broker_snapshot_sha256="f" * 64,
        expected_broker_snapshot_sha256="f" * 64,
        broker_snapshot_fresh=True,
    )
    return base.model_copy(update=updates)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"position_quantity": Decimal("1")}, "POSITION_REMAINS"),
        ({"open_order_count": 1}, "OPEN_ORDER_REMAINS"),
        ({"pending_execution_count": 1}, "PENDING_EXECUTION_REMAINS"),
        ({"child_position_count": 1}, "CHILD_POSITION_REMAINS"),
        ({"fill_ambiguity": True}, "FILL_STATE_AMBIGUOUS"),
        ({"broker_snapshot_fresh": False}, "BROKER_SNAPSHOT_STALE"),
        ({"broker_snapshot_sha256": "e" * 64}, "BROKER_RECONCILIATION_MISMATCH"),
    ],
)
def test_release_requires_exact_terminal_broker_reconciliation(
    tmp_path, updates, reason
) -> None:
    path = tmp_path / f"release-{reason}.sqlite3"
    _install(path)
    contract = _contract()
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        store.claim(CapitalSleeve.REGULAR_SLEEVE, contract)
        with pytest.raises(OwnershipError, match=reason):
            store.release(contract.sha256, _release(**updates))


def test_exact_terminal_release_is_idempotent(tmp_path) -> None:
    path = tmp_path / "release.sqlite3"
    _install(path)
    contract = _contract()
    with Database.open(path) as db:
        store = ContractOwnershipStore(db)
        store.claim(CapitalSleeve.REGULAR_SLEEVE, contract)
        first = store.release(contract.sha256, _release())
        retry = store.release(contract.sha256, _release())
        assert first.status == "RELEASED"
        assert retry.idempotent is True
        assert retry.event_sha256 == first.event_sha256
        assert store.projection().owner_of(contract.sha256) is None
