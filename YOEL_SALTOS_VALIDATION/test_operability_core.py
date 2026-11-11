import math

from operability_core import (
    atr,
    choose_barrier_exit,
    position_size,
    passes_go_gate,
)


def test_atr_uses_true_range_and_trailing_mean():
    highs = [11.0, 13.0, 12.0]
    lows = [9.0, 10.0, 8.0]
    closes = [10.0, 12.0, 9.0]
    result = atr(highs, lows, closes, 2)
    assert math.isnan(result[0])
    assert result[1] == 2.5
    assert result[2] == 3.5


def test_position_size_respects_risk_and_notional_caps():
    assert position_size(100_000, 100, 2, 0.005, 0.10) == 100
    assert position_size(100_000, 100, 20, 0.005, 0.10) == 25
    assert position_size(100_000, 100, 0, 0.005, 0.10) == 0


def test_barrier_exit_is_conservative_when_both_touch():
    assert choose_barrier_exit(99, 103, 98, 104, 102, 1) == (99, "STOP")
    assert choose_barrier_exit(101, 97, 96, 102, 98, -1) == (101, "STOP")


def test_go_gate_requires_every_frozen_condition():
    passing = {
        "total_return": 0.12,
        "cagr": 0.03,
        "sharpe": 0.9,
        "profit_factor": 1.2,
        "max_drawdown": -0.15,
        "trades": 120,
        "positive_year_fraction": 0.7,
        "positive_symbol_fraction": 0.6,
        "neighbor_sign_consistent": True,
        "portfolio_contribution": True,
    }
    assert passes_go_gate(passing)
    failing = dict(passing, profit_factor=1.14)
    assert not passes_go_gate(failing)
