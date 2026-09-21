from __future__ import annotations

from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.risk import RiskEngine, RiskInputs, RiskResult


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine.month1()


@pytest.fixture
def base_inputs() -> RiskInputs:
    return RiskInputs(
        experiment_equity=Decimal("500.00"),
        day_start_equity=Decimal("500.00"),
        week_start_equity=Decimal("500.00"),
        high_water_equity=Decimal("500.00"),
        estimated_loss=Decimal("0"),
        position_capital=Decimal("0"),
        total_open_risk=Decimal("0"),
        daily_loss=Decimal("0"),
        weekly_drawdown=Decimal("0"),
        total_drawdown=Decimal("0"),
        concurrent_positions=0,
    )


def test_entire_experimental_equity_may_be_at_risk(engine, base_inputs) -> None:
    inputs = base_inputs.model_copy(
        update={
            "estimated_loss": Decimal("500.00"),
            "position_capital": Decimal("500.00"),
            "total_open_risk": Decimal("500.00"),
            "daily_loss": Decimal("450.00"),
            "weekly_drawdown": Decimal("450.00"),
            "total_drawdown": Decimal("450.00"),
            "concurrent_positions": 12,
        }
    )

    result = engine.evaluate(inputs)

    assert result.result == RiskResult.PASS
    assert result.reason_codes == ()
    assert result.maximum_experiment_liability == Decimal("500.00")
    assert result.drawdown_limits_enforced is False
    assert result.concurrent_position_limit_enforced is False


@pytest.mark.parametrize("field", ["estimated_loss", "total_open_risk"])
def test_liability_above_equity_is_blocked(engine, base_inputs, field) -> None:
    result = engine.evaluate(
        base_inputs.model_copy(update={field: Decimal("500.01")})
    )

    assert result.result == RiskResult.BLOCK
    assert any("EXCEEDS_EQUITY" in reason for reason in result.reason_codes)


def test_large_notional_is_not_itself_a_policy_violation(engine, base_inputs) -> None:
    result = engine.evaluate(
        base_inputs.model_copy(
            update={
                "position_capital": Decimal("2500.00"),
                "estimated_loss": Decimal("180.00"),
                "total_open_risk": Decimal("180.00"),
            }
        )
    )

    assert result.result == RiskResult.PASS
    assert result.position_capital_limit_enforced is False


def test_drawdown_does_not_stop_experiment_while_equity_remains_positive(
    engine, base_inputs
) -> None:
    inputs = base_inputs.model_copy(
        update={
            "experiment_equity": Decimal("50.00"),
            "day_start_equity": Decimal("500.00"),
            "week_start_equity": Decimal("500.00"),
            "high_water_equity": Decimal("500.00"),
            "daily_loss": Decimal("450.00"),
            "weekly_drawdown": Decimal("450.00"),
            "total_drawdown": Decimal("450.00"),
            "estimated_loss": Decimal("50.00"),
            "total_open_risk": Decimal("50.00"),
        }
    )

    result = engine.evaluate(inputs)

    assert result.result == RiskResult.PASS


def test_liability_breach_can_request_reduced_size(engine, base_inputs) -> None:
    result = engine.evaluate(
        base_inputs.model_copy(
            update={
                "estimated_loss": Decimal("700.00"),
                "total_open_risk": Decimal("700.00"),
                "can_reduce_size": True,
            }
        )
    )

    assert result.result == RiskResult.REDUCE_SIZE
    assert result.maximum_estimated_loss == Decimal("500.00")


def test_same_inputs_produce_byte_identical_results(engine, base_inputs) -> None:
    first = engine.evaluate(base_inputs)
    second = engine.evaluate(base_inputs)

    assert canonical_bytes(first) == canonical_bytes(second)


def test_non_positive_equity_fails_closed(engine, base_inputs) -> None:
    result = engine.evaluate(
        base_inputs.model_copy(update={"experiment_equity": Decimal("0")})
    )

    assert result.result == RiskResult.BLOCK
    assert result.reason_codes == ("INVALID_EQUITY",)
