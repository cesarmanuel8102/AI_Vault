import pytest

from zero_dte_core import (
    adverse_failure_to_launch_due,
    adaptive_allocation_fraction,
    contract_quantity,
    contract_quantity_for_allocation,
    failure_to_launch_due,
    friction_within_target,
    checkpoint_snapshot,
    entry_before_cutoff,
    rank_daily_candidates,
    quality_signal,
    select_contract_by_delta,
    select_expiry,
    select_strike,
    scale_out_quantity,
    trailing_profit_exit_due,
    causal_quality_score,
    passes_causal_quality_gate,
    rank_quality_candidates,
)


def test_entry_cutoff_blocks_new_positions_at_and_after_cutoff_hour():
    assert entry_before_cutoff(13, 14)
    assert not entry_before_cutoff(14, 14)
    assert not entry_before_cutoff(15, 14)
    assert entry_before_cutoff(15, 24)


def test_daily_candidate_ranking_uses_signal_strength_then_lower_friction():
    candidates = [
        {"ticker": "A", "relative_volume": 1.5, "close_location": 0.8, "friction": 0.02},
        {"ticker": "B", "relative_volume": 2.0, "close_location": 0.8, "friction": 0.03},
        {"ticker": "C", "relative_volume": 2.0, "close_location": 0.8, "friction": 0.01},
    ]

    assert [item["ticker"] for item in rank_daily_candidates(candidates)] == ["C", "B", "A"]


def test_scale_out_quantity_locks_requested_fraction_and_leaves_runner():
    assert scale_out_quantity(20, 0.50) == 10
    assert scale_out_quantity(20, 0.75) == 15
    assert scale_out_quantity(11, 0.75) == 8
    assert scale_out_quantity(2, 0.75) == 1
    assert scale_out_quantity(1, 0.75) == 0
    assert scale_out_quantity(20, 0) == 0


def test_trailing_profit_exit_requires_activation_and_drawdown_from_peak():
    assert not trailing_profit_exit_due(0.15, 0.15, 0.15, 0.05)
    assert not trailing_profit_exit_due(0.11, 0.14, 0.15, 0.05)
    assert not trailing_profit_exit_due(0.16, 0.20, 0.15, 0.05)
    assert trailing_profit_exit_due(0.15, 0.20, 0.15, 0.05)
    assert trailing_profit_exit_due(0.24, 0.30, 0.15, 0.05)
    assert not trailing_profit_exit_due(0.10, 0.20, 0, 0.05)


def test_friction_gate_requires_roundtrip_hurdle_not_to_exceed_target():
    assert friction_within_target(1.00, 0.10)
    assert friction_within_target(0.33, 0.10)
    assert not friction_within_target(0.329, 0.10)
    assert not friction_within_target(0, 0.10)


def test_adverse_failure_requires_time_loss_and_directional_underlying_failure():
    assert adverse_failure_to_launch_due(15, -0.40, -0.001, 15, -0.40)
    assert adverse_failure_to_launch_due(20, -0.60, -0.001, 15, -0.40)
    assert not adverse_failure_to_launch_due(14.99, -0.60, -0.001, 15, -0.40)
    assert not adverse_failure_to_launch_due(15, -0.39, -0.001, 15, -0.40)
    assert not adverse_failure_to_launch_due(15, -0.60, 0.0, 15, -0.40)
    assert not adverse_failure_to_launch_due(15, -0.60, 0.001, 15, -0.40)


def test_zero_dte_requires_exact_same_day_expiry():
    from datetime import date

    expiries = [date(2026, 1, 5), date(2026, 1, 7)]
    assert select_expiry(expiries, date(2026, 1, 5), 0) == date(2026, 1, 5)
    assert select_expiry(expiries, date(2026, 1, 6), 0) is None


def test_positive_dte_uses_nearest_nonexpired_listed_expiry():
    from datetime import date

    expiries = [date(2026, 1, 9), date(2026, 1, 12), date(2026, 1, 16)]
    assert select_expiry(expiries, date(2026, 1, 2), 7) == date(2026, 1, 9)
    assert select_expiry(expiries, date(2026, 1, 2), 14) == date(2026, 1, 16)
    assert select_expiry([date(2025, 12, 31)], date(2026, 1, 2), 7) is None


def test_delta_selector_uses_absolute_delta_and_rejects_invalid_quotes():
    candidates = [
        {"symbol": "bad", "delta": -0.70, "bid": 0.0, "ask": 1.0},
        {"symbol": "put65", "delta": -0.65, "bid": 1.0, "ask": 1.1},
        {"symbol": "put72", "delta": -0.72, "bid": 1.0, "ask": 1.1},
    ]
    assert select_contract_by_delta(candidates, 0.70)["symbol"] == "put72"
    assert select_contract_by_delta([], 0.70) is None


def test_atm_selects_closest_strike_and_prefers_itm_on_tie():
    strikes = [99.0, 101.0, 103.0]
    assert select_strike(strikes, 100.0, 1, "atm") == 99.0
    assert select_strike(strikes, 100.0, -1, "atm") == 101.0


def test_otm_selects_nearest_strike_in_signal_direction():
    strikes = [95.0, 99.0, 101.0, 105.0]
    assert select_strike(strikes, 100.0, 1, "otm") == 101.0
    assert select_strike(strikes, 100.0, -1, "otm") == 99.0


def test_otm_returns_none_when_no_valid_strike_exists():
    assert select_strike([95.0, 100.0], 100.0, 1, "otm") is None
    assert select_strike([100.0, 105.0], 100.0, -1, "otm") is None


def test_quantity_uses_ten_percent_of_the_smaller_cash_or_equity_budget():
    assert contract_quantity(cash=50_000, equity=100_000, ask=5.0) == 10
    assert contract_quantity(cash=100_000, equity=50_000, ask=5.0) == 10
    assert contract_quantity(cash=4_000, equity=100_000, ask=5.0) == 0


def test_quantity_accepts_full_capital_fraction_for_small_account_variant():
    assert contract_quantity(cash=500, equity=500, ask=2.50, capital_fraction=1.0) == 2
    assert contract_quantity(cash=500, equity=500, ask=5.01, capital_fraction=1.0) == 0


def test_daily_allocation_quantity_reserves_equal_equity_budgets():
    assert contract_quantity_for_allocation(500, 500, 2.00, 0.50) == 1
    assert contract_quantity_for_allocation(300, 500, 1.00, 0.50) == 2
    assert contract_quantity_for_allocation(50, 500, 1.00, 0.50) == 0


def test_adaptive_allocation_uses_all_capital_across_remaining_slots():
    assert adaptive_allocation_fraction(2, 2) == 0.5
    assert adaptive_allocation_fraction(1, 2) == 1.0
    assert adaptive_allocation_fraction(2, 1) == 1.0


def test_invalid_mode_or_quote_is_rejected():
    with pytest.raises(ValueError):
        select_strike([100.0], 100.0, 1, "near")
    assert contract_quantity(100_000, 100_000, 0) == 0


def test_failure_to_launch_only_fires_after_enabled_checkpoint_below_threshold():
    assert not failure_to_launch_due(4.99, -0.20, 5, 0.0)
    assert failure_to_launch_due(5.0, -0.001, 5, 0.0)
    assert not failure_to_launch_due(5.0, 0.0, 5, 0.0)
    assert not failure_to_launch_due(60.0, -0.50, 0, 0.0)


def test_quality_signal_is_direction_symmetric_and_requires_volume_and_range():
    assert quality_signal(1, 100, 102, 98, 101, 1.20)
    assert quality_signal(-1, 100, 102, 98, 99, 1.20)
    assert not quality_signal(1, 100, 102, 98, 100.99, 1.20)
    assert not quality_signal(-1, 100, 102, 98, 99.01, 1.20)
    assert not quality_signal(1, 100, 102, 98, 101, 1.19)
    assert not quality_signal(1, 100, 100, 100, 100, 2.0)


def test_checkpoint_snapshot_uses_only_directional_information_available_now():
    bullish = checkpoint_snapshot(2.0, 2.1, 2.2, 100, 101, 1, 99, 98)
    bearish = checkpoint_snapshot(2.0, 2.1, 2.2, 100, 99, -1, 101, 102)
    for snapshot in (bullish, bearish):
        assert snapshot == {
            "option_return": 0.05,
            "underlying_return": 0.01,
            "level_margin": 0.02,
            "invalidation_margin": 0.03,
            "spread_fraction": 0.05,
        }
    assert checkpoint_snapshot(0, 2.1, 2.2, 100, 101, 1, 99, 98) is None


def _quality_candidate(ticker="A", **overrides):
    candidate = {
        "ticker": ticker,
        "relative_volume": 1.50,
        "close_location": 0.80,
        "body_strength": 0.60,
        "range_atr": 0.90,
        "level_rejection_atr": 0.35,
        "friction": 0.04,
        "cash": 500,
        "equity": 500,
        "premium": 2.00,
        "quantity": 1,
    }
    candidate.update(overrides)
    return candidate


def test_causal_gate_fails_closed_and_is_independent_of_capital_fields():
    thresholds = {
        "relative_volume_min": 1.20,
        "close_location_min": 0.70,
        "body_strength_min": 0.40,
        "range_atr_min": 0.50,
        "range_atr_max": 1.50,
        "level_rejection_atr_min": 0.10,
        "friction_max": 0.10,
    }
    small = _quality_candidate()
    large = _quality_candidate(cash=5_000, equity=5_000, premium=5.00, quantity=10)

    assert passes_causal_quality_gate(small, thresholds)
    assert passes_causal_quality_gate(large, thresholds)
    assert not passes_causal_quality_gate({"ticker": "missing"}, thresholds)
    assert not passes_causal_quality_gate(_quality_candidate(range_atr=0), thresholds)


def test_causal_score_ignores_capital_and_ranks_deterministically():
    weights = {
        "relative_volume": 1.0,
        "close_location": 2.0,
        "body_strength": 1.0,
        "level_rejection_atr": 1.0,
        "friction": -1.0,
    }
    first = _quality_candidate("B")
    same_signal_larger_account = _quality_candidate(
        "B", cash=50_000, equity=50_000, premium=10.00, quantity=50
    )
    stronger = _quality_candidate("C", close_location=0.90)
    tied = _quality_candidate("A")

    assert causal_quality_score(first, weights) == causal_quality_score(
        same_signal_larger_account, weights
    )
    assert [item["ticker"] for item in rank_quality_candidates(
        [first, stronger, tied], weights
    )] == ["C", "A", "B"]
