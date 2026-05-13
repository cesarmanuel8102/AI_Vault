"""
Tests for _update_scorecard_with_trade in action_executor.

After the 9X double-counting fix, platform metrics are recorded when
trades resolve via paper_execution._update_platform_metrics(), NOT in
_update_scorecard_with_trade.  These tests verify:
  - _LANE_TO_PLATFORM mapping still present
  - _update_scorecard_with_trade does NOT call record_trade (no double-counting)
  - Scorecard seed_metrics are still updated correctly
"""
import pytest
from unittest.mock import patch, MagicMock

import brain_v9.config as _cfg
from brain_v9.autonomy.action_executor import (
    _update_scorecard_with_trade,
    _LANE_TO_PLATFORM,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _empty_scorecard():
    return {
        "seed_metrics": {
            "entries_taken": 0,
            "entries_resolved": 0,
            "wins": 0,
            "losses": 0,
            "gross_units": 0,
            "net_units": 0,
            "valid_candidates_skipped": 0,
        },
        "entry_outcome_counts": {},
        "strategy_performance_seed": {},
        "pair_performance_seed": {},
        "pair_breakdown_seed": {},
    }


def _make_trade(result="win", profit=5.0, symbol="EURUSD_otc"):
    return {"result": result, "profit": profit, "symbol": symbol, "direction": "call"}


# ── _LANE_TO_PLATFORM ────────────────────────────────────────────────────────

def test_lane_to_platform_mapping():
    assert _LANE_TO_PLATFORM["pocket_option"] == "pocket_option"
    assert _LANE_TO_PLATFORM["ibkr"] == "ibkr"
    assert _LANE_TO_PLATFORM["internal_paper_simulator"] == "internal_paper"
    assert _LANE_TO_PLATFORM["internal_paper"] == "internal_paper"


# ── 9X fix: record_trade is NOT called from _update_scorecard_with_trade ─────

@patch("brain_v9.trading.platform_manager.get_platform_manager")
def test_update_scorecard_does_not_call_platform_manager(mock_get_pm):
    """After 9X fix, platform metrics are recorded on resolution, not here."""
    mock_pm = MagicMock()
    mock_get_pm.return_value = mock_pm

    scorecard = _empty_scorecard()
    trade = _make_trade(result="win", profit=5.0, symbol="EURUSD_otc")
    _update_scorecard_with_trade(scorecard, trade, "strat_1", platform="pocket_option")

    mock_pm.record_trade.assert_not_called()


@patch("brain_v9.trading.platform_manager.get_platform_manager")
def test_update_scorecard_no_pm_call_ibkr(mock_get_pm):
    mock_pm = MagicMock()
    mock_get_pm.return_value = mock_pm

    scorecard = _empty_scorecard()
    trade = _make_trade(result="loss", profit=3.0)
    _update_scorecard_with_trade(scorecard, trade, "strat_2", platform="ibkr")

    mock_pm.record_trade.assert_not_called()


# ── Scorecard seed_metrics still updated correctly ───────────────────────────

def test_update_scorecard_still_updates_scorecard():
    """Core scorecard logic must still work correctly without PM hook."""
    scorecard = _empty_scorecard()
    trade = _make_trade(result="loss", profit=2.5, symbol="GBPUSD_otc")

    _update_scorecard_with_trade(scorecard, trade, "strat_x", platform="ibkr")

    seed = scorecard["seed_metrics"]
    assert seed["entries_taken"] == 1
    assert seed["losses"] == 1
    assert seed["wins"] == 0
    assert float(seed["net_units"]) == 2.5  # profit is added, not subtracted (scorecard convention)
    assert scorecard["pair_breakdown_seed"]["GBPUSD"] == 1
    assert scorecard["entry_outcome_counts"]["loss"] == 1
    assert scorecard["strategy_performance_seed"]["strat_x"] == 2.5


def test_update_scorecard_win():
    scorecard = _empty_scorecard()
    trade = _make_trade(result="win", profit=10.0, symbol="SPY")

    _update_scorecard_with_trade(scorecard, trade, "ibkr_strat", platform="ibkr")

    seed = scorecard["seed_metrics"]
    assert seed["entries_taken"] == 1
    assert seed["wins"] == 1
    assert seed["losses"] == 0
    assert float(seed["net_units"]) == 10.0
    assert scorecard["strategy_performance_seed"]["ibkr_strat"] == 10.0


def test_update_scorecard_pending_resolution():
    """pending_resolution trades should still update seed_metrics counters."""
    scorecard = _empty_scorecard()
    trade = _make_trade(result="pending_resolution", profit=0.0, symbol="AAPL")

    _update_scorecard_with_trade(scorecard, trade, "strat_pending", platform="internal_paper_simulator")

    seed = scorecard["seed_metrics"]
    assert seed["entries_taken"] == 1
    # pending is neither win nor loss
    assert seed["wins"] == 0
    assert seed["losses"] == 0
    assert float(seed["net_units"]) == 0.0
