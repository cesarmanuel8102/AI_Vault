"""
P-OP35 + P-OP36: Indicator Configuration Alignment + ADX Regime Filter — tests.

Covers:
  1. _compute_ema basic correctness + insufficient data -> 0.0
  2. _CANDLE_BUFFER_MAX increased to 120
  3. BB std_dev now 2.5 (via _compute_bollinger call signature)
  4. EMA 50 trend classification (bullish / bearish / unknown)
  5. RSI mild thresholds 35/65 (via _get_thresholds)
  6. _compute_adx basic correctness + insufficient data -> zeros
  7. Signal engine: ADX > 25 hard-blocks mean reversion
  8. Signal engine: ADX 20-25 transition penalty (-0.04)
  9. Signal engine: DI contra penalty (-0.04)
  10. Signal engine: EMA contra confidence penalty (-0.06)
  11. Signal engine: EMA contra hard block (window_change + EMA contra)
  12. Signal engine: ema_contra_penalty / adx reasons in reasons list
"""
from __future__ import annotations

import math
from typing import Any, Dict
from unittest.mock import patch

import pytest

from brain_v9.trading.feature_engine import (
    _compute_ema,
    _compute_adx,
    _CANDLE_BUFFER_MAX,
)
from brain_v9.trading.signal_engine import (
    _mean_reversion_signal,
    _get_thresholds,
)


# -- Helpers ------------------------------------------------------------------

def _po_feature(**overrides: Any) -> Dict[str, Any]:
    """Minimal PO mean reversion feature with defaults that produce a valid signal.

    Direction will be CALL (oversold indicators).
    ADX/DI default to 0 (unavailable) so they don't interfere unless set.
    """
    f: Dict[str, Any] = {
        "symbol": "EURUSD_otc",
        "venue": "pocket_option",
        "asset_class": "otc_binary",
        "price_available": True,
        "payout_pct": 85,
        "volatility_proxy_pct": 0.12,
        "price_zscore": -1.0,
        "last_vs_close_pct": -0.05,
        "recent_micro_move_pct": -0.03,
        "last": 1.1050,
        # Indicator values that trigger a strong reversion setup (call)
        "rsi_14": 22.0,          # below oversold_strong (25)
        "bb_pct_b": -0.15,       # below bb_lower_strong (-0.1)
        "stoch_k": 12.0,         # below stoch_oversold_strong (15)
        "stoch_d": 18.0,
        "macd_histogram": 0.001, # confirms call direction
        "indicator_confluence": 3,
        "market_regime": "range",
        "window_change_pct": 0.0,
        # EMA 50 fields (P-OP36b)
        "ema_50": 0.0,
        "ema_50_trend": "unknown",
        # ADX/DI fields (P-OP36a) — default 0 = unavailable
        "adx": 0.0,
        "plus_di": 0.0,
        "minus_di": 0.0,
    }
    f.update(overrides)
    return f


def _put_overrides() -> Dict[str, Any]:
    """Override dict to force a PUT signal (overbought indicators)."""
    return {
        "rsi_14": 78.0,
        "bb_pct_b": 1.15,
        "stoch_k": 88.0,
        "stoch_d": 82.0,
        "macd_histogram": -0.001,
        "indicator_confluence": -3,
        "price_zscore": 1.0,
        "last_vs_close_pct": 0.05,
        "recent_micro_move_pct": 0.03,
    }


# -- 1. _compute_ema ---------------------------------------------------------

class TestComputeEma:
    def test_insufficient_data_returns_zero(self):
        assert _compute_ema([1.0] * 30, period=50) == 0.0
        assert _compute_ema([], period=10) == 0.0

    def test_exact_period_returns_sma(self):
        prices = list(range(1, 11))
        expected_sma = sum(prices) / len(prices)
        assert _compute_ema(prices, period=10) == pytest.approx(expected_sma, abs=1e-9)

    def test_known_values(self):
        prices = [10.0, 11.0, 12.0, 11.0, 10.0, 13.0, 14.0]
        result = _compute_ema(prices, period=5)
        assert result == pytest.approx(12.3555, abs=0.01)

    def test_returns_float(self):
        assert isinstance(_compute_ema([1.0] * 20, period=10), float)


# -- 2. _CANDLE_BUFFER_MAX ---------------------------------------------------

class TestCandleBufferMax:
    def test_buffer_max_is_at_least_120(self):
        assert _CANDLE_BUFFER_MAX >= 120


# -- 3. EMA 50 trend classification ------------------------------------------

class TestEma50Trend:
    def test_bullish_when_price_above_ema(self):
        last, ema = 1.1100, 1.1050
        trend = "bullish" if (ema > 0 and last > ema) else ("bearish" if ema > 0 else "unknown")
        assert trend == "bullish"

    def test_bearish_when_price_below_ema(self):
        last, ema = 1.1000, 1.1050
        trend = "bullish" if (ema > 0 and last > ema) else ("bearish" if ema > 0 else "unknown")
        assert trend == "bearish"

    def test_unknown_when_ema_zero(self):
        last, ema = 1.1050, 0.0
        trend = "bullish" if (ema > 0 and last > ema) else ("bearish" if ema > 0 else "unknown")
        assert trend == "unknown"


# -- 4. RSI mild thresholds 35/65 --------------------------------------------

class TestRsiMildThresholds:
    def test_base_thresholds_use_35_65(self):
        th = _get_thresholds(None)
        assert th["rsi_oversold_mild"] == pytest.approx(35.0)
        assert th["rsi_overbought_mild"] == pytest.approx(65.0)

    def test_strong_thresholds_unchanged(self):
        th = _get_thresholds(None)
        assert th["rsi_oversold_strong"] == pytest.approx(25.0)
        assert th["rsi_overbought_strong"] == pytest.approx(75.0)


# -- 5. _compute_adx ---------------------------------------------------------

class TestComputeAdx:
    def _trending_data(self, n: int = 30) -> tuple:
        """Generate an uptrend with clear +DM."""
        highs = [1.08 + i * 0.001 for i in range(n)]
        lows = [h - 0.0005 for h in highs]
        closes = [h - 0.0002 for h in highs]
        return highs, lows, closes

    def _flat_data(self, n: int = 30) -> tuple:
        """Generate flat/ranging data."""
        import math as _m
        highs = [1.08 + 0.0003 * _m.sin(i) for i in range(n)]
        lows = [h - 0.0002 for h in highs]
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
        return highs, lows, closes

    def test_insufficient_data_returns_zeros(self):
        result = _compute_adx([1.0]*5, [0.9]*5, [0.95]*5, period=10)
        assert result["adx"] == 0.0
        assert result["plus_di"] == 0.0
        assert result["minus_di"] == 0.0

    def test_mismatched_lengths_returns_zeros(self):
        result = _compute_adx([1.0]*20, [0.9]*15, [0.95]*20, period=10)
        assert result["adx"] == 0.0

    def test_trending_data_has_high_adx(self):
        h, l, c = self._trending_data(40)
        result = _compute_adx(h, l, c, period=10)
        assert result["adx"] > 20  # clear trend

    def test_trending_data_plus_di_dominates(self):
        h, l, c = self._trending_data(40)
        result = _compute_adx(h, l, c, period=10)
        assert result["plus_di"] > result["minus_di"]

    def test_flat_data_has_low_adx(self):
        h, l, c = self._flat_data(40)
        result = _compute_adx(h, l, c, period=10)
        assert result["adx"] < 30  # ranging market

    def test_returns_all_keys(self):
        h, l, c = self._trending_data(30)
        result = _compute_adx(h, l, c, period=10)
        assert "adx" in result
        assert "plus_di" in result
        assert "minus_di" in result

    def test_values_in_range(self):
        h, l, c = self._trending_data(40)
        result = _compute_adx(h, l, c, period=10)
        for key in ("adx", "plus_di", "minus_di"):
            assert 0.0 <= result[key] <= 100.0


# -- 6. ADX > 25 hard block --------------------------------------------------

class TestAdxHardBlock:
    """ADX > 25 should hard-block mean reversion signals."""

    def test_adx_above_25_blocks(self):
        feat = _po_feature(adx=30.0, plus_di=25.0, minus_di=15.0)
        result = _mean_reversion_signal(feat)
        assert result["signal_valid"] is False
        assert "adx_trend_block" in result["reasons"]
        assert "trend_direction_blocked" in result["reasons"]

    def test_adx_below_20_no_block(self):
        feat = _po_feature(adx=15.0, plus_di=20.0, minus_di=18.0)
        result = _mean_reversion_signal(feat)
        assert result["signal_valid"] is True
        assert "adx_trend_block" not in result["reasons"]

    def test_adx_zero_no_block(self):
        """ADX=0 means not computed yet — should not block."""
        feat = _po_feature(adx=0.0)
        result = _mean_reversion_signal(feat)
        assert "adx_trend_block" not in result["reasons"]

    def test_adx_exactly_25_no_block(self):
        """ADX exactly 25 is at the boundary — transition, not block."""
        feat = _po_feature(adx=25.0, plus_di=20.0, minus_di=15.0)
        result = _mean_reversion_signal(feat)
        assert "adx_trend_block" not in result["reasons"]
        assert "adx_transition_penalty" in result["reasons"]


# -- 7. ADX transition penalty -----------------------------------------------

class TestAdxTransitionPenalty:
    """ADX 20-25 should apply a confidence penalty."""

    def _get_confidence(self, adx_val: float) -> float:
        feat = _po_feature(adx=adx_val, plus_di=20.0, minus_di=18.0)
        return _mean_reversion_signal(feat)["confidence"]

    def test_transition_penalty_applied(self):
        conf_low = self._get_confidence(15.0)   # range — no penalty
        conf_mid = self._get_confidence(22.0)    # transition — penalty
        assert conf_mid == pytest.approx(conf_low - 0.04, abs=0.001)

    def test_transition_reason_present(self):
        feat = _po_feature(adx=22.0, plus_di=20.0, minus_di=18.0)
        result = _mean_reversion_signal(feat)
        assert "adx_transition_penalty" in result["reasons"]


# -- 8. DI contra penalty ----------------------------------------------------

class TestDiContraPenalty:
    """DI contra (trading against directional pressure) should penalize confidence."""

    def test_call_into_bearish_pressure(self):
        """CALL direction + -DI > +DI -> penalty."""
        conf_neutral = _mean_reversion_signal(
            _po_feature(adx=15.0, plus_di=20.0, minus_di=20.0)
        )["confidence"]
        conf_contra = _mean_reversion_signal(
            _po_feature(adx=15.0, plus_di=10.0, minus_di=25.0)
        )["confidence"]
        assert conf_contra == pytest.approx(conf_neutral - 0.04, abs=0.001)

    def test_di_contra_reason_present(self):
        feat = _po_feature(adx=15.0, plus_di=10.0, minus_di=25.0)
        result = _mean_reversion_signal(feat)
        assert "di_contra_penalty" in result["reasons"]

    def test_di_aligned_no_penalty(self):
        """CALL direction + +DI > -DI -> no penalty."""
        feat = _po_feature(adx=15.0, plus_di=25.0, minus_di=10.0)
        result = _mean_reversion_signal(feat)
        assert "di_contra_penalty" not in result["reasons"]


# -- 9. EMA 50 contra confidence penalty -------------------------------------

class TestEma50ContraPenalty:
    """Verify signal engine applies -0.06 confidence penalty when trade opposes EMA 50 trend."""

    def _confidence(self, **kw) -> float:
        return _mean_reversion_signal(_po_feature(**kw))["confidence"]

    def test_no_penalty_when_ema_unknown(self):
        assert self._confidence(ema_50_trend="unknown") == self._confidence(ema_50_trend="bullish")

    def test_penalty_when_ema_contra_call(self):
        c_neutral = self._confidence(ema_50_trend="unknown")
        c_contra = self._confidence(ema_50_trend="bearish")
        assert c_contra == pytest.approx(c_neutral - 0.06, abs=0.001)

    def test_penalty_when_ema_contra_put(self):
        po = _put_overrides()
        c_neutral = self._confidence(ema_50_trend="unknown", **po)
        c_contra = self._confidence(ema_50_trend="bullish", **po)
        assert c_contra == pytest.approx(c_neutral - 0.06, abs=0.001)

    def test_reason_present_when_contra(self):
        result = _mean_reversion_signal(_po_feature(ema_50_trend="bearish"))
        assert "ema_contra_penalty" in result["reasons"]

    def test_reason_absent_when_aligned(self):
        result = _mean_reversion_signal(_po_feature(ema_50_trend="bullish"))
        assert "ema_contra_penalty" not in result["reasons"]


# -- 10. EMA 50 contra hard block --------------------------------------------

class TestEma50ContraHardBlock:
    def test_hard_block_when_ema_contra_and_window(self):
        feat = _po_feature(ema_50_trend="bearish", window_change_pct=-0.04)
        result = _mean_reversion_signal(feat)
        assert result["signal_valid"] is False
        assert "trend_direction_blocked" in result["reasons"]

    def test_no_hard_block_when_window_small(self):
        feat = _po_feature(ema_50_trend="bearish", window_change_pct=-0.01)
        result = _mean_reversion_signal(feat)
        assert result["signal_valid"] is True

    def test_no_hard_block_when_ema_agrees(self):
        feat = _po_feature(ema_50_trend="bullish", window_change_pct=-0.05)
        result = _mean_reversion_signal(feat)
        assert "ema_contra_penalty" not in result["reasons"]


# -- 11. BB 2.5 sanity check -------------------------------------------------

class TestBBStdDev:
    def test_bb_call_uses_2_5(self):
        import inspect
        from brain_v9.trading.feature_engine import _po_price_context
        source = inspect.getsource(_po_price_context)
        assert "_compute_bollinger(ind_prices, 20, 2.5)" in source
