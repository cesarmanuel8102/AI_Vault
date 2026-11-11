from datetime import date

import pytest

from options_operability_core import (
    passes_options_go_gate,
    premium_quantity,
    reinforcement_quantity,
    select_weekly_contract,
    target_price,
)


def test_selects_earliest_expiry_and_nearest_otm_call():
    contracts = [
        {"expiry": date(2025, 1, 10), "strike": 101, "right": "call"},
        {"expiry": date(2025, 1, 10), "strike": 105, "right": "call"},
        {"expiry": date(2025, 1, 17), "strike": 101, "right": "call"},
    ]
    selected = select_weekly_contract(contracts, date(2025, 1, 6), 100, "call")
    assert selected == contracts[0]


def test_put_selection_is_strictly_otm_and_skips_same_day_expiry():
    contracts = [
        {"expiry": date(2025, 1, 3), "strike": 99, "right": "put"},
        {"expiry": date(2025, 1, 10), "strike": 100, "right": "put"},
        {"expiry": date(2025, 1, 10), "strike": 99, "right": "put"},
        {"expiry": date(2025, 1, 10), "strike": 95, "right": "put"},
    ]
    selected = select_weekly_contract(contracts, date(2025, 1, 3), 100, "put")
    assert selected == contracts[2]


def test_premium_quantity_respects_two_percent_budget():
    assert premium_quantity(100_000, 2.50) == 8
    assert premium_quantity(500, 6.00) == 0


def test_reinforcement_never_exceeds_original_outlay():
    assert reinforcement_quantity(10, 0.50, 0.10) == 50
    assert reinforcement_quantity(10, 0.50, 0.0) == 0


def test_target_uses_weighted_average_cost():
    assert target_price([(10, 0.50), (50, 0.10)], 0.35) == pytest.approx(0.225)


def test_options_go_gate_requires_robustness_and_no_reinforcement_dependency():
    metrics = {
        "total_return": 0.10,
        "cagr": 0.025,
        "sharpe": 0.80,
        "profit_factor": 1.20,
        "max_drawdown": -0.15,
        "trades": 120,
        "positive_year_fraction": 0.75,
        "positive_symbol_fraction": 0.60,
        "reinforcement_required_for_solvency": False,
    }
    assert passes_options_go_gate(metrics)
    metrics["reinforcement_required_for_solvency"] = True
    assert not passes_options_go_gate(metrics)
