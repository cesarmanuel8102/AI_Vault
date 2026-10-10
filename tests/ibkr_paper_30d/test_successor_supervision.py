from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.contract_ownership import (
    ContractOwnershipStore,
    canonical_contract_identity,
)
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    TransitionPhase,
    TransitionTarget,
)
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.multi_universe_transition import MultiUniverseTransitionCoordinator
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.successor_supervision import (
    SuccessorSupervisionBinder,
    SupervisionBindingError,
    build_supervision_binding_plan,
)


def _target() -> TransitionTarget:
    return TransitionTarget(
        transition_id="transition-supervision-1",
        predecessor_epoch_id="AUTONOMY_EPOCH_2",
        successor_epoch_id="AUTONOMY_EPOCH_3",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head="3" * 40,
        account_identity_sha256="4" * 64,
        clock_authority_sha256="5" * 64,
        regular_sleeve_authority_sha256="6" * 64,
        continuous_sleeve_authority_sha256="7" * 64,
        economic_risk_authorization_sha256="8" * 64,
        certified_family_set_sha256="9" * 64,
        canary_authorization_sha256="a" * 64,
        writer_binding_sha256="b" * 64,
    )


def _evidence(phase: TransitionPhase) -> dict[str, object]:
    evidence: dict[str, object] = {
        "phase_evidence_sha256": sha256_json({"phase": phase.value}),
        "canary_flat": True,
        "continuity_exact": True,
    }
    if phase is TransitionPhase.PREDECESSOR_RETIRED:
        evidence.update(
            retirement_status="PASS",
            retirement_tombstone_sha256="c" * 64,
        )
    if phase is TransitionPhase.SUCCESSOR_COMMITTED:
        evidence["successor_commit_sha256"] = "d" * 64
    return evidence


def _open_committed(path) -> Database:
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    coordinator = MultiUniverseTransitionCoordinator(db)
    coordinator.prepare(_target())
    for phase in (
        TransitionPhase.PREDECESSOR_QUIESCED,
        TransitionPhase.PREDECESSOR_RETIRED,
        TransitionPhase.SUCCESSOR_COMMITTED,
    ):
        coordinator.advance(phase, _evidence(phase))
    return db


def _stock(con_id: int, symbol: str):
    return canonical_contract_identity(
        {
            "conId": con_id,
            "secType": "STK",
            "currency": "USD",
            "exchange": "SMART",
            "primaryExchange": "NASDAQ",
            "localSymbol": symbol,
            "tradingClass": "NMS",
            "multiplier": "1",
        }
    )


def _bag():
    parent = canonical_contract_identity(
        {
            "conId": 0,
            "secType": "BAG",
            "currency": "USD",
            "exchange": "SMART",
        },
        legs=(
            {"conId": 3001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
            {"conId": 3002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
        ),
    )
    legs = tuple(
        canonical_contract_identity(
            {
                "conId": con_id,
                "secType": "OPT",
                "currency": "USD",
                "exchange": "SMART",
                "localSymbol": f"TEST {con_id}",
                "tradingClass": "TEST",
                "multiplier": "100",
            }
        )
        for con_id in (3001, 3002)
    )
    return parent, legs


def _inputs(*, include_second: bool = False, include_bag: bool = False):
    contracts = [(_stock(1001, "TEST"), Decimal("1.25"), Decimal("118.60"))]
    if include_second:
        contracts.append((_stock(1002, "NEXT"), Decimal("2"), Decimal("35.125")))
    bag_parent = None
    bag_legs = ()
    if include_bag:
        bag_parent, bag_legs = _bag()
        contracts.append((bag_parent, Decimal("1"), Decimal("3.50")))

    positions = []
    day1_positions = []
    historical = []
    for index, (contract, quantity, average_cost) in enumerate(contracts, start=1):
        members = (contract,) if contract is not bag_parent else (contract, *bag_legs)
        fill_hash = f"{index:x}" * 64
        historical.append(fill_hash)
        positions.append(
            {
                "contract": contract.model_dump(mode="json"),
                "ownership_members": [item.model_dump(mode="json") for item in members],
                "group_id": f"inherited-{index}",
                "quantity": str(quantity),
                "multiplier": str(contract.multiplier or Decimal("1")),
                "average_cost": str(average_cost),
                "mark": str(average_cost + Decimal("1.25")),
                "market_value_usd": str(
                    quantity
                    * (contract.multiplier or Decimal("1"))
                    * (average_cost + Decimal("1.25"))
                ),
            }
        )
        day1_positions.append(
            {
                "contract_identity_sha256": contract.sha256,
                "group_id": f"inherited-{index}",
                "quantity": str(quantity),
                "average_cost": str(average_cost),
                "historical_fill_sha256": [fill_hash],
                "lineage_sha256": sha256_json(
                    {"contract": contract.sha256, "fill": fill_hash}
                ),
            }
        )

    broker = {
        "account_identity_sha256": "4" * 64,
        "writer_binding_sha256": "b" * 64,
        "execution_lock_generation": 46,
        "observed_at_utc": "2026-10-10T16:00:00Z",
        "positions": positions,
        "open_orders": [],
        "executions": [
            {
                "execution_id_hash": hash_value,
                "contract_identity_sha256": position["contract_identity_sha256"],
                "commission": "0.625",
            }
            for hash_value, position in zip(historical, day1_positions, strict=True)
        ],
        "fees_usd": str(Decimal("0.625") * len(historical)),
        "realized_pnl_usd": "12.50",
        "unrealized_pnl_usd": "7.75",
        "execution_ambiguity": False,
    }
    day1 = {
        "account_identity_sha256": "4" * 64,
        "transition_id": "transition-supervision-1",
        "writer_binding_sha256": "b" * 64,
        "execution_lock_generation": 46,
        "regular_sleeve_authority_sha256": "6" * 64,
        "allocation_usd": "500.00",
        "currency_balances": [{"currency": "USD", "amount": "25.60"}],
        "positions": day1_positions,
        "open_order_count": 0,
        "fill_count": len(historical),
        "fees_usd": str(Decimal("0.625") * len(historical)),
        "realized_pnl_usd": "12.50",
        "unrealized_pnl_usd": "7.75",
        "historical_event_sha256": historical,
        "source_ledger_sha256": "e" * 64,
        "day1_lineage_sha256": sha256_json(day1_positions),
    }
    return broker, day1


@pytest.mark.parametrize(
    ("include_second", "include_bag", "expected_positions", "expected_contracts"),
    [
        (False, False, 1, 1),
        (True, False, 2, 2),
        (False, True, 2, 4),
    ],
)
def test_exact_inherited_carry_is_bound_without_rebase(
    tmp_path, include_second, include_bag, expected_positions, expected_contracts
) -> None:
    broker, day1 = _inputs(include_second=include_second, include_bag=include_bag)
    plan = build_supervision_binding_plan(
        broker_snapshot=broker,
        day1_projection=day1,
        account_identity_sha256="4" * 64,
        transition_target_sha256=_target().sha256,
    )
    with _open_committed(tmp_path / "supervision.sqlite3") as db:
        receipt = SuccessorSupervisionBinder(db).bind(plan, deepcopy(broker))
        ledgers = SleeveLedgerStore(db).project_all()
        ownership = ContractOwnershipStore(db).projection()

        assert receipt.status == "PASS"
        assert len(ledgers.regular.positions) == expected_positions
        regular_by_contract = {
            item.contract_identity_sha256: item for item in ledgers.regular.positions
        }
        first_contract = canonical_contract_identity(
            broker["positions"][0]["contract"]
        )
        assert regular_by_contract[first_contract.sha256].quantity == Decimal("1.25")
        assert regular_by_contract[first_contract.sha256].average_cost == Decimal("118.60")
        assert ledgers.regular.fees_usd == Decimal(day1["fees_usd"])
        assert ledgers.regular.realized_pnl_usd == Decimal("12.50")
        assert ledgers.regular.unrealized_pnl_usd == Decimal("7.75")
        assert ledgers.regular.historical_event_sha256 == tuple(
            day1["historical_event_sha256"]
        )
        assert ledgers.continuous.allocation_usd == Decimal("500.00")
        assert ledgers.continuous.positions == ()
        assert ledgers.continuous.realized_pnl_usd == Decimal("0.00")
        assert ledgers.continuous.unrealized_pnl_usd == Decimal("0.00")
        assert len(ownership.active_contracts) == expected_contracts
        assert all(
            item.sleeve is CapitalSleeve.REGULAR_SLEEVE
            for item in ownership.active_contracts
        )
        assert MultiUniverseTransitionCoordinator(db).recover(_target()).phase is TransitionPhase.SUPERVISION_BOUND


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda broker, day1: broker["positions"].append(deepcopy(broker["positions"][0])), "UNATTRIBUTED_POSITION"),
        (
            lambda broker, day1: (
                day1["positions"][0].update(quantity="9"),
                day1.update(day1_lineage_sha256=sha256_json(day1["positions"])),
            ),
            "INHERITED_POSITION_MISMATCH",
        ),
        (
            lambda broker, day1: (
                day1["positions"][0].update(average_cost="9"),
                day1.update(day1_lineage_sha256=sha256_json(day1["positions"])),
            ),
            "INHERITED_POSITION_MISMATCH",
        ),
        (lambda broker, day1: broker["open_orders"].append({"order_id": 1}), "OPEN_ORDER_BLOCKS_SUPERVISION_BINDING"),
        (lambda broker, day1: broker.update(execution_ambiguity=True), "EXECUTION_STATE_AMBIGUOUS"),
        (lambda broker, day1: day1.update(day1_lineage_sha256="f" * 64), "INHERITED_LINEAGE_MISMATCH"),
        (lambda broker, day1: day1.update(fees_usd="99"), "INHERITED_ECONOMICS_MISMATCH"),
    ],
)
def test_invalid_inherited_state_fails_closed(mutate, reason) -> None:
    broker, day1 = _inputs()
    mutate(broker, day1)
    with pytest.raises(SupervisionBindingError, match=reason):
        build_supervision_binding_plan(
            broker_snapshot=broker,
            day1_projection=day1,
            account_identity_sha256="4" * 64,
            transition_target_sha256=_target().sha256,
        )


def test_changed_broker_snapshot_rolls_back_all_bootstrap_events(tmp_path) -> None:
    broker, day1 = _inputs()
    plan = build_supervision_binding_plan(
        broker_snapshot=broker,
        day1_projection=day1,
        account_identity_sha256="4" * 64,
        transition_target_sha256=_target().sha256,
    )
    fresh = deepcopy(broker)
    fresh["positions"][0]["quantity"] = "2"
    with _open_committed(tmp_path / "stale.sqlite3") as db:
        with pytest.raises(SupervisionBindingError, match="SUPERVISION_BINDING_STALE"):
            SuccessorSupervisionBinder(db).bind(plan, fresh)
        assert db.execute("SELECT COUNT(*) FROM sleeve_ledger_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM contract_ownership_events").fetchone()[0] == 0
        assert MultiUniverseTransitionCoordinator(db).recover(_target()).phase is TransitionPhase.SUCCESSOR_COMMITTED


def test_existing_continuous_claim_blocks_atomic_binding(tmp_path) -> None:
    broker, day1 = _inputs()
    plan = build_supervision_binding_plan(
        broker_snapshot=broker,
        day1_projection=day1,
        account_identity_sha256="4" * 64,
        transition_target_sha256=_target().sha256,
    )
    with _open_committed(tmp_path / "ownership-conflict.sqlite3") as db:
        contract = canonical_contract_identity(broker["positions"][0]["contract"])
        ContractOwnershipStore(db).claim(CapitalSleeve.CONTINUOUS_SLEEVE, contract)
        before = db.execute("SELECT COUNT(*) FROM contract_ownership_events").fetchone()[0]
        with pytest.raises(SupervisionBindingError, match="CONTRACT_OWNED_BY_OTHER_SLEEVE"):
            SuccessorSupervisionBinder(db).bind(plan, deepcopy(broker))
        assert db.execute("SELECT COUNT(*) FROM sleeve_ledger_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM contract_ownership_events").fetchone()[0] == before
        assert MultiUniverseTransitionCoordinator(db).recover(_target()).phase is TransitionPhase.SUCCESSOR_COMMITTED


def test_exact_retry_returns_same_supervision_receipt(tmp_path) -> None:
    broker, day1 = _inputs()
    plan = build_supervision_binding_plan(
        broker_snapshot=broker,
        day1_projection=day1,
        account_identity_sha256="4" * 64,
        transition_target_sha256=_target().sha256,
    )
    with _open_committed(tmp_path / "retry.sqlite3") as db:
        binder = SuccessorSupervisionBinder(db)
        first = binder.bind(plan, deepcopy(broker))
        retry = binder.bind(plan, deepcopy(broker))
        assert retry.idempotent is True
        assert retry.transition_event_sha256 == first.transition_event_sha256
        assert db.execute("SELECT COUNT(*) FROM sleeve_ledger_events").fetchone()[0] == 2
