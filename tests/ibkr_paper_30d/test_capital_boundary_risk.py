from decimal import Decimal

from ibkr_paper_30d.risk import (
    CapitalBoundaryInputs,
    CapitalBoundaryRiskEngine,
    RiskResult,
)


def engine():
    return CapitalBoundaryRiskEngine.aggressive_month1()


def test_full_equity_loss_is_allowed():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("500.00"),
        liability_is_bounded=True,
    ))
    assert result.result == RiskResult.PASS
    assert result.reason_codes == ()


def test_one_cent_over_equity_is_blocked():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("500.01"),
        liability_is_bounded=True,
    ))
    assert result.result == RiskResult.BLOCK
    assert result.reason_codes == ("EXPERIMENT_CAPITAL_BOUNDARY",)


def test_unbounded_liability_is_blocked_even_if_margin_is_small():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("100.00"),
        liability_is_bounded=False,
    ))
    assert result.result == RiskResult.BLOCK
    assert "UNBOUNDED_LIABILITY" in result.reason_codes


def test_external_capital_is_never_part_of_experiment():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("1200.00"),
        maximum_loss=Decimal("1000.00"),
        liability_is_bounded=True,
        uses_external_capital=True,
    ))
    assert result.result == RiskResult.BLOCK
    assert "EXTERNAL_CAPITAL_FORBIDDEN" in result.reason_codes
