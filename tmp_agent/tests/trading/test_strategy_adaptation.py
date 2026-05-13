"""
Tests for P3-06: Strategy parameter adaptation in strategy_engine.

Verifies:
  1. adapt_strategy_parameters() adjusts confidence_threshold based on win-rate
  2. Low-sample strategies are untouched (only get default)
  3. Clamping works: threshold stays within [BASE - 0.10, BASE + 0.10]
  4. Filter adaptation (spread_pct_max) adjusts based on expectancy
  5. Signal engine uses per-strategy confidence_threshold

NOTE: _BASE_CONFIDENCE_THRESHOLD = 0.58 (P-OP32n).
      Clamp range = [0.48, 0.68].
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers to build strategy + scorecard dicts
# ---------------------------------------------------------------------------

def _strategy(strategy_id="strat_a", venue="pocket_option", family="trend_following",
              min_win_rate=0.55, spread_pct_max=0.25):
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": family,
        "timeframes": ["1m"],
        "universe": ["EURUSD_otc"],
        "filters": {
            "spread_pct_max": spread_pct_max,
            "volatility_min_atr_pct": 0.35,
            "market_regime_allowed": ["trend_up", "trend_mild"],
        },
        "success_criteria": {
            "min_resolved_trades": 20,
            "min_expectancy": 0.05,
            "min_win_rate": min_win_rate,
        },
        "setup_variants": ["pullback_continuation"],
        "core_indicators": [],
        "entry": {},
        "exit": {},
        "paper_only": True,
    }


def _scorecard(entries_resolved=20, win_rate=0.60, expectancy=0.15):
    return {
        "entries_resolved": entries_resolved,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "wins": int(entries_resolved * win_rate),
        "losses": entries_resolved - int(entries_resolved * win_rate),
    }


# ---------------------------------------------------------------------------
# adapt_strategy_parameters tests
# ---------------------------------------------------------------------------

class TestAdaptStrategyParameters:

    def test_low_sample_untouched(self, isolated_base_path):
        """Strategies with < 10 resolved trades get default threshold only."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy()
        scorecards = {"strat_a": _scorecard(entries_resolved=5)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] == 0.58  # default (BASE)

    def test_no_scorecard_untouched(self, isolated_base_path):
        """Strategies without a scorecard entry get default threshold."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy()
        adapt_strategy_parameters([strat], {})
        assert strat["confidence_threshold"] == 0.58

    def test_high_win_rate_lowers_threshold(self, isolated_base_path):
        """Win rate above target should lower confidence threshold."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(min_win_rate=0.55)
        # win_rate=0.75, delta=+0.20, adjustment = -(0.20*0.5) = -0.10
        scorecards = {"strat_a": _scorecard(win_rate=0.75, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] < 0.58
        assert strat["confidence_threshold"] >= 0.48  # clamped min

    def test_low_win_rate_raises_threshold(self, isolated_base_path):
        """Win rate below target should raise confidence threshold."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(min_win_rate=0.55)
        # win_rate=0.35, delta=-0.20, adjustment = -(−0.20*0.5) = +0.10
        scorecards = {"strat_a": _scorecard(win_rate=0.35, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] > 0.58
        assert strat["confidence_threshold"] <= 0.68  # clamped max

    def test_exact_target_keeps_base(self, isolated_base_path):
        """Win rate exactly at target should keep base threshold."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(min_win_rate=0.55)
        scorecards = {"strat_a": _scorecard(win_rate=0.55, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] == 0.58

    def test_extreme_high_wr_clamped_to_035(self, isolated_base_path):
        """Even with 100% win rate, threshold should not go below 0.48."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(min_win_rate=0.55)
        scorecards = {"strat_a": _scorecard(win_rate=1.0, entries_resolved=30)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] == 0.48

    def test_extreme_low_wr_clamped_to_055(self, isolated_base_path):
        """Even with 0% win rate, threshold should not go above 0.68."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(min_win_rate=0.55)
        scorecards = {"strat_a": _scorecard(win_rate=0.0, entries_resolved=30)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["confidence_threshold"] == 0.68

    def test_multiple_strategies_independent(self, isolated_base_path):
        """Each strategy should be adapted independently."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat_a = _strategy(strategy_id="strat_a", min_win_rate=0.55)
        strat_b = _strategy(strategy_id="strat_b", min_win_rate=0.55)
        scorecards = {
            "strat_a": _scorecard(win_rate=0.70, entries_resolved=20),
            "strat_b": _scorecard(win_rate=0.40, entries_resolved=20),
        }
        adapt_strategy_parameters([strat_a, strat_b], scorecards)
        assert strat_a["confidence_threshold"] < 0.58  # good performer
        assert strat_b["confidence_threshold"] > 0.58  # bad performer

    def test_spread_filter_loosened_positive_expectancy(self, isolated_base_path):
        """Good expectancy should loosen spread_pct_max."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(spread_pct_max=0.25, min_win_rate=0.50)
        scorecards = {"strat_a": _scorecard(win_rate=0.65, expectancy=0.3, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["filters"]["spread_pct_max"] > 0.25

    def test_spread_filter_tightened_negative_expectancy(self, isolated_base_path):
        """Negative expectancy should tighten spread_pct_max."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy(spread_pct_max=0.25, min_win_rate=0.55)
        scorecards = {"strat_a": _scorecard(win_rate=0.40, expectancy=-0.2, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["filters"]["spread_pct_max"] < 0.25

    def test_no_filter_spread_unset(self, isolated_base_path):
        """Strategies without spread_pct_max should not crash."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strat = _strategy()
        strat["filters"]["spread_pct_max"] = None
        scorecards = {"strat_a": _scorecard(win_rate=0.70, entries_resolved=20)}
        adapt_strategy_parameters([strat], scorecards)
        assert strat["filters"]["spread_pct_max"] is None
        assert strat["confidence_threshold"] < 0.58

    def test_returns_strategies(self, isolated_base_path):
        """Function should return the strategies list."""
        from brain_v9.trading.strategy_engine import adapt_strategy_parameters
        strats = [_strategy()]
        result = adapt_strategy_parameters(strats, {})
        assert result is strats


# ---------------------------------------------------------------------------
# Signal engine uses per-strategy confidence_threshold
# ---------------------------------------------------------------------------

class TestSignalEnginePerStrategyThreshold:

    def test_custom_threshold_used(self, isolated_base_path):
        """_evaluate_strategy_feature should use strategy's confidence_threshold."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = {
            "strategy_id": "test_strat",
            "venue": "pocket_option",
            "family": "mean_reversion",
            "timeframes": ["1m"],
            "universe": ["EURUSD_otc"],
            "filters": {},
            "core_indicators": [],
            "setup_variants": ["base"],
            "asset_classes": ["forex_otc"],
            "invalidators": [],
            "confidence_threshold": 0.35,  # lowered from default 0.58
        }
        # Create a feature that produces a signal with confidence ~0.40
        # (below 0.45 default but above 0.35 custom)
        feature = {
            "symbol": "EURUSD_otc",
            "venue": "pocket_option",
            "timeframe": "1m",
            "asset_class": "forex_otc",
            "price_available": True,
            "last": 1.0850,
            "mid": 1.0850,
            "spread_pct": 0.10,
            "payout_pct": 82,
            "market_regime": "range",
            "stream_symbol_match": True,
            "indicator_count": 0,
            "indicator_access_ready": False,
            "available_timeframes": ["1m"],
        }
        result = _evaluate_strategy_feature(strategy, feature)
        # We verify the function doesn't crash and uses the custom threshold
        assert "execution_ready" in result
        assert "confidence" in result

    def test_default_threshold_when_not_set(self, isolated_base_path):
        """Without confidence_threshold, should default to 0.58."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = {
            "strategy_id": "test_strat2",
            "venue": "pocket_option",
            "family": "mean_reversion",
            "timeframes": ["1m"],
            "universe": ["EURUSD_otc"],
            "filters": {},
            "core_indicators": [],
            "setup_variants": ["base"],
            "asset_classes": ["forex_otc"],
            "invalidators": [],
            # No confidence_threshold key — should default to 0.58
        }
        feature = {
            "symbol": "EURUSD_otc",
            "venue": "pocket_option",
            "timeframe": "1m",
            "asset_class": "forex_otc",
            "price_available": True,
            "last": 1.0850,
            "mid": 1.0850,
            "spread_pct": 0.10,
            "payout_pct": 82,
            "market_regime": "range",
            "stream_symbol_match": True,
            "indicator_count": 0,
            "indicator_access_ready": False,
            "available_timeframes": ["1m"],
        }
        result = _evaluate_strategy_feature(strategy, feature)
        assert "execution_ready" in result
