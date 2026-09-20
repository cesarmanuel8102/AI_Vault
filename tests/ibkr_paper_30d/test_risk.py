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


def evaluate_with(engine, base, field: str, value: str | int):
    return engine.evaluate(base.model_copy(update={field: Decimal(value) if isinstance(value, str) else value}))


@pytest.mark.parametrize(
    "field,below,at,above,reason",
    [
        ("estimated_loss", "24.99", "25.00", "25.01", "MAX_ESTIMATED_LOSS_PER_TRADE"),
        ("position_capital", "199.99", "200.00", "200.01", "MAX_SINGLE_POSITION_CAPITAL"),
        ("total_open_risk", "74.99", "75.00", "75.01", "MAX_TOTAL_OPEN_RISK"),
        ("daily_loss", "39.99", "40.00", "40.01", "MAX_DAILY_LOSS"),
        ("weekly_drawdown", "59.99", "60.00", "60.01", "MAX_WEEKLY_DRAWDOWN"),
        ("total_drawdown", "99.99", "100.00", "100.01", "MAX_TOTAL_DRAWDOWN"),
    ],
)
def test_money_limit_boundaries_block_at_limit(
    engine, base_inputs, field, below, at, above, reason
) -> None:
    assert evaluate_with(engine, base_inputs, field, below).result == RiskResult.PASS
    at_result = evaluate_with(engine, base_inputs, field, at)
    above_result = evaluate_with(engine, base_inputs, field, above)
    assert at_result.result == RiskResult.BLOCK
    assert above_result.result == RiskResult.BLOCK
    assert reason in at_result.reason_codes
    assert reason in above_result.reason_codes


def test_fourth_concurrent_position_is_blocked(engine, base_inputs) -> None:
    result = evaluate_with(engine, base_inputs, "concurrent_positions", 3)

    assert result.result == RiskResult.BLOCK
    assert result.reason_codes == ("MAX_CONCURRENT_POSITIONS",)


def test_multiple_failures_are_all_reported(engine, base_inputs) -> None:
    inputs = base_inputs.model_copy(
        update={
            "estimated_loss": Decimal("25"),
            "position_capital": Decimal("200"),
            "total_drawdown": Decimal("100"),
        }
    )

    result = engine.evaluate(inputs)

    assert result.result == RiskResult.BLOCK
    assert result.reason_codes == (
        "MAX_ESTIMATED_LOSS_PER_TRADE",
        "MAX_SINGLE_POSITION_CAPITAL",
        "MAX_TOTAL_DRAWDOWN",
    )


def test_sizing_only_breach_can_request_reduced_size(engine, base_inputs) -> None:
    inputs = base_inputs.model_copy(
        update={"position_capital": Decimal("250"), "can_reduce_size": True}
    )

    result = engine.evaluate(inputs)

    assert result.result == RiskResult.REDUCE_SIZE
    assert result.maximum_position_capital == Decimal("199.99")


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
