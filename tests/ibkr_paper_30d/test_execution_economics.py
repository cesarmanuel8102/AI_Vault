from __future__ import annotations

from decimal import Decimal

from ibkr_paper_30d.autonomous_research import (
    CodexAutonomousCLIProvider,
    EconomicCandidateAssessment,
)
from ibkr_paper_30d.execution_economics import execution_break_even_economics

AS_OF = "2026-11-07T20:00:00Z"


def _economics(regular="514.2260692", continuous="463.215114", observed=None):
    return execution_break_even_economics(
        {"REGULAR_SLEEVE": regular, "CONTINUOUS_SLEEVE": continuous},
        observed_commissions=observed or {},
        as_of_utc=AS_OF,
    )


def test_crypto_minimum_commission_dominates_near_500_dollar_sleeve() -> None:
    crypto = _economics()["CONTINUOUS_SLEEVE"]["CRYPTO"]

    assert Decimal(crypto["notional_usd"]) == Decimal("463.215114")
    assert Decimal(crypto["entry_commission_usd"]) == Decimal("1.75")
    assert Decimal(crypto["exit_commission_usd"]) == Decimal("1.75")
    assert Decimal(crypto["round_trip_commission_usd"]) == Decimal("3.50")
    assert Decimal("0.0075") < Decimal(crypto["round_trip_commission_pct"]) < Decimal("0.0076")
    assert Decimal(crypto["break_even_move_pct"]) > Decimal(crypto["round_trip_commission_pct"])
    assert crypto["commission_source"] == "DETERMINISTIC_BROKER_SCHEDULE"


def test_crypto_percentage_commission_applies_above_minimum() -> None:
    crypto = _economics(continuous="5000")["CONTINUOUS_SLEEVE"]["CRYPTO"]

    assert Decimal(crypto["entry_commission_usd"]) == Decimal("9.00")


def test_stock_round_trip_counts_commission_once_per_order() -> None:
    stock = _economics()["REGULAR_SLEEVE"]["STK"]
    total = (
        Decimal(stock["round_trip_commission_usd"])
        + Decimal(stock["spread_cost_usd"])
        + Decimal(stock["slippage_cost_usd"])
        + Decimal(stock["fees_usd"])
    )

    assert Decimal(stock["round_trip_commission_usd"]) == Decimal("2.00")
    assert Decimal(stock["round_trip_cost_usd"]) == total
    assert Decimal(stock["break_even_move_pct"]) == (total / Decimal("514.2260692")).quantize(Decimal("0.000001"))


def test_option_and_combo_are_per_contract_with_multiplier() -> None:
    regular = _economics()["REGULAR_SLEEVE"]
    option = regular["OPT"]
    combo = regular["BAG"]

    assert option["unit"] == "PER_CONTRACT"
    assert Decimal(option["round_trip_commission_usd"]) == Decimal("2.00")
    assert Decimal(option["break_even_premium_move_per_share_usd"]) == Decimal("0.02")
    assert combo["legs"] == 2
    assert Decimal(combo["round_trip_commission_usd"]) == Decimal("2.60")


def test_observed_commissions_are_reported_with_their_source() -> None:
    economics = _economics(observed={
        "REGULAR_SLEEVE": {"median_commission_per_order_usd": "1.0053", "fills": 14,
                           "last_fill_utc": "2026-11-05T18:36:38Z"},
    })

    stock = economics["REGULAR_SLEEVE"]["STK"]
    assert stock["observed_commission_per_order_usd"] == "1.0053"
    assert stock["observed_commission_source"] == "HISTORICAL_ESTIMATE_FROM_EXECUTED_FILLS"
    assert Decimal(stock["entry_commission_usd"]) == Decimal("1.0053")


def test_every_entry_carries_source_timestamp_and_assumption_labels() -> None:
    for families in _economics().values():
        if not isinstance(families, dict):
            continue
        for item in families.values():
            assert item["as_of_utc"] == AS_OF
            assert item["spread_source"] == "CONSERVATIVE_ASSUMPTION_REPLACE_WITH_LIVE_QUOTE"
            assert item["epistemic_status"] == "DETERMINISTIC_CALCULATION"


def test_unavailable_sleeve_capital_reports_no_break_even() -> None:
    crypto = _economics(continuous=None)["CONTINUOUS_SLEEVE"]

    assert crypto == {"status": "UNAVAILABLE", "reason": "SLEEVE_EQUITY_UNAVAILABLE"}


def test_candidate_assessment_accepts_break_even_accountability_fields() -> None:
    item = EconomicCandidateAssessment(
        symbol="SOL", sec_type="CRYPTO", disposition="NO_ENTRY",
        estimate_basis="x", reason="y",
        expected_move_pct=Decimal("0.012"), expected_holding_horizon="1 day",
        break_even_move_pct=Decimal("0.0091"), expected_move_to_break_even_ratio=Decimal("1.32"),
        after_cost_rationale="Move exceeds costs by 32%.",
    )

    assert item.break_even_move_pct == Decimal("0.0091")


def test_strict_schema_requires_break_even_fields_but_allows_null() -> None:
    schema = CodexAutonomousCLIProvider.strict_output_schema()
    candidate = schema["$defs"]["EconomicCandidateAssessment"]

    for field in ("expected_move_pct", "expected_holding_horizon", "break_even_move_pct",
                  "expected_move_to_break_even_ratio", "after_cost_rationale"):
        assert field in candidate["required"]
        assert {"type": "null"} in candidate["properties"][field]["anyOf"]


def test_bundle_exposes_execution_economics_on_available_capital() -> None:
    from test_sleeve_equity_authority import _bundle_context, _state
    from ibkr_paper_30d.multi_universe_models import CapitalSleeve

    portfolio = _bundle_context(
        _state("514.2260692", sleeve=CapitalSleeve.REGULAR_SLEEVE).model_dump(mode="json"),
        _state("463.215114").model_dump(mode="json"),
    )

    economics = portfolio["execution_economics"]
    assert Decimal(economics["CONTINUOUS_SLEEVE"]["CRYPTO"]["notional_usd"]) == Decimal("463.215114")
    assert Decimal(economics["REGULAR_SLEEVE"]["STK"]["notional_usd"]) == Decimal("514.2260692")


def test_prompt_asks_for_break_even_accountability_without_requiring_a_trade() -> None:
    import inspect

    from ibkr_paper_30d import autonomous_research

    source = inspect.getsource(autonomous_research.CodexAutonomousCLIProvider)

    assert "execution_economics" in source
    assert "expected_move_to_break_even_ratio" in source
    assert "does not require a trade" in source
