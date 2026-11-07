from __future__ import annotations

import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import capital_equity_for_sleeve
from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.coordinated_model_executor import ModelExecutionOperation
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.production_continuity_runtime import (
    _ProductionSleeveAuthoritySnapshotReader,
)
from ibkr_paper_30d.sleeve_execution_authority import SleeveExecutionAuthorityValidator
from ibkr_paper_30d.sleeve_ledger import (
    CurrencyBalance,
    SleeveLedgerState,
    SleeveLedgerStore,
    authoritative_sleeve_equity,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from test_sleeve_execution_authority import _broker, _snapshot, _v4_request

CONTRACT = "c" * 64
AUTHORITY = "a" * 64


def _state(cash: str, *, positions=(), valuation="FRESH", other=(), **extra) -> SleeveLedgerState:
    values = dict(
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        initialized=True,
        allocation_usd=Decimal("500.00"),
        currency_balances=(CurrencyBalance(currency="USD", amount=Decimal(cash)), *other),
        positions=tuple(positions),
        open_order_count=0,
        fill_count=0,
        fees_usd=Decimal("0"),
        realized_pnl_usd=Decimal("0"),
        unrealized_pnl_usd=Decimal("0"),
        reserved_liability_usd=Decimal("0.00"),
        historical_event_sha256=(),
        source_ledger_sha256=None,
        event_count=1,
        valuation_status=valuation,
    )
    values.update(extra)
    return SleeveLedgerState(**values)


def _store(tmp_path):
    from ibkr_paper_30d.sleeve_ledger import RegularCarryForward

    db = Database.open(tmp_path / "sleeves.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    store = SleeveLedgerStore(db)
    store.bootstrap_regular(
        RegularCarryForward(
            allocation_usd=Decimal("500.00"),
            currency_balances=(CurrencyBalance(currency="USD", amount=Decimal("500.00")),),
            positions=(),
            open_order_count=0,
            fill_count=0,
            fees_usd=Decimal("0"),
            realized_pnl_usd=Decimal("0"),
            unrealized_pnl_usd=Decimal("0"),
            historical_event_sha256=(),
            source_ledger_sha256="a" * 64,
        )
    )
    return db, store


def _fill(action: str, qty: str, price: str, commission: str, execution: str) -> dict:
    return {
        "execution_id_sha256": execution * 64,
        "order_ref": f"codex-ibkr-paper-30d-a-{execution * 12}",
        "contract_identity_sha256": CONTRACT,
        "action": action,
        "quantity": qty,
        "price": price,
        "multiplier": "1",
        "commission_usd": commission,
        "authority_event_sha256": [AUTHORITY],
    }


def _reconcile(store, positions):
    store.reconcile_broker_snapshot(
        {"positions": positions, "open_orders": [], "executions": []},
        {"active_contracts": [{"contract_identity_sha256": CONTRACT, "sleeve": "CONTINUOUS_SLEEVE"}]},
    )


def test_audited_flat_state_equity_equals_cash_for_both_sleeves() -> None:
    regular = _state(
        "514.2260692",
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        fees_deductible_usd=Decimal("13.2939308"),
    )
    continuous = _state(
        "463.215114",
        realized_pnl_usd=Decimal("-10.701886"),
        fees_deductible_usd=Decimal("24.50"),
    )

    assert authoritative_sleeve_equity(regular).equity_usd == Decimal("514.2260692")
    assert authoritative_sleeve_equity(continuous).equity_usd == Decimal("463.215114")
    assert authoritative_sleeve_equity(regular).status == "FRESH"


def test_closed_round_trip_profit_is_in_cash_and_commissions_count_once(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        store.bootstrap_extended()
        store.import_model_fill(CapitalSleeve.CONTINUOUS_SLEEVE, _fill("BUY", "10", "10", "1.75", "1"))
        _reconcile(store, [{
            "contract_identity_sha256": CONTRACT, "quantity": "10", "multiplier": "1",
            "average_cost": "10", "mark": "11", "market_value_usd": "110", "mark_fresh": True,
        }])
        store.import_model_fill(CapitalSleeve.CONTINUOUS_SLEEVE, _fill("SELL", "10", "12", "1.75", "2"))
        _reconcile(store, [])
        state = store.project(CapitalSleeve.CONTINUOUS_SLEEVE)

        valuation = authoritative_sleeve_equity(state)
        assert valuation.equity_usd == Decimal("516.50")
        assert valuation.cash_usd == Decimal("516.50")
    finally:
        db.close()


def test_open_position_equity_is_cash_plus_fresh_market_value(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        store.bootstrap_extended()
        store.import_model_fill(CapitalSleeve.CONTINUOUS_SLEEVE, _fill("BUY", "10", "10", "1.75", "1"))
        _reconcile(store, [{
            "contract_identity_sha256": CONTRACT, "quantity": "10", "multiplier": "1",
            "average_cost": "10.175", "mark": "11", "market_value_usd": "110", "mark_fresh": True,
        }])
        valuation = authoritative_sleeve_equity(store.project(CapitalSleeve.CONTINUOUS_SLEEVE))

        assert valuation.status == "FRESH"
        assert valuation.cash_usd == Decimal("398.25")
        assert valuation.positions_market_value_usd == Decimal("110")
        assert valuation.equity_usd == Decimal("508.25")
    finally:
        db.close()


def test_position_without_fresh_mark_makes_equity_unavailable(tmp_path) -> None:
    db, store = _store(tmp_path)
    try:
        store.bootstrap_extended()
        store.import_model_fill(CapitalSleeve.CONTINUOUS_SLEEVE, _fill("BUY", "10", "10", "1.75", "1"))
        _reconcile(store, [{
            "contract_identity_sha256": CONTRACT, "quantity": "10", "multiplier": "1",
            "average_cost": "10", "mark": "0", "market_value_usd": "0", "mark_fresh": False,
        }])
        valuation = authoritative_sleeve_equity(store.project(CapitalSleeve.CONTINUOUS_SLEEVE))

        assert valuation.status == "UNAVAILABLE"
        assert valuation.equity_usd is None
        assert valuation.available_capital_usd is None
        assert "SLEEVE_FRESH_VALUATION_REQUIRED" in valuation.reason_codes
    finally:
        db.close()


def test_non_usd_balance_without_fx_makes_equity_unavailable() -> None:
    valuation = authoritative_sleeve_equity(
        _state("400", other=(CurrencyBalance(currency="EUR", amount=Decimal("40")),))
    )

    assert valuation.status == "UNAVAILABLE"
    assert valuation.equity_usd is None
    assert "SLEEVE_FX_VALUATION_REQUIRED" in valuation.reason_codes


def test_available_capital_subtracts_reserved_liability() -> None:
    valuation = authoritative_sleeve_equity(
        _state("463.215114", reserved_liability_usd=Decimal("100.00"))
    )

    assert valuation.available_capital_usd == Decimal("363.215114")


def test_valuation_accepts_dumped_projection_mapping() -> None:
    dumped = _state("514.2260692").model_dump(mode="json")

    assert authoritative_sleeve_equity(dumped).equity_usd == Decimal("514.2260692")


def _bundle_context(regular: dict, continuous: dict):
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: SimpleNamespace(
            model_dump=lambda mode="json": {
                "regular": regular,
                "continuous": continuous,
                "aggregate_currency_balances": [],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: SimpleNamespace(
            model_dump=lambda mode="json": {"active_contracts": [], "projection_sha256": "o" * 64}
        )
    )
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())
    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={"positions": []},
        open_orders={"open_orders": []},
        transition_phase="ACTIVE",
        regular_entry_open=True,
        family_sessions={},
    )
    return portfolio


def test_bundle_sleeve_equity_matches_authoritative_ledger_not_legacy_formula() -> None:
    regular = _state(
        "514.2260692", sleeve=CapitalSleeve.REGULAR_SLEEVE,
        fees_deductible_usd=Decimal("13.2939308"),
    ).model_dump(mode="json")
    continuous = _state(
        "463.215114", realized_pnl_usd=Decimal("-10.701886"),
        fees_deductible_usd=Decimal("24.50"),
    ).model_dump(mode="json")

    portfolio = _bundle_context(regular, continuous)

    assert Decimal(portfolio["sleeves"]["regular"]["equity_usd"]) == Decimal("514.2260692")
    assert Decimal(portfolio["sleeves"]["continuous"]["equity_usd"]) == Decimal("463.215114")
    assert portfolio["sleeves"]["regular"]["equity_formula"] == "USD_CASH_PLUS_FRESH_POSITION_MARKET_VALUE_V1"


def test_bundle_blocks_new_entries_when_sleeve_equity_needs_fx() -> None:
    regular = _state(
        "400", sleeve=CapitalSleeve.REGULAR_SLEEVE,
        other=(CurrencyBalance(currency="EUR", amount=Decimal("40")),),
    ).model_dump(mode="json")
    continuous = _state("463.215114").model_dump(mode="json")

    portfolio = _bundle_context(regular, continuous)

    assert portfolio["sleeves"]["regular"]["equity_usd"] is None
    eligibility = portfolio["entry_eligibility"]["REGULAR_SLEEVE"]
    assert eligibility["status"] == "BLOCK"
    assert "SLEEVE_FX_VALUATION_REQUIRED" in eligibility["reason_codes"]


def test_capital_equity_for_sleeve_rejects_unavailable_valuation() -> None:
    bundle = SimpleNamespace(
        multi_sleeve_v4_active=True,
        multi_sleeve_portfolio={"sleeves": {"regular": {"equity_usd": None}, "continuous": {"equity_usd": "463.215114"}}},
    )

    with pytest.raises(ValueError, match="SLEEVE_FRESH_VALUATION_REQUIRED"):
        capital_equity_for_sleeve(bundle, CapitalSleeve.REGULAR_SLEEVE)
    assert capital_equity_for_sleeve(bundle, CapitalSleeve.CONTINUOUS_SLEEVE) == Decimal("463.215114")


def test_authority_blocks_new_trade_when_sleeve_valuation_is_not_fresh() -> None:
    request = _v4_request(ModelExecutionOperation.NEW_TRADE)
    receipt = SleeveExecutionAuthorityValidator.validate(
        request, _broker(request), _snapshot(request, equity_valuation_fresh=False)
    )

    assert receipt.status == "BLOCK"
    assert "SLEEVE_FRESH_VALUATION_REQUIRED" in receipt.reason_codes


def test_authority_maximum_loss_is_bounded_by_real_equity() -> None:
    request = _v4_request(ModelExecutionOperation.NEW_TRADE)
    above = SleeveExecutionAuthorityValidator.validate(
        request, _broker(request),
        _snapshot(request, equity_usd=Decimal("463.215114"), proposed_maximum_loss_usd=Decimal("463.22")),
    )
    within = SleeveExecutionAuthorityValidator.validate(
        request, _broker(request),
        _snapshot(request, equity_usd=Decimal("463.215114"), proposed_maximum_loss_usd=Decimal("463.21")),
    )

    assert "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED" in above.reason_codes
    assert "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED" not in within.reason_codes
    assert "SLEEVE_AGGREGATE_LIABILITY_EXCEEDED" not in within.reason_codes


def test_v4_bundle_marks_legacy_single_ledger_as_non_authoritative() -> None:
    legacy = SimpleNamespace(
        allocation=Decimal("500.00"), cash=Decimal("491.64"), market_value=Decimal("0"),
        equity=Decimal("491.64"), high_water_mark=Decimal("581.45"), drawdown=Decimal("89.80"),
        fees=Decimal("34.29"), valid=True, reason_codes=(),
    )
    portfolio = {
        "sleeves": {
            "regular": {"equity_usd": "514.2260692", "available_capital_usd": "514.2260692"},
            "continuous": {"equity_usd": "463.215114", "available_capital_usd": "463.215114"},
        }
    }

    subledger, broker, risk = AutonomousStateBuilder._economic_bundle_fields(
        {"paper_account": True, "declared_options_level": 4}, legacy, portfolio
    )

    assert subledger["authority"] == "LEGACY_SINGLE_LEDGER_NON_AUTHORITATIVE"
    for misleading in ("equity", "cash", "high_water_mark", "drawdown", "fees"):
        assert misleading not in subledger
    assert "experiment_buying_power" not in broker
    assert broker["sleeve_available_capital_usd"] == {
        "REGULAR_SLEEVE": "514.2260692",
        "CONTINUOUS_SLEEVE": "463.215114",
    }
    assert risk["maximum_liability_by_sleeve_usd"] == {
        "REGULAR_SLEEVE": "514.2260692",
        "CONTINUOUS_SLEEVE": "463.215114",
    }
    assert "maximum_experiment_liability" not in risk


def test_legacy_bundle_fields_are_unchanged_without_sleeves() -> None:
    legacy = SimpleNamespace(
        allocation=Decimal("500.00"), cash=Decimal("299.00"), market_value=Decimal("300.00"),
        equity=Decimal("599.00"), high_water_mark=Decimal("599.00"), drawdown=Decimal("0"),
        fees=Decimal("1"), valid=True, reason_codes=(),
    )

    subledger, broker, risk = AutonomousStateBuilder._economic_bundle_fields(
        {"paper_account": True, "declared_options_level": 4}, legacy, None
    )

    assert subledger["equity"] == "599.00"
    assert broker["experiment_buying_power"] == "599.00"
    assert risk["maximum_experiment_liability"] == "599.00"


def test_production_authority_reader_uses_the_single_authoritative_equity() -> None:
    source = inspect.getsource(_ProductionSleeveAuthoritySnapshotReader.__call__)

    assert "authoritative_sleeve_equity(" in source
    assert "realized_pnl_usd" not in source
    assert "fees_usd" not in source
