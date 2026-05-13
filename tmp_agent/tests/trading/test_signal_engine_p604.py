"""
P6-04  Signal engine tests — Phase 6 Sprint 2.

Tests for brain_v9/trading/signal_engine.py:
 1. Helper functions (_safe_float, _clamp, _utc_now)
 2. Strategy filter pass (_strategy_filter_pass)
 3. Indicator support (_indicator_support)
 4. Signal generators (_trend_signal, _breakout_signal, _mean_reversion_signal)
 5. Full evaluation (_evaluate_strategy_feature)
 6. Snapshot builder (build_strategy_signal_snapshot)
 7. Stale data rejection (P5-09)
 8. Confidence threshold (P3-06)
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from brain_v9.trading.signal_engine import (
    _breakout_signal,
    _clamp,
    _evaluate_strategy_feature,
    _indicator_support,
    _mean_reversion_signal,
    _safe_float,
    _strategy_filter_pass,
    _trend_signal,
    _utc_now,
    build_strategy_signal_snapshot,
    read_strategy_signal_snapshot,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _base_feature(**overrides: Any) -> Dict[str, Any]:
    """Minimal feature that passes most filters."""
    f: Dict[str, Any] = {
        "symbol": "EURUSD_otc",
        "venue": "pocket_option",
        "asset_class": "otc_binary",
        "timeframe": "spot",
        "market_regime": "trend_strong",
        "spread_pct": 0.02,
        "volatility_proxy_pct": 0.12,
        "last_vs_close_pct": 0.5,
        "bid_ask_imbalance": 0.3,
        "liquidity_score": 0.8,
        "price_available": True,
        "price_zscore": 0.1,
        "recent_micro_move_pct": 0.05,
        "payout_pct": 85,
        "is_stale": False,
        "data_age_seconds": 60,
        "last": 1.1050,
        "mid": 1.1049,
        "key": "po_EURUSD_otc",
        "captured_utc": "2026-03-01T00:00:00Z",
        "indicator_candidates": ["RSI", "MACD"],
        "indicator_count": 2,
        "indicator_access_ready": True,
        "stream_symbol_match": True,
        "visible_symbol": "EURUSD_otc",
        "last_stream_symbol": "EURUSD_otc",
        "available_timeframes": ["spot"],
    }
    f.update(overrides)
    return f


def _base_strategy(**overrides: Any) -> Dict[str, Any]:
    """Minimal strategy matching _base_feature."""
    s: Dict[str, Any] = {
        "strategy_id": "test_strat_01",
        "venue": "pocket_option",
        "family": "breakout",
        "universe": ["EURUSD_otc"],
        "asset_classes": ["otc_binary"],
        "timeframes": ["spot"],
        "core_indicators": [],
        "filters": {
            "market_regime_allowed": ["trend_strong", "range"],
            "spread_pct_max": 0.10,
            "volatility_min_atr_pct": 0.01,
        },
        "setup_variants": ["base"],
        "confidence_threshold": 0.45,
    }
    s.update(overrides)
    return s


# ===================================================================
# 1. Helpers
# ===================================================================

class TestSafeFloat:
    def test_valid_int(self):
        assert _safe_float(5) == 5.0

    def test_valid_string(self):
        assert _safe_float("3.14") == 3.14

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_none_custom_default(self):
        assert _safe_float(None, 99.0) == 99.0

    def test_garbage_returns_default(self):
        assert _safe_float("abc") == 0.0

    def test_bool_true(self):
        assert _safe_float(True) == 1.0


class TestClamp:
    def test_within(self):
        assert _clamp(0.5, 0.0, 1.0) == 0.5

    def test_below(self):
        assert _clamp(-1.0, 0.0, 1.0) == 0.0

    def test_above(self):
        assert _clamp(2.0, 0.0, 1.0) == 1.0

    def test_at_boundary(self):
        assert _clamp(0.0, 0.0, 1.0) == 0.0
        assert _clamp(1.0, 0.0, 1.0) == 1.0


class TestUtcNow:
    def test_ends_with_Z(self):
        assert _utc_now().endswith("Z")

    def test_is_iso_format(self):
        from datetime import datetime
        datetime.fromisoformat(_utc_now().replace("Z", "+00:00"))


# ===================================================================
# 2. Strategy filter pass
# ===================================================================

class TestStrategyFilterPass:

    def test_passes_when_all_ok(self):
        feature = _base_feature()
        strategy = _base_strategy()
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is True
        assert blockers == []

    def test_blocks_regime_not_allowed(self):
        # P-OP8: For PO venue, only "unknown" and "dislocated" are blocked.
        # Test the PO-specific block:
        feature = _base_feature(market_regime="dislocated")
        strategy = _base_strategy()
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is False
        assert "regime_not_allowed" in blockers

    def test_trend_strong_always_passes_regime(self):
        """trend_strong bypasses regime filter."""
        feature = _base_feature(market_regime="trend_strong")
        strategy = _base_strategy(
            filters={"market_regime_allowed": ["range"], "spread_pct_max": None, "volatility_min_atr_pct": None}
        )
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is True

    def test_blocks_spread_too_wide(self):
        feature = _base_feature(spread_pct=0.50)
        strategy = _base_strategy()
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is False
        assert "spread_too_wide" in blockers

    def test_blocks_volatility_too_low(self):
        feature = _base_feature(volatility_proxy_pct=0.001)
        strategy = _base_strategy()
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is False
        assert "volatility_too_low" in blockers

    def test_no_filters_passes(self):
        feature = _base_feature()
        strategy = _base_strategy(filters={})
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is True

    def test_multiple_blockers(self):
        # P-OP8: Use "dislocated" regime to trigger regime blocker for PO venue
        feature = _base_feature(spread_pct=1.0, volatility_proxy_pct=0.0, market_regime="dislocated")
        strategy = _base_strategy()
        ok, blockers = _strategy_filter_pass(feature, strategy)
        assert ok is False
        assert len(blockers) >= 2


# ===================================================================
# 3. Indicator support
# ===================================================================

class TestIndicatorSupport:

    def test_no_required_indicators_passes(self):
        ok, blockers, reasons = _indicator_support(_base_feature(), _base_strategy(core_indicators=[]))
        assert ok is True
        assert blockers == []

    def test_non_po_venue_always_passes(self):
        feature = _base_feature(venue="ibkr")
        strategy = _base_strategy(core_indicators=["RSI"])
        ok, blockers, reasons = _indicator_support(feature, strategy)
        assert ok is True

    def test_po_with_indicator_candidates_passes(self):
        feature = _base_feature(indicator_candidates=["RSI", "MACD"])
        strategy = _base_strategy(core_indicators=["RSI"])
        ok, blockers, reasons = _indicator_support(feature, strategy)
        assert ok is True
        assert "indicator_controls_detected" in reasons

    def test_po_without_indicator_candidates_blocks(self):
        feature = _base_feature(indicator_candidates=[])
        strategy = _base_strategy(core_indicators=["RSI"])
        ok, blockers, reasons = _indicator_support(feature, strategy)
        assert ok is False
        assert "indicator_controls_unavailable" in blockers


# ===================================================================
# 4. Signal generators
# ===================================================================

class TestTrendSignal:

    def test_positive_move_call(self):
        sig = _trend_signal(_base_feature(last_vs_close_pct=0.5))
        assert sig["direction"] == "call"
        assert sig["signal_valid"] is True

    def test_negative_move_put(self):
        sig = _trend_signal(_base_feature(last_vs_close_pct=-0.5, bid_ask_imbalance=0.0))
        assert sig["direction"] == "put"

    def test_small_move_invalid(self):
        sig = _trend_signal(_base_feature(last_vs_close_pct=0.05, bid_ask_imbalance=-0.2))
        assert sig["signal_valid"] is False

    def test_confidence_range(self):
        sig = _trend_signal(_base_feature())
        assert 0.0 <= sig["confidence"] <= 1.0

    def test_signal_score_range(self):
        sig = _trend_signal(_base_feature())
        assert -1.0 <= sig["signal_score"] <= 1.0


class TestBreakoutSignal:

    def test_po_valid_breakout(self):
        sig = _breakout_signal(_base_feature(
            last_vs_close_pct=0.15, payout_pct=85,
            recent_micro_move_pct=0.06, volatility_proxy_pct=0.15,
            # P-OP9: Provide indicator values for confluence check
            indicator_confluence=3, rsi_14=30.0, bb_pct_b=0.1,
            stoch_k=25.0, stoch_d=30.0, macd_histogram=0.001,
        ))
        assert sig["direction"] in ("call", "put")
        assert sig["signal_valid"] is True

    def test_po_low_payout_invalid(self):
        sig = _breakout_signal(_base_feature(payout_pct=50))
        # payout < 70 → invalid for PO breakout
        assert sig["signal_valid"] is False

    def test_non_po_venue(self):
        sig = _breakout_signal(_base_feature(
            venue="ibkr", asset_class="equity",
            last_vs_close_pct=0.5, spread_pct=0.10, liquidity_score=0.9,
        ))
        assert sig["signal_valid"] is True
        assert sig["confidence"] > 0.0

    def test_non_po_low_move_invalid(self):
        sig = _breakout_signal(_base_feature(
            venue="ibkr", asset_class="equity",
            last_vs_close_pct=0.1, spread_pct=0.50, liquidity_score=0.3,
        ))
        assert sig["signal_valid"] is False


class TestMeanReversionSignal:

    def test_no_price_invalid(self):
        sig = _mean_reversion_signal(_base_feature(price_available=False))
        assert sig["signal_valid"] is False
        assert "missing_price_context" in sig["reasons"]

    def test_valid_reversion(self):
        sig = _mean_reversion_signal(_base_feature(
            price_available=True, price_zscore=1.5,
            payout_pct=80, volatility_proxy_pct=0.08,
            recent_micro_move_pct=0.05, last_vs_close_pct=0.1,
            # P-OP9: Provide extreme indicator values for reversion signals
            rsi_14=78.0, bb_pct_b=1.15, stoch_k=88.0, stoch_d=85.0,
            macd_histogram=-0.001, indicator_confluence=-3,
            # P-OP32f: mean reversion is now blocked in trend_strong regime,
            # so use a range regime for this reversion-validity test.
            market_regime="range",
        ))
        assert sig["signal_valid"] is True
        # indicators are overbought → expect sell/put direction
        assert sig["direction"] == "put"

    def test_negative_zscore_call(self):
        sig = _mean_reversion_signal(_base_feature(
            price_available=True, price_zscore=-1.5,
            payout_pct=80, volatility_proxy_pct=0.08,
            # P-OP9: Provide oversold indicator values for bullish reversion
            rsi_14=22.0, bb_pct_b=-0.15, stoch_k=12.0, stoch_d=15.0,
            macd_histogram=0.001, indicator_confluence=3,
        ))
        assert sig["direction"] == "call"

    def test_confidence_range(self):
        sig = _mean_reversion_signal(_base_feature(price_available=True, payout_pct=90))
        assert 0.0 <= sig["confidence"] <= 1.0


# ===================================================================
# 5. Full evaluation
# ===================================================================

class TestEvaluateStrategyFeature:

    def test_valid_signal_structure(self):
        result = _evaluate_strategy_feature(_base_strategy(), _base_feature())
        required_keys = {
            "strategy_id", "venue", "symbol", "direction",
            "signal_valid", "execution_ready", "confidence",
            "signal_score", "entry_price", "blockers", "reasons",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_symbol_not_in_universe_blocked(self):
        result = _evaluate_strategy_feature(
            _base_strategy(universe=["GBPUSD"]),
            _base_feature(symbol="EURUSD_otc"),
        )
        assert "symbol_not_in_universe" in result["blockers"]
        assert result["signal_valid"] is False

    def test_asset_class_blocked(self):
        result = _evaluate_strategy_feature(
            _base_strategy(asset_classes=["equity"]),
            _base_feature(asset_class="otc_binary"),
        )
        assert "asset_class_not_supported" in result["blockers"]

    def test_stale_data_blocked(self):
        """P5-09: stale data should produce a blocker."""
        result = _evaluate_strategy_feature(
            _base_strategy(),
            _base_feature(is_stale=True),
        )
        assert "data_too_stale" in result["blockers"]
        assert result["signal_valid"] is False

    def test_stream_symbol_mismatch_blocked(self):
        result = _evaluate_strategy_feature(
            _base_strategy(),
            _base_feature(stream_symbol_match=False),
        )
        assert "stream_symbol_mismatch" in result["blockers"]

    def test_price_unavailable_blocked(self):
        result = _evaluate_strategy_feature(
            _base_strategy(),
            _base_feature(price_available=False),
        )
        assert "price_unavailable" in result["blockers"]

    def test_confidence_below_threshold_blocked(self):
        """P3-06: per-strategy confidence threshold."""
        result = _evaluate_strategy_feature(
            _base_strategy(confidence_threshold=0.99),
            _base_feature(),
        )
        # Signal may be valid but confidence < 0.99
        if result["signal_valid"] is False:
            # blockers already prevent signal
            pass
        else:
            assert result["execution_ready"] is False
            assert "confidence_below_threshold" in result["blockers"]

    def test_execution_ready_when_all_pass(self):
        """With good data and low threshold, execution_ready should be True."""
        result = _evaluate_strategy_feature(
            _base_strategy(
                family="breakout",
                confidence_threshold=0.30,
                core_indicators=[],
            ),
            _base_feature(
                last_vs_close_pct=0.15, payout_pct=85,
                recent_micro_move_pct=0.06, volatility_proxy_pct=0.15,
                # P-OP9: Provide indicator confluence for valid breakout signal
                indicator_confluence=3, rsi_14=30.0, bb_pct_b=0.1,
                stoch_k=25.0, stoch_d=30.0, macd_histogram=0.001,
            ),
        )
        assert result["execution_ready"] is True
        assert result["signal_valid"] is True
        assert result["confidence"] >= 0.30

    def test_trend_family_dispatch(self):
        result = _evaluate_strategy_feature(
            _base_strategy(family="trend_following"),
            _base_feature(),
        )
        assert "trend_move_detected" in result["reasons"]

    def test_mean_reversion_family_dispatch(self):
        result = _evaluate_strategy_feature(
            _base_strategy(family="mean_reversion"),
            _base_feature(price_available=True, price_zscore=1.5, payout_pct=80, volatility_proxy_pct=0.08),
        )
        assert "range_reversion_setup" in result["reasons"]

    def test_unsupported_family(self):
        result = _evaluate_strategy_feature(
            _base_strategy(family="unknown_family"),
            _base_feature(),
        )
        assert "unsupported_family" in result["reasons"]
        assert result["signal_valid"] is False

    def test_entry_price_uses_last(self):
        result = _evaluate_strategy_feature(
            _base_strategy(), _base_feature(last=1.2345, mid=1.2340),
        )
        assert result["entry_price"] == 1.2345

    def test_entry_price_falls_back_to_mid(self):
        result = _evaluate_strategy_feature(
            _base_strategy(), _base_feature(last=None, mid=1.2340),
        )
        assert result["entry_price"] == 1.2340


# ===================================================================
# 6. Snapshot builder
# ===================================================================

class TestBuildStrategySignalSnapshot:

    def test_structure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("brain_v9.trading.signal_engine.ENGINE_PATH", tmp_path)
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH",
            tmp_path / "snapshot.json",
        )
        strategies = [_base_strategy()]
        features = {"items": [_base_feature()]}
        result = build_strategy_signal_snapshot(strategies, feature_snapshot=features)
        assert result["schema_version"] == "strategy_signal_snapshot_v1"
        assert result["strategies_count"] == 1
        assert "items" in result
        assert "by_strategy" in result

    def test_empty_features(self, tmp_path, monkeypatch):
        monkeypatch.setattr("brain_v9.trading.signal_engine.ENGINE_PATH", tmp_path)
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH",
            tmp_path / "snapshot.json",
        )
        # Provide empty feature snapshot AND mock build_market_feature_snapshot
        # to avoid real filesystem access
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.build_market_feature_snapshot",
            lambda: {"items": []},
        )
        result = build_strategy_signal_snapshot(
            [_base_strategy()],
            feature_snapshot={"items": []},
        )
        assert result["signals_count"] == 0

    def test_venue_filtering(self, tmp_path, monkeypatch):
        """Strategies only see features from their own venue."""
        monkeypatch.setattr("brain_v9.trading.signal_engine.ENGINE_PATH", tmp_path)
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH",
            tmp_path / "snapshot.json",
        )
        strategies = [_base_strategy(venue="pocket_option")]
        features = {
            "items": [
                _base_feature(venue="pocket_option"),
                _base_feature(venue="ibkr", symbol="AAPL", asset_class="equity"),
            ]
        }
        result = build_strategy_signal_snapshot(strategies, feature_snapshot=features)
        # Only PO feature should produce signals
        assert result["signals_count"] == 1

    def test_by_strategy_best_signal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("brain_v9.trading.signal_engine.ENGINE_PATH", tmp_path)
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH",
            tmp_path / "snapshot.json",
        )
        strategies = [_base_strategy()]
        features = {"items": [_base_feature()]}
        result = build_strategy_signal_snapshot(strategies, feature_snapshot=features)
        bs = result["by_strategy"][0]
        assert bs["strategy_id"] == "test_strat_01"
        assert bs["best_signal"] is not None

    def test_writes_to_disk(self, tmp_path, monkeypatch):
        snap_path = tmp_path / "snapshot.json"
        monkeypatch.setattr("brain_v9.trading.signal_engine.ENGINE_PATH", tmp_path)
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH", snap_path,
        )
        build_strategy_signal_snapshot([_base_strategy()], feature_snapshot={"items": [_base_feature()]})
        assert snap_path.exists()


# ===================================================================
# 7. Read snapshot
# ===================================================================

class TestReadSnapshot:

    def test_missing_file_returns_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.SIGNAL_SNAPSHOT_PATH",
            tmp_path / "does_not_exist.json",
        )
        result = read_strategy_signal_snapshot()
        assert result["items"] == []
        assert result["by_strategy"] == []
