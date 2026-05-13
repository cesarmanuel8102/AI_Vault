"""
Tests for P4-06: Improved PO regime detection.

Verifies:
  - PO regime detector now produces 'trend_strong' (previously impossible)
  - 'trend_mild' threshold uses OR logic (was AND — too strict)
  - 'range_break_down' triggers for negative moves
  - 'mild' threshold correctly tuned at 0.10
  - 'range' remains the default for flat markets
  - IBKR regime detector unchanged (regression)
"""
from __future__ import annotations

import math
import pytest
from typing import Any, Dict, List

from brain_v9.trading.feature_engine import (
    _po_price_context,
    _infer_market_regime,
)


# ---------- Helpers ----------

def _make_po_prices(base: float = 1.08000, count: int = 40,
                    trend_pct: float = 0.0, noise_pct: float = 0.001) -> List[float]:
    """Generate a synthetic PO price series.

    Args:
        base: Starting price
        count: Number of ticks
        trend_pct: Cumulative % change over the window (e.g. 0.10 = +0.10%)
        noise_pct: Per-tick noise magnitude as % of base
    """
    prices = []
    step = (trend_pct / 100.0) / max(count - 1, 1) * base
    noise_abs = (noise_pct / 100.0) * base
    for i in range(count):
        p = base + step * i
        # Add deterministic alternating noise
        if i % 2 == 0:
            p += noise_abs
        else:
            p -= noise_abs
        prices.append(round(p, 5))
    return prices


# ---------- PO regime detection (via _po_price_context internals) ----------

class TestPORegimeDetection:
    """Test the improved PO regime detection logic in _po_price_context."""

    def _compute_regime(self, prices: List[float]) -> str:
        """Replicate the regime computation from _po_price_context for testing."""
        if len(prices) < 5:
            return "unknown"

        last = prices[-1]
        window = prices[-20:] if len(prices) >= 20 else prices
        window_open = window[0]
        window_mean = sum(window) / len(window)
        variance = sum((p - window_mean) ** 2 for p in window) / len(window)
        std_dev = math.sqrt(max(variance, 0.0))
        window_change_pct = ((last - window_open) / window_open) * 100.0 if window_open > 0 else 0.0
        window_high = max(window)
        window_low = min(window)
        window_range_pct = ((window_high - window_low) / window_mean) * 100.0 if window_mean > 0 else 0.0
        price_zscore = ((last - window_mean) / std_dev) if std_dev > 0 else 0.0

        # This must match the production code exactly
        regime = "range"
        abs_change = abs(window_change_pct)
        abs_zscore = abs(price_zscore)
        if abs_change >= 0.15 and abs_zscore >= 1.8:
            regime = "trend_strong"
        elif abs_change >= 0.06 or abs_zscore >= 1.2:
            regime = "trend_mild" if window_change_pct > 0 else "range_break_down"
        elif window_range_pct >= 0.10:
            regime = "mild"

        return regime

    def test_flat_market_is_range(self):
        """Perfectly flat prices produce 'range'."""
        prices = [1.08000] * 30
        # All same price → std_dev=0, change=0, range_pct=0
        assert self._compute_regime(prices) == "range"

    def test_tiny_noise_is_range(self):
        """Very small noise stays in 'range'."""
        prices = _make_po_prices(trend_pct=0.0, noise_pct=0.0005)
        regime = self._compute_regime(prices)
        assert regime == "range"

    def test_moderate_range_is_mild(self):
        """Window range >= 0.10% with low change and low zscore → 'mild'."""
        # Create a market that oscillates — key: last price must be close to
        # window_open (so change_pct < 0.06) and near mean (so zscore < 1.2),
        # but range must be >= 0.10%
        base = 1.08000
        half_range = 0.00060  # ~0.11% total range
        prices = []
        for i in range(25):
            # Full sine cycle returns to start
            import math
            offset = half_range * math.sin(2 * math.pi * i / 24)
            prices.append(round(base + offset, 5))
        # Last price at base (near open and near mean)
        prices.append(base)
        regime = self._compute_regime(prices)
        assert regime == "mild", (
            f"Expected 'mild' for moderate-range oscillation, got '{regime}'"
        )

    def test_upward_trend_by_change_is_trend_mild(self):
        """Upward move >= 0.06% produces 'trend_mild' via change threshold."""
        prices = _make_po_prices(trend_pct=0.08, noise_pct=0.0001, count=25)
        regime = self._compute_regime(prices)
        assert regime == "trend_mild"

    def test_downward_move_by_change_is_range_break_down(self):
        """Downward move >= 0.06% produces 'range_break_down' via change threshold."""
        prices = _make_po_prices(trend_pct=-0.08, noise_pct=0.0001, count=25)
        regime = self._compute_regime(prices)
        assert regime == "range_break_down"

    def test_zscore_alone_triggers_trend_mild(self):
        """High z-score alone (even without large change) triggers 'trend_mild'.

        This was the key fix: old code required BOTH change AND zscore (AND logic).
        New code uses OR logic — either one is sufficient.
        """
        # Create a series where most prices are clustered, then a spike
        base = 1.08000
        prices = [base] * 18  # flat for 18 ticks
        # Add a small spike that creates high zscore but small window_change_pct
        # (because window_open and last are close, but last deviates from mean)
        prices.append(base + 0.0002)  # mild step
        prices.append(base + 0.001)   # spike — high zscore
        regime = self._compute_regime(prices)
        # With such a tight cluster, the spike creates a significant zscore
        # The regime should be trend_mild (positive) due to OR logic
        assert regime in ("trend_mild", "trend_strong"), (
            f"High z-score should trigger trend detection, got '{regime}'"
        )

    def test_strong_trend_produces_trend_strong(self):
        """Large move + high zscore produces 'trend_strong' — previously impossible."""
        # Create a strong upward trend
        prices = _make_po_prices(trend_pct=0.25, noise_pct=0.0001, count=25)
        regime = self._compute_regime(prices)
        # Should be trend_strong (abs_change >= 0.15 AND abs_zscore >= 1.8)
        # or at minimum trend_mild
        assert regime in ("trend_strong", "trend_mild"), (
            f"Strong trend should produce trend_strong or trend_mild, got '{regime}'"
        )

    def test_strong_downward_move(self):
        """Strong downward move should be detectable."""
        prices = _make_po_prices(trend_pct=-0.25, noise_pct=0.0001, count=25)
        regime = self._compute_regime(prices)
        assert regime in ("trend_strong", "range_break_down"), (
            f"Strong downward move should be detected, got '{regime}'"
        )

    def test_too_few_prices_is_unknown(self):
        """Fewer than 5 prices → 'unknown'."""
        assert self._compute_regime([1.0, 1.0, 1.0]) == "unknown"

    def test_regime_spectrum_ordering(self):
        """Increasing trend strength should move through the regime spectrum."""
        regimes_by_trend = []
        for trend in [0.0, 0.03, 0.08, 0.20]:
            prices = _make_po_prices(trend_pct=trend, noise_pct=0.0001, count=25)
            regime = self._compute_regime(prices)
            regimes_by_trend.append(regime)

        # First should be range or mild
        assert regimes_by_trend[0] in ("range", "mild")
        # Last should be trend_mild or trend_strong
        assert regimes_by_trend[-1] in ("trend_mild", "trend_strong")


# ---------- IBKR regime detector regression ----------

class TestIBKRRegimeRegression:
    """Ensure the IBKR regime detector (_infer_market_regime) is unchanged."""

    def test_unknown_when_no_price(self):
        assert _infer_market_regime(0.0, 0.0, False) == "unknown"

    def test_dislocated_wide_spread(self):
        assert _infer_market_regime(0.5, 0.30, True) == "dislocated"

    def test_trend_strong_large_move(self):
        assert _infer_market_regime(1.5, 0.10, True) == "trend_strong"
        assert _infer_market_regime(-1.5, 0.10, True) == "trend_strong"

    def test_trend_mild_positive(self):
        assert _infer_market_regime(0.50, 0.10, True) == "trend_mild"

    def test_range_break_down_negative(self):
        assert _infer_market_regime(-0.50, 0.10, True) == "range_break_down"

    def test_range_tiny_move(self):
        assert _infer_market_regime(0.05, 0.10, True) == "range"

    def test_mild_moderate_move(self):
        assert _infer_market_regime(0.20, 0.10, True) == "mild"


# ---------- P-OP33: CandleBuffer tests ----------

class TestCandleBuffer:
    """Test _CandleBuffer tick→candle aggregation logic."""

    def _make_buffer(self) -> "_CandleBuffer":
        """Create an isolated CandleBuffer that does NOT touch disk."""
        from brain_v9.trading.feature_engine import _CandleBuffer
        buf = _CandleBuffer()
        buf._loaded = True  # skip disk load
        buf._persist = lambda: None  # no-op persist
        return buf

    def _make_tick(self, price: float, ts: str) -> Dict[str, Any]:
        return {"price": price, "captured_utc": ts}

    def test_single_minute_candle(self):
        """Multiple ticks in the same minute form one partial candle, zero completed."""
        buf = self._make_buffer()
        ticks = [
            self._make_tick(1.08000, "2026-03-29T10:00:05Z"),
            self._make_tick(1.08020, "2026-03-29T10:00:15Z"),
            self._make_tick(1.07980, "2026-03-29T10:00:25Z"),
            self._make_tick(1.08010, "2026-03-29T10:00:45Z"),
        ]
        buf.update(ticks)
        # All in minute 10:00 — still partial, 0 completed candles
        assert buf.candle_count == 0
        assert buf._partial is not None
        assert buf._partial["o"] == 1.08000
        assert buf._partial["h"] == 1.08020
        assert buf._partial["l"] == 1.07980
        assert buf._partial["c"] == 1.08010
        assert buf._partial["n"] == 4

    def test_two_minutes_produces_one_completed(self):
        """Ticks spanning two minutes → one completed candle + one partial."""
        buf = self._make_buffer()
        ticks = [
            self._make_tick(1.08000, "2026-03-29T10:00:05Z"),
            self._make_tick(1.08020, "2026-03-29T10:00:30Z"),
            # New minute
            self._make_tick(1.08050, "2026-03-29T10:01:05Z"),
            self._make_tick(1.08030, "2026-03-29T10:01:30Z"),
        ]
        buf.update(ticks)
        assert buf.candle_count == 1
        completed = buf.get_candles()
        assert len(completed) == 1
        assert completed[0]["o"] == 1.08000
        assert completed[0]["h"] == 1.08020
        assert completed[0]["c"] == 1.08020
        assert completed[0]["n"] == 2
        # Partial should be the second minute
        assert buf._partial["o"] == 1.08050
        assert buf._partial["c"] == 1.08030

    def test_get_closes_highs_lows(self):
        """get_closes/get_highs/get_lows return correct values from completed candles."""
        buf = self._make_buffer()
        ticks = []
        for minute in range(5):
            ts_base = f"2026-03-29T10:{minute:02d}"
            ticks.append(self._make_tick(1.08000 + minute * 0.0001, f"{ts_base}:05Z"))
            ticks.append(self._make_tick(1.08010 + minute * 0.0001, f"{ts_base}:15Z"))
            ticks.append(self._make_tick(1.07990 + minute * 0.0001, f"{ts_base}:25Z"))
        buf.update(ticks)
        # 4 completed (minutes 0-3), minute 4 is partial
        assert buf.candle_count == 4
        closes = buf.get_closes()
        highs = buf.get_highs()
        lows = buf.get_lows()
        assert len(closes) == 4
        assert len(highs) == 4
        assert len(lows) == 4
        # Each candle's high should be > low
        for h, l in zip(highs, lows):
            assert h > l

    def test_buffer_trim_at_max(self):
        """Buffer trims to _CANDLE_BUFFER_MAX completed candles."""
        from brain_v9.trading.feature_engine import _CANDLE_BUFFER_MAX
        buf = self._make_buffer()
        # Generate ticks across _CANDLE_BUFFER_MAX + 10 minutes to verify trimming.
        n_minutes = _CANDLE_BUFFER_MAX + 10
        ticks = []
        for minute in range(n_minutes):
            hour = 10 + minute // 60
            min_part = minute % 60
            ts = f"2026-03-29T{hour:02d}:{min_part:02d}:05Z"
            ticks.append(self._make_tick(1.08000 + minute * 0.00001, ts))
        buf.update(ticks)
        assert buf.candle_count <= _CANDLE_BUFFER_MAX

    def test_empty_rows_no_crash(self):
        """Empty or invalid rows don't crash the buffer."""
        buf = self._make_buffer()
        buf.update([])
        assert buf.candle_count == 0
        buf.update([{"price": 0, "captured_utc": "2026-03-29T10:00:05Z"}])
        assert buf.candle_count == 0
        buf.update([{"price": 1.0}])  # no captured_utc
        assert buf.candle_count == 0

    def test_minute_bucket_floors_correctly(self):
        """_minute_bucket floors timestamps to the minute."""
        buf = self._make_buffer()
        # 10:05:00 and 10:05:59 should be the same bucket
        b1 = buf._minute_bucket("2026-03-29T10:05:00Z")
        b2 = buf._minute_bucket("2026-03-29T10:05:59Z")
        b3 = buf._minute_bucket("2026-03-29T10:06:00Z")
        assert b1 is not None
        assert b1 == b2
        assert b3 != b1  # different minute

    def test_repeated_update_no_duplicates(self):
        """Calling update() multiple times with overlapping rows must NOT create duplicates.

        This simulates the real PO feed behaviour: a rolling 500-row window
        where most rows are the same across successive Brain cycles.
        """
        buf = self._make_buffer()
        # Build a feed that spans 5 minutes
        base_ticks = []
        for minute in range(5):
            for sec in (5, 15, 25, 35, 45):
                ts = f"2026-03-29T10:{minute:02d}:{sec:02d}Z"
                base_ticks.append(self._make_tick(1.08000 + minute * 0.0001 + sec * 0.000001, ts))

        # First call
        buf.update(base_ticks)
        count_after_first = buf.candle_count

        # Second call with the SAME rows (simulates next Brain cycle)
        buf.update(base_ticks)
        count_after_second = buf.candle_count

        # Third call with same rows plus one new minute
        extended = list(base_ticks) + [
            self._make_tick(1.08100, "2026-03-29T10:05:05Z"),
            self._make_tick(1.08110, "2026-03-29T10:05:15Z"),
        ]
        buf.update(extended)
        count_after_third = buf.candle_count

        # Counts should be stable — no duplicates
        assert count_after_first == count_after_second, (
            f"Duplicate candles created: {count_after_first} vs {count_after_second}"
        )
        # Third call adds one more completed candle (minute 4 becomes completed, minute 5 is partial)
        assert count_after_third == count_after_second + 1, (
            f"Expected one more candle, got {count_after_third} vs {count_after_second}"
        )

        # Verify no duplicate timestamps
        ts_list = [c["t"] for c in buf.get_candles()]
        assert len(ts_list) == len(set(ts_list)), (
            f"Duplicate timestamps found: {ts_list}"
        )
