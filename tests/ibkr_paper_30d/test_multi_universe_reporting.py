from decimal import Decimal

from ibkr_paper_30d.reporting import build_multi_universe_performance_report


def test_multi_universe_report_preserves_history_and_sleeve_separation() -> None:
    report = build_multi_universe_performance_report(
        regular_principal_usd=Decimal("500"),
        regular_opening_equity_usd=Decimal("470"),
        regular_current_equity_usd=Decimal("485"),
        extended_principal_usd=Decimal("500"),
        extended_opening_equity_usd=Decimal("500"),
        extended_current_equity_usd=Decimal("510"),
        regular_currency_balances={"USD": Decimal("210"), "EUR": Decimal("12")},
        extended_currency_balances={"USD": Decimal("300"), "EUR": Decimal("5")},
        canary_adjustment_usd=Decimal("-1.25"),
        ownership={
            "REGULAR_SLEEVE": ("regular-contract",),
            "EXTENDED_SLEEVE": ("extended-contract",),
        },
        certified_families=("family-a",),
        paper_limitations=("PAPER_FILL_SIMULATION",),
    )

    assert report["regular_historical_pnl_usd"] == "-30.00"
    assert report["regular_successor_pnl_usd"] == "15.00"
    assert report["extended_successor_pnl_usd"] == "10.00"
    assert report["combined_successor_pnl_usd"] == "25.00"
    assert report["combined_lifetime_pnl_usd"] == "-5.00"
    assert report["canary_adjustment_usd"] == "-1.25"
    assert report["currency_balances"]["REGULAR_SLEEVE"]["EUR"] == "12.00"
    assert report["currency_balances"]["EXTENDED_SLEEVE"]["EUR"] == "5.00"
    assert report["aggregate_currency_balances"]["EUR"] == "17.00"
    assert report["capital_rebased"] is False
    assert report["cross_sleeve_netting"] is False
