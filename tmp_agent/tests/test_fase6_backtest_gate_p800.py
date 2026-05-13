"""
Brain V9 — Fase 6: Backtest Gate & Research-to-Probation Gate

Tests for:
- _load_feed_ticks() with synthetic feed data
- _tick_to_feature() conversion
- simulate_strategy() signal evaluation and resolution
- simulate_strategy() pass/fail gate criteria
- research_to_probation_gate() combined checks
- No feed data edge case
- IBKR venue simulation skip
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

import brain_v9.trading.backtest_gate as bg


# ═════════════════════════════════════════════════════════════════════════════
# Helpers — synthetic feed and strategy data
# ═════════════════════════════════════════════════════════════════════════════

def _write_feed(tmp_path: Path, rows: list) -> Path:
    """Write a synthetic normalized feed file."""
    feed_path = tmp_path / "test_feed.json"
    feed = {
        "schema_version": "pocketoption_browser_bridge_normalized_feed_v1",
        "row_count": len(rows),
        "rows": rows,
    }
    feed_path.write_text(json.dumps(feed), encoding="utf-8")
    return feed_path


def _make_ticks(prices: list, symbol: str = "AUDNZD_otc", payout: float = 92.0) -> list:
    """Create synthetic tick rows from a list of prices."""
    rows = []
    for i, price in enumerate(prices):
        rows.append({
            "captured_utc": f"2026-03-28T00:{i:02d}:00Z",
            "pair": "AUD/NZD OTC",
            "symbol": symbol,
            "source_timestamp": 1774660000.0 + i * 30,
            "price": price,
            "payout_pct": payout,
            "expiry_seconds": 60,
            "socket_event_count": 100 + i,
            "last_socket_event": "updateStream",
            "last_stream_symbol": symbol,
            "visible_symbol": symbol,
            "stream_symbol_match": True,
            "indicator_candidates": ["RSI14", "Bollinger Bands 5 1", "MACD12 26 9"],
            "indicator_candidates_count": 3,
        })
    return rows


def _make_po_strategy(strategy_id="test_po_breakout_v1", family="breakout"):
    return {
        "strategy_id": strategy_id,
        "venue": "pocket_option",
        "family": family,
        "asset_classes": ["otc_binary"],
        "universe": ["AUDNZD_otc"],
        "timeframes": ["1m"],
        "setup_variants": ["breakout_1m"],
        "indicators": ["rsi_14", "bollinger_20_2"],
        "filters": [],
        "linked_hypotheses": ["H001"],
        "objective": "Test breakout in OTC binary",
        "success_criteria": {"min_sample": 5, "min_expectancy": 0.5},
        "probation_budget": 5,
        "confidence_threshold": 0.45,
    }


def _make_ibkr_strategy():
    return {
        "strategy_id": "ibkr_trend_v1",
        "venue": "ibkr",
        "family": "trend_following",
        "asset_classes": ["equity"],
        "universe": ["AAPL"],
        "timeframes": ["5m"],
        "linked_hypotheses": ["H002"],
        "objective": "Trend following on AAPL",
        "probation_budget": 5,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. _load_feed_ticks
# ═════════════════════════════════════════════════════════════════════════════

class TestLoadFeedTicks:

    def test_loads_and_sorts_ticks(self, tmp_path):
        # Write ticks out of order
        rows = _make_ticks([1.19, 1.20, 1.18])
        # Reverse to make out of order
        rows_reversed = list(reversed(rows))
        feed_path = _write_feed(tmp_path, rows_reversed)
        ticks = bg._load_feed_ticks(feed_path)
        assert len(ticks) == 3
        # Should be sorted by source_timestamp ascending
        assert float(ticks[0]["price"]) == 1.19
        assert float(ticks[2]["price"]) == 1.18

    def test_empty_feed(self, tmp_path):
        feed_path = _write_feed(tmp_path, [])
        ticks = bg._load_feed_ticks(feed_path)
        assert ticks == []

    def test_missing_file(self, tmp_path):
        ticks = bg._load_feed_ticks(tmp_path / "nonexistent.json")
        assert ticks == []


# ═════════════════════════════════════════════════════════════════════════════
# 2. _tick_to_feature
# ═════════════════════════════════════════════════════════════════════════════

class TestTickToFeature:

    def test_basic_conversion(self):
        tick = _make_ticks([1.1920])[0]
        feature = bg._tick_to_feature(tick)
        assert feature["venue"] == "pocket_option"
        assert feature["symbol"] == "AUDNZD_otc"
        assert feature["price_available"] is True
        assert feature["last"] == 1.1920
        assert feature["timeframe"] == "5m"  # P-OP26: switched to 5m
        assert feature["asset_class"] == "otc_binary"
        assert feature["is_stale"] is False
        assert feature["indicator_access_ready"] is True

    def test_price_change_from_prev(self):
        ticks = _make_ticks([1.0000, 1.0100])
        feature = bg._tick_to_feature(ticks[1], ticks[0])
        assert abs(feature["last_vs_close_pct"] - 1.0) < 0.01  # ~1% change
        assert feature["close"] == 1.0000

    def test_no_prev_tick(self):
        tick = _make_ticks([1.1920])[0]
        feature = bg._tick_to_feature(tick, None)
        assert feature["last_vs_close_pct"] == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 3. simulate_strategy — signal evaluation
# ═════════════════════════════════════════════════════════════════════════════

class TestSimulateStrategy:

    def test_no_feed_data(self, tmp_path):
        feed_path = _write_feed(tmp_path, [])
        result = bg.simulate_strategy(_make_po_strategy(), feed_path)
        assert result["passed"] is False
        assert result["reason"] == "no_feed_data_available"
        assert result["ticks_available"] == 0

    def test_simulation_returns_metrics(self, tmp_path):
        # Create a longer price series with enough variation for signals
        prices = [1.1900 + i * 0.0005 for i in range(20)]
        rows = _make_ticks(prices)
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(_make_po_strategy(), feed_path)

        # Verify structure
        assert "passed" in result
        assert "simulated_trades" in result
        assert "win_rate" in result
        assert "expectancy" in result
        assert "wins" in result
        assert "losses" in result
        assert "ticks_available" in result
        assert "gate_criteria" in result
        assert result["ticks_available"] == 20

    def test_insufficient_signals_fails(self, tmp_path):
        # Only 2 ticks — can't produce 3 trades
        rows = _make_ticks([1.19, 1.20])
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(
            _make_po_strategy(),
            feed_path,
            min_simulated_trades=3,
        )
        assert result["passed"] is False
        assert "insufficient_signals" in result["reason"]

    def test_gate_criteria_in_result(self, tmp_path):
        rows = _make_ticks([1.19, 1.20, 1.21])
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(
            _make_po_strategy(),
            feed_path,
            min_simulated_trades=5,
            min_win_rate=0.5,
            min_expectancy=-1.0,
        )
        assert result["gate_criteria"]["min_simulated_trades"] == 5
        assert result["gate_criteria"]["min_win_rate"] == 0.5
        assert result["gate_criteria"]["min_expectancy"] == -1.0


# ═════════════════════════════════════════════════════════════════════════════
# 4. research_to_probation_gate — combined checks
# ═════════════════════════════════════════════════════════════════════════════

class TestResearchToProbationGate:

    def test_venue_check_valid(self, tmp_path):
        feed_path = _write_feed(tmp_path, _make_ticks([1.19, 1.20]))
        with patch.object(bg, "PO_FEED_PATH", feed_path):
            result = bg.research_to_probation_gate(_make_po_strategy())
        assert result["checks"]["venue_valid"]["passed"] is True

    def test_venue_check_invalid(self, tmp_path):
        strat = _make_po_strategy()
        strat["venue"] = "binance"
        result = bg.research_to_probation_gate(strat)
        assert result["checks"]["venue_valid"]["passed"] is False

    def test_hypothesis_present(self, tmp_path):
        feed_path = _write_feed(tmp_path, _make_ticks([1.19, 1.20]))
        with patch.object(bg, "PO_FEED_PATH", feed_path):
            result = bg.research_to_probation_gate(_make_po_strategy())
        assert result["checks"]["hypothesis_present"]["passed"] is True

    def test_hypothesis_missing(self, tmp_path):
        strat = _make_po_strategy()
        strat["linked_hypotheses"] = []
        strat["objective"] = ""
        feed_path = _write_feed(tmp_path, _make_ticks([1.19, 1.20]))
        with patch.object(bg, "PO_FEED_PATH", feed_path):
            result = bg.research_to_probation_gate(strat)
        assert result["checks"]["hypothesis_present"]["passed"] is False

    def test_budget_from_success_criteria(self, tmp_path):
        strat = _make_po_strategy()
        strat["probation_budget"] = 0
        strat["success_criteria"] = {"min_sample": 8}
        feed_path = _write_feed(tmp_path, _make_ticks([1.19, 1.20]))
        with patch.object(bg, "PO_FEED_PATH", feed_path):
            result = bg.research_to_probation_gate(strat)
        assert result["checks"]["budget_available"]["passed"] is True
        assert result["checks"]["budget_available"]["probation_budget"] == 8

    def test_ibkr_simulation_skipped(self, tmp_path):
        result = bg.research_to_probation_gate(_make_ibkr_strategy())
        assert result["checks"]["simulation"]["passed"] is True
        assert "ibkr" in result["checks"]["simulation"]["reason"]

    def test_all_checks_present(self, tmp_path):
        feed_path = _write_feed(tmp_path, _make_ticks([1.19, 1.20]))
        with patch.object(bg, "PO_FEED_PATH", feed_path):
            result = bg.research_to_probation_gate(_make_po_strategy())
        assert "venue_valid" in result["checks"]
        assert "hypothesis_present" in result["checks"]
        assert "budget_available" in result["checks"]
        assert "simulation" in result["checks"]
        assert "strategy_id" in result
        assert "gate_utc" in result

    def test_overall_pass_requires_all_checks(self, tmp_path):
        strat = _make_po_strategy()
        strat["venue"] = "unknown_exchange"
        result = bg.research_to_probation_gate(strat)
        # venue is invalid → overall should fail
        assert result["passed"] is False


# ═════════════════════════════════════════════════════════════════════════════
# 5. Edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_strategy_with_no_universe(self, tmp_path):
        """Strategy with empty universe should still run — signals just won't fire."""
        strat = _make_po_strategy()
        strat["universe"] = []
        rows = _make_ticks([1.19, 1.20, 1.21, 1.22, 1.23])
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(strat, feed_path)
        # No signals because symbol not in universe
        assert result["simulated_trades"] == 0

    def test_single_tick(self, tmp_path):
        rows = _make_ticks([1.19])
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(_make_po_strategy(), feed_path)
        # Can't resolve against next tick → 0 trades
        assert result["simulated_trades"] == 0

    def test_constant_prices(self, tmp_path):
        """Same price for all ticks — signals may fire but resolution is ambiguous."""
        prices = [1.1920] * 10
        rows = _make_ticks(prices)
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(_make_po_strategy(), feed_path)
        # All trades where entry==exit are not counted as win
        assert isinstance(result["simulated_trades"], int)

    def test_mean_reversion_strategy(self, tmp_path):
        """Test with a mean_reversion family strategy."""
        strat = _make_po_strategy(family="mean_reversion")
        strat["strategy_id"] = "test_mr_v1"
        prices = [1.1900, 1.2000, 1.1950, 1.1900, 1.1850, 1.1900, 1.1950, 1.2000, 1.1950, 1.1900]
        rows = _make_ticks(prices)
        feed_path = _write_feed(tmp_path, rows)
        result = bg.simulate_strategy(strat, feed_path)
        assert "passed" in result
        assert "simulated_trades" in result
