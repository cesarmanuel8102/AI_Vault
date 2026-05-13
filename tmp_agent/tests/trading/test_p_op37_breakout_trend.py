"""
P-OP37: Breakout trend continuation enhancement tests.

Tests for ADX/DI/EMA/BB/RSI awareness added to _breakout_signal() in signal_engine.py.
Validates that breakout strategy correctly:
  - Boosts confidence when ADX confirms trend + DI aligned
  - Penalizes confidence in ranging markets (ADX < 15)
  - Hard-blocks breakout against confirmed trend (ADX > 25 + DI contradicts)
  - Adjusts confidence based on EMA 50 alignment
  - Adjusts confidence based on BB bandwidth
  - Rewards RSI continuation zone (40-65 CALL, 35-60 PUT)
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from brain_v9.trading.signal_engine import _breakout_signal


def _bo_feature(**overrides: Any) -> Dict[str, Any]:
    """Breakout-ready PO feature with sensible defaults for P-OP37 tests."""
    f: Dict[str, Any] = {
        "symbol": "EURUSD_otc",
        "venue": "pocket_option",
        "asset_class": "otc_binary",
        "market_regime": "trend_mild",
        "last_vs_close_pct": 0.15,
        "spread_pct": 0.02,
        "volatility_proxy_pct": 0.12,
        "recent_micro_move_pct": 0.06,
        "payout_pct": 85,
        "price_available": True,
        "last": 1.1050,
        "mid": 1.1049,
        # Indicator values — confluence +2 = CALL
        "rsi_14": 52.0,
        "bb_pct_b": 0.65,
        "stoch_k": 55.0,
        "stoch_d": 50.0,
        "macd_histogram": 0.001,
        "indicator_confluence": 2,
        # ADX / DI / EMA defaults — neutral (no effect)
        "adx": 0.0,
        "plus_di": 0.0,
        "minus_di": 0.0,
        "ema_50": 0.0,
        "ema_50_trend": "unknown",
        "bb_bandwidth": 0.05,
    }
    f.update(overrides)
    return f


def _confidence(feature: Dict[str, Any]) -> float:
    """Extract confidence from breakout signal evaluation."""
    return _breakout_signal(feature)["confidence"]


def _signal_valid(feature: Dict[str, Any]) -> bool:
    """Extract signal_valid from breakout signal evaluation."""
    return _breakout_signal(feature)["signal_valid"]


def _reasons(feature: Dict[str, Any]) -> list:
    """Extract reasons from breakout signal evaluation."""
    return _breakout_signal(feature)["reasons"]


# ── Baseline ─────────────────────────────────────────────────────────────────

class TestBreakoutBaseline:
    """Verify baseline breakout works without ADX/DI/EMA data."""

    def test_baseline_valid_signal(self):
        sig = _breakout_signal(_bo_feature())
        assert sig["signal_valid"] is True
        assert sig["direction"] == "call"

    def test_baseline_confidence_without_adx(self):
        # With ADX=0 (unavailable), no P-OP37 adjustments apply
        c = _confidence(_bo_feature())
        assert 0.5 < c < 0.8  # 0.35 + 2*0.15 = 0.65 baseline


# ── ADX + DI Confirms Breakout ──────────────────────────────────────────────

class TestBreakoutAdxDiConfirms:
    """ADX > 25 + DI aligned → confidence boost."""

    def test_adx_trend_di_confirms_call_boost(self):
        base_c = _confidence(_bo_feature())
        boosted_c = _confidence(_bo_feature(
            adx=30.0, plus_di=35.0, minus_di=20.0,  # +DI > -DI*1.1 → confirms CALL
        ))
        assert boosted_c > base_c
        assert boosted_c >= base_c + 0.07  # +0.08 from adx_di_confirms

    def test_adx_trend_di_confirms_put_boost(self):
        # Confluence -2 → PUT direction
        base_c = _confidence(_bo_feature(indicator_confluence=-2))
        boosted_c = _confidence(_bo_feature(
            indicator_confluence=-2,
            adx=30.0, plus_di=15.0, minus_di=30.0,  # -DI > +DI*1.1 → confirms PUT
        ))
        assert boosted_c > base_c
        assert boosted_c >= base_c + 0.07

    def test_adx_trend_di_confirms_reason(self):
        r = _reasons(_bo_feature(
            adx=30.0, plus_di=35.0, minus_di=20.0,
        ))
        assert "adx_di_confirms_breakout" in r

    def test_adx_trend_without_di_dominance(self):
        """ADX > 25 but DI not dominant enough → smaller boost."""
        base_c = _confidence(_bo_feature())
        boosted_c = _confidence(_bo_feature(
            adx=30.0, plus_di=25.0, minus_di=24.0,  # +DI > -DI but NOT > -DI*1.1
        ))
        assert boosted_c > base_c
        # +0.04 from adx_confirms, not +0.08
        r = _reasons(_bo_feature(adx=30.0, plus_di=25.0, minus_di=24.0))
        assert "adx_confirms_breakout" in r
        assert "adx_di_confirms_breakout" not in r


# ── ADX Range Penalty ────────────────────────────────────────────────────────

class TestBreakoutAdxRangePenalty:
    """ADX < 15 → breakout unreliable in ranging market."""

    def test_adx_low_penalizes(self):
        base_c = _confidence(_bo_feature())
        penalized_c = _confidence(_bo_feature(
            adx=12.0, plus_di=20.0, minus_di=18.0,
        ))
        assert penalized_c < base_c

    def test_adx_low_reason(self):
        r = _reasons(_bo_feature(adx=12.0, plus_di=20.0, minus_di=18.0))
        assert "adx_range_penalizes_breakout" in r

    def test_adx_20_no_penalty(self):
        """ADX = 20 is not < 15, so no range penalty."""
        r = _reasons(_bo_feature(adx=20.0, plus_di=20.0, minus_di=18.0))
        assert "adx_range_penalizes_breakout" not in r


# ── Hard Block: Breakout Against Confirmed Trend ─────────────────────────────

class TestBreakoutTrendContraBlock:
    """ADX > 25 + DI contradicts direction → hard block."""

    def test_call_against_bearish_trend_blocked(self):
        # Confluence +2 → CALL, but ADX > 25 and -DI > +DI → bearish trend
        valid = _signal_valid(_bo_feature(
            indicator_confluence=2,
            adx=30.0, plus_di=15.0, minus_di=30.0,  # bearish DI
        ))
        assert valid is False

    def test_put_against_bullish_trend_blocked(self):
        # Confluence -2 → PUT, but ADX > 25 and +DI > -DI → bullish trend
        valid = _signal_valid(_bo_feature(
            indicator_confluence=-2,
            adx=30.0, plus_di=30.0, minus_di=15.0,  # bullish DI
        ))
        assert valid is False

    def test_contra_block_reason(self):
        r = _reasons(_bo_feature(
            indicator_confluence=2,
            adx=30.0, plus_di=15.0, minus_di=30.0,
        ))
        assert "breakout_against_confirmed_trend" in r

    def test_no_block_when_adx_below_25(self):
        """ADX = 22 with DI contradicting → no hard block (only transition)."""
        valid = _signal_valid(_bo_feature(
            indicator_confluence=2,
            adx=22.0, plus_di=15.0, minus_di=30.0,
        ))
        # ADX < 25, so no hard block; signal_valid depends on other criteria
        r = _reasons(_bo_feature(
            indicator_confluence=2,
            adx=22.0, plus_di=15.0, minus_di=30.0,
        ))
        assert "breakout_against_confirmed_trend" not in r

    def test_aligned_not_blocked(self):
        """ADX > 25, DI aligned with direction → NOT blocked."""
        valid = _signal_valid(_bo_feature(
            indicator_confluence=2,
            adx=30.0, plus_di=35.0, minus_di=20.0,
        ))
        assert valid is True


# ── DI Confirms Without Strong ADX ──────────────────────────────────────────

class TestBreakoutDiConfirmsNoAdx:
    """DI aligned even without ADX > 25 → small bonus."""

    def test_di_confirms_without_strong_adx(self):
        base_c = _confidence(_bo_feature())
        boosted_c = _confidence(_bo_feature(
            adx=18.0, plus_di=30.0, minus_di=15.0,  # DI confirms CALL, ADX < 25
        ))
        assert boosted_c > base_c
        r = _reasons(_bo_feature(adx=18.0, plus_di=30.0, minus_di=15.0))
        assert "di_confirms_direction" in r


# ── EMA 50 Alignment ────────────────────────────────────────────────────────

class TestBreakoutEmaAlignment:
    """EMA 50 trend and price position affect breakout confidence."""

    def test_ema_confirms_call(self):
        """Price > EMA 50, trend bullish, direction CALL → boost."""
        base_c = _confidence(_bo_feature())
        boosted_c = _confidence(_bo_feature(
            ema_50=1.1000, ema_50_trend="bullish", last=1.1050,
        ))
        assert boosted_c > base_c
        r = _reasons(_bo_feature(ema_50=1.1000, ema_50_trend="bullish", last=1.1050))
        assert "ema_confirms_breakout" in r

    def test_ema_confirms_put(self):
        """Price < EMA 50, trend bearish, direction PUT → boost."""
        base_c = _confidence(_bo_feature(indicator_confluence=-2))
        boosted_c = _confidence(_bo_feature(
            indicator_confluence=-2,
            ema_50=1.1100, ema_50_trend="bearish", last=1.1050,
        ))
        assert boosted_c > base_c

    def test_ema_contradicts_call(self):
        """Trend bearish, direction CALL → penalty."""
        base_c = _confidence(_bo_feature())
        penalized_c = _confidence(_bo_feature(
            ema_50=1.1100, ema_50_trend="bearish", last=1.1050,
        ))
        assert penalized_c < base_c
        r = _reasons(_bo_feature(ema_50=1.1100, ema_50_trend="bearish", last=1.1050))
        assert "ema_contradicts_breakout" in r

    def test_ema_contradicts_put(self):
        """Trend bullish, direction PUT → penalty."""
        base_c = _confidence(_bo_feature(indicator_confluence=-2))
        penalized_c = _confidence(_bo_feature(
            indicator_confluence=-2,
            ema_50=1.1000, ema_50_trend="bullish", last=1.1050,
        ))
        assert penalized_c < base_c

    def test_ema_unknown_no_effect(self):
        """Unknown EMA trend → no adjustment."""
        base_c = _confidence(_bo_feature())
        neutral_c = _confidence(_bo_feature(
            ema_50=1.1000, ema_50_trend="unknown", last=1.1050,
        ))
        assert base_c == neutral_c


# ── BB Bandwidth ─────────────────────────────────────────────────────────────

class TestBreakoutBbBandwidth:
    """BB bandwidth affects breakout confidence."""

    def test_narrow_bandwidth_penalty(self):
        """bb_bandwidth < 0.03 → penalty."""
        base_c = _confidence(_bo_feature(bb_bandwidth=0.05))  # neutral
        penalized_c = _confidence(_bo_feature(bb_bandwidth=0.02))
        assert penalized_c < base_c
        r = _reasons(_bo_feature(bb_bandwidth=0.02))
        assert "bb_bandwidth_narrow" in r

    def test_wide_bandwidth_boost(self):
        """bb_bandwidth > 0.08 → boost."""
        base_c = _confidence(_bo_feature(bb_bandwidth=0.05))
        boosted_c = _confidence(_bo_feature(bb_bandwidth=0.10))
        assert boosted_c > base_c
        r = _reasons(_bo_feature(bb_bandwidth=0.10))
        assert "bb_bandwidth_expanding" in r

    def test_neutral_bandwidth_no_effect(self):
        """bb_bandwidth between 0.03 and 0.08 → no adjustment."""
        r = _reasons(_bo_feature(bb_bandwidth=0.05))
        assert "bb_bandwidth_narrow" not in r
        assert "bb_bandwidth_expanding" not in r


# ── RSI Continuation Zone ────────────────────────────────────────────────────

class TestBreakoutRsiContinuationZone:
    """RSI in continuation band gives breakout a boost."""

    def test_rsi_continuation_call(self):
        """RSI 52 (in 40-65) for CALL → bonus."""
        r = _reasons(_bo_feature(rsi_14=52.0))
        assert "rsi_continuation_zone" in r

    def test_rsi_outside_continuation_call(self):
        """RSI 30 (below 40) for CALL → no bonus."""
        r = _reasons(_bo_feature(rsi_14=30.0))
        assert "rsi_continuation_zone" not in r

    def test_rsi_continuation_put(self):
        """RSI 48 (in 35-60) for PUT → bonus."""
        r = _reasons(_bo_feature(indicator_confluence=-2, rsi_14=48.0))
        assert "rsi_continuation_zone" in r

    def test_rsi_overbought_no_continuation(self):
        """RSI 80 for CALL → no continuation bonus (above 65)."""
        r = _reasons(_bo_feature(rsi_14=80.0))
        assert "rsi_continuation_zone" not in r


# ── Full Stacked Scenario ────────────────────────────────────────────────────

class TestBreakoutFullStack:
    """Combined ADX + DI + EMA + BB + RSI in ideal breakout condition."""

    def test_ideal_trend_continuation_call(self):
        """All confirmations stacked for CALL breakout."""
        sig = _breakout_signal(_bo_feature(
            indicator_confluence=2,
            adx=30.0, plus_di=35.0, minus_di=20.0,   # ADX trend + DI confirms
            ema_50=1.1000, ema_50_trend="bullish", last=1.1050,  # EMA confirms
            bb_bandwidth=0.10,  # expanding
            rsi_14=52.0,  # continuation zone
        ))
        assert sig["signal_valid"] is True
        assert sig["confidence"] >= 0.75  # heavily boosted
        assert "adx_di_confirms_breakout" in sig["reasons"]
        assert "ema_confirms_breakout" in sig["reasons"]
        assert "bb_bandwidth_expanding" in sig["reasons"]
        assert "rsi_continuation_zone" in sig["reasons"]

    def test_worst_case_breakout_penalized(self):
        """All contradictions stacked → low confidence."""
        sig = _breakout_signal(_bo_feature(
            indicator_confluence=2,
            adx=12.0, plus_di=18.0, minus_di=20.0,   # range + DI mild contra
            ema_50=1.1100, ema_50_trend="bearish", last=1.1050,  # EMA contra
            bb_bandwidth=0.02,  # narrow
            rsi_14=30.0,  # outside continuation zone
        ))
        # Confidence should be significantly lower than baseline
        base_c = _confidence(_bo_feature())
        assert sig["confidence"] < base_c - 0.10
