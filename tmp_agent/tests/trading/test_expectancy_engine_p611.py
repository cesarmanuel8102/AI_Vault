"""
P6-11 — Tests for trading/expectancy_engine.py

Covers all pure-math scoring functions, metric builders, decorators,
and the top-level build_expectancy_snapshot integration with mocked I/O.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from brain_v9.trading.expectancy_engine import (
    _safe_float,
    _safe_int,
    _round,
    _clamp,
    _recent_stability,
    _profit_factor,
    _sample_quality,
    _drawdown_penalty,
    _expectancy_score,
    _win_rate_score,
    _profit_factor_score,
    _consistency_score,
    _base_metrics,
    _decorate_strategy_item,
    _decorate_symbol_item,
    _decorate_context_item,
    _append_ndjson,
    build_expectancy_snapshot,
    read_expectancy_snapshot,
    read_expectancy_by_strategy,
    read_expectancy_by_strategy_venue,
    read_expectancy_by_strategy_symbol,
    read_expectancy_by_strategy_context,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_int_coerced(self):
        assert _safe_float(5) == 5.0

    def test_string_number(self):
        assert _safe_float("2.5") == 2.5

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_none_custom_default(self):
        assert _safe_float(None, 7.7) == 7.7

    def test_garbage_returns_default(self):
        assert _safe_float("xyz") == 0.0

    def test_empty_string_returns_default(self):
        assert _safe_float("") == 0.0


class TestSafeInt:
    def test_normal_int(self):
        assert _safe_int(42) == 42

    def test_float_truncated(self):
        assert _safe_int(3.9) == 3

    def test_string_number(self):
        assert _safe_int("10") == 10

    def test_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_none_custom_default(self):
        assert _safe_int(None, -1) == -1

    def test_garbage_returns_default(self):
        assert _safe_int("abc") == 0


class TestRound:
    def test_basic(self):
        assert _round(1.23456789) == 1.2346

    def test_custom_digits(self):
        assert _round(1.23456789, 2) == 1.23

    def test_none_input(self):
        # _safe_float inside _round handles None → 0.0
        assert _round(None) == 0.0


class TestClamp:
    def test_within(self):
        assert _clamp(0.5, 0.0, 1.0) == 0.5

    def test_below(self):
        assert _clamp(-5.0, 0.0, 1.0) == 0.0

    def test_above(self):
        assert _clamp(10.0, 0.0, 1.0) == 1.0

    def test_at_boundaries(self):
        assert _clamp(0.0, 0.0, 1.0) == 0.0
        assert _clamp(1.0, 0.0, 1.0) == 1.0

    def test_negative_range(self):
        assert _clamp(0.0, -1.0, -0.5) == -0.5


# ── Scoring Functions ────────────────────────────────────────────────────────


class TestRecentStability:
    def test_empty_returns_zero(self):
        assert _recent_stability([]) == 0.0

    def test_single_nonzero_profit(self):
        assert _recent_stability([{"profit": 1.0}]) == 0.5

    def test_single_zero_profit(self):
        assert _recent_stability([{"profit": 0.0}]) == 0.25

    def test_uniform_profits_high_stability(self):
        # All identical magnitudes → variance=0 → coeff=0 → stability=1.0
        items = [{"profit": 1.0}] * 5
        assert _recent_stability(items) == 1.0

    def test_high_variance_low_stability(self):
        # Very different magnitudes → high coeff → low stability
        items = [{"profit": 0.01}, {"profit": 100.0}, {"profit": 0.01}, {"profit": 100.0}, {"profit": 0.01}]
        result = _recent_stability(items)
        assert 0.0 <= result <= 0.5  # high variance → low stability

    def test_takes_last_5(self):
        # More than 5 items — only last 5 used
        items = [{"profit": 999.0}] * 10 + [{"profit": 1.0}] * 5
        result = _recent_stability(items)
        assert result == 1.0  # last 5 all identical

    def test_missing_profit_defaults_to_zero(self):
        items = [{}] * 3
        result = _recent_stability(items)
        # All zeros → mean_abs=0 → returns 1.0
        assert result == 1.0


class TestProfitFactor:
    def test_normal(self):
        assert _profit_factor(100.0, 50.0) == 2.0

    def test_zero_loss_positive_profit(self):
        assert _profit_factor(100.0, 0.0) == 99.0

    def test_zero_loss_zero_profit(self):
        assert _profit_factor(0.0, 0.0) == 0.0

    def test_loss_greater_than_profit(self):
        result = _profit_factor(30.0, 60.0)
        assert result == 0.5

    def test_negative_loss_value_uses_abs(self):
        # gross_loss should be positive, but abs() handles negative
        assert _profit_factor(100.0, -50.0) == 2.0


class TestSampleQuality:
    def test_at_target(self):
        assert _sample_quality(100, 100) == 1.0

    def test_half_target(self):
        assert _sample_quality(50, 100) == 0.5

    def test_over_target_capped(self):
        assert _sample_quality(200, 100) == 1.0

    def test_zero_entries(self):
        assert _sample_quality(0, 100) == 0.0

    def test_default_target_is_100(self):
        assert _sample_quality(50) == 0.5

    def test_min_target_1_if_zero(self):
        # max(0, 1.0) = 1.0 → 50/1.0 = 50 → clamped to 1.0
        assert _sample_quality(50, 0) == 1.0


class TestDrawdownPenalty:
    def test_no_turnover(self):
        card: Dict[str, Any] = {"gross_profit": 0.0, "gross_loss": 0.0, "largest_loss": 0.0}
        assert _drawdown_penalty(card) == 0.0

    def test_small_loss_relative_to_turnover(self):
        card: Dict[str, Any] = {"gross_profit": 100.0, "gross_loss": -50.0, "largest_loss": -5.0}
        # turnover = 100 + 50 = 150, largest_loss = 5
        # proxy_drawdown_pct = 5/150 ≈ 0.0333
        # penalty = 0.0333 / 0.20 ≈ 0.1667
        result = _drawdown_penalty(card)
        assert 0.1 < result < 0.2

    def test_large_loss_high_penalty(self):
        card: Dict[str, Any] = {"gross_profit": 50.0, "gross_loss": -50.0, "largest_loss": -40.0}
        # turnover = 50 + 50 = 100, largest_loss = 40
        # proxy = 40/100 = 0.40
        # penalty = 0.40 / 0.20 = 2.0 → clamped to 1.0
        assert _drawdown_penalty(card) == 1.0

    def test_missing_fields_default_zero(self):
        assert _drawdown_penalty({}) == 0.0


class TestExpectancyScore:
    def test_at_target(self):
        assert _expectancy_score(0.10) == 1.0

    def test_half_target(self):
        assert _expectancy_score(0.05) == 0.5

    def test_negative_expectancy(self):
        result = _expectancy_score(-0.10)
        assert result == -1.0

    def test_zero(self):
        assert _expectancy_score(0.0) == 0.0

    def test_above_target_capped(self):
        assert _expectancy_score(0.50) == 1.0


class TestWinRateScore:
    def test_fifty_percent(self):
        assert _win_rate_score(0.5) == 0.0

    def test_seventy_percent(self):
        assert _win_rate_score(0.7) == 1.0

    def test_thirty_percent(self):
        assert _win_rate_score(0.3) == -1.0

    def test_above_seventy_capped(self):
        assert _win_rate_score(0.9) == 1.0


class TestProfitFactorScore:
    def test_at_one(self):
        assert _profit_factor_score(1.0) == 0.0

    def test_at_two(self):
        assert _profit_factor_score(2.0) == 1.0

    def test_below_one(self):
        result = _profit_factor_score(0.5)
        assert result == -0.5

    def test_above_two_capped(self):
        assert _profit_factor_score(5.0) == 1.0


class TestConsistencyScore:
    def test_all_perfect(self):
        result = _consistency_score(1.0, 2.0, 1.0, 0.10)
        # sq=1.0*0.35=0.35, pf=min(2.0/2,1)=1.0*0.25=0.25, rs=1.0*0.20=0.20, exp_pos=1.0*0.20=0.20
        # total = 1.0
        assert result == 1.0

    def test_all_zero(self):
        result = _consistency_score(0.0, 0.0, 0.0, 0.0)
        # sq=0, pf=0, rs=0, exp_pos=0
        assert result == 0.0

    def test_negative_expectancy_zero_bonus(self):
        result = _consistency_score(1.0, 2.0, 1.0, -0.05)
        # sq=0.35, pf=0.25, rs=0.20, exp_pos=0
        assert result == 0.8

    def test_high_pf_capped(self):
        result = _consistency_score(0.0, 10.0, 0.0, 0.0)
        # pf_norm = min(10/2, 1) = 1.0 → 0.25
        assert result == 0.25


# ── Base Metrics ─────────────────────────────────────────────────────────────


class TestBaseMetrics:
    @pytest.fixture
    def minimal_card(self) -> Dict[str, Any]:
        return {
            "wins": 6,
            "losses": 4,
            "draws": 0,
            "entries_taken": 10,
            "entries_resolved": 10,
            "gross_profit": 6.0,
            "gross_loss": -4.0,
            "net_pnl": 2.0,
            "avg_win": 1.0,
            "avg_loss": -1.0,
            "win_rate": 0.6,
            "expectancy": 0.2,
            "largest_loss": -2.0,
            "largest_win": 1.5,
            "recent_5_outcomes": [
                {"profit": 1.0},
                {"profit": -1.0},
                {"profit": 1.0},
                {"profit": 1.0},
                {"profit": -1.0},
            ],
        }

    def test_returns_all_keys(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        expected_keys = {
            "entries_taken", "entries_resolved", "wins", "losses", "breakeven",
            "gross_profit", "gross_loss", "net_pnl", "avg_win", "avg_loss",
            "win_rate", "loss_rate", "expectancy", "profit_factor",
            "sample_quality", "expectancy_score", "win_rate_score",
            "profit_factor_score", "drawdown_penalty", "recent_stability",
            "consistency_score", "largest_loss", "largest_win",
            "recent_5_outcomes", "last_trade_utc", "promotion_state",
            "governance_state", "freeze_recommended", "promote_candidate",
            "watch_recommended", "success_criteria",
        }
        assert set(metrics.keys()) == expected_keys

    def test_win_loss_counts(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["wins"] == 6
        assert metrics["losses"] == 4
        assert metrics["breakeven"] == 0

    def test_loss_rate_calculated(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["loss_rate"] == 0.4

    def test_loss_rate_zero_when_no_resolved(self):
        card: Dict[str, Any] = {"entries_resolved": 0, "losses": 0}
        metrics = _base_metrics(card)
        assert metrics["loss_rate"] == 0.0

    def test_profit_factor_calculated(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["profit_factor"] == 1.5  # 6.0 / 4.0

    def test_gross_loss_is_negative_in_output(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["gross_loss"] <= 0

    def test_largest_loss_is_absolute(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["largest_loss"] == 2.0  # abs(-2.0)

    def test_empty_card_uses_defaults(self):
        metrics = _base_metrics({})
        assert metrics["wins"] == 0
        assert metrics["losses"] == 0
        assert metrics["expectancy"] == 0.0
        assert metrics["sample_quality"] == 0.0

    def test_sample_quality_uses_min_sample_target(self, minimal_card):
        metrics_30 = _base_metrics(minimal_card, min_sample_target=30)
        metrics_100 = _base_metrics(minimal_card, min_sample_target=100)
        # 10 resolved: 10/30 vs 10/100
        assert metrics_30["sample_quality"] > metrics_100["sample_quality"]

    def test_boolean_fields(self, minimal_card):
        metrics = _base_metrics(minimal_card)
        assert metrics["freeze_recommended"] is False
        assert metrics["promote_candidate"] is False
        assert metrics["watch_recommended"] is False

    def test_boolean_fields_when_true(self):
        card: Dict[str, Any] = {
            "freeze_recommended": True,
            "promote_candidate": True,
            "watch_recommended": True,
        }
        metrics = _base_metrics(card)
        assert metrics["freeze_recommended"] is True
        assert metrics["promote_candidate"] is True
        assert metrics["watch_recommended"] is True


# ── Decorators ───────────────────────────────────────────────────────────────


class TestDecorateStrategyItem:
    def test_includes_strategy_id(self):
        card: Dict[str, Any] = {"venue": "ibkr", "family": "trend"}
        item = _decorate_strategy_item("strat_A", card)
        assert item["strategy_id"] == "strat_A"
        assert item["venue"] == "ibkr"
        assert item["family"] == "trend"

    def test_includes_base_metrics(self):
        card: Dict[str, Any] = {"wins": 5, "losses": 3, "entries_resolved": 8}
        item = _decorate_strategy_item("strat_B", card)
        assert "expectancy" in item
        assert "profit_factor" in item
        assert "consistency_score" in item


class TestDecorateSymbolItem:
    def test_includes_symbol_fields(self):
        card: Dict[str, Any] = {
            "strategy_id": "strat_X",
            "venue": "po",
            "family": "breakout",
            "symbol": "EURUSD",
            "scope": "forex",
        }
        item = _decorate_symbol_item("strat_X::po::EURUSD", card)
        assert item["key"] == "strat_X::po::EURUSD"
        assert item["symbol"] == "EURUSD"
        assert item["scope"] == "forex"
        assert "expectancy" in item


class TestDecorateContextItem:
    def test_includes_context_fields(self):
        card: Dict[str, Any] = {
            "strategy_id": "strat_Y",
            "venue": "ibkr",
            "family": "mean_reversion",
            "symbol": "SPY",
            "scope": "us_equity",
            "timeframe": "5m",
            "setup_variant": "oversold_bounce",
        }
        item = _decorate_context_item("key123", card)
        assert item["timeframe"] == "5m"
        assert item["setup_variant"] == "oversold_bounce"
        assert item["symbol"] == "SPY"


# ── NDJSON helper ────────────────────────────────────────────────────────────


class TestAppendNdjson:
    def test_creates_file_and_appends(self, tmp_path):
        path = tmp_path / "sub" / "report.ndjson"
        _append_ndjson(path, {"type": "test", "value": 1})
        _append_ndjson(path, {"type": "test", "value": 2})
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["value"] == 1
        assert json.loads(lines[1])["value"] == 2


# ── Snapshot Integration ─────────────────────────────────────────────────────


class TestBuildExpectancySnapshot:
    @pytest.fixture
    def mock_scorecards(self):
        return {
            "scorecards": {
                "trend_follow": {
                    "venue": "ibkr",
                    "family": "trend",
                    "wins": 7,
                    "losses": 3,
                    "draws": 0,
                    "entries_taken": 10,
                    "entries_resolved": 10,
                    "gross_profit": 7.0,
                    "gross_loss": -3.0,
                    "net_pnl": 4.0,
                    "avg_win": 1.0,
                    "avg_loss": -1.0,
                    "win_rate": 0.7,
                    "expectancy": 0.4,
                    "largest_loss": -1.5,
                    "largest_win": 2.0,
                    "recent_5_outcomes": [{"profit": 1.0}] * 5,
                    "strategy_id": "trend_follow",
                },
                "mean_rev": {
                    "venue": "po",
                    "family": "mean_reversion",
                    "wins": 4,
                    "losses": 6,
                    "draws": 0,
                    "entries_taken": 10,
                    "entries_resolved": 10,
                    "gross_profit": 4.0,
                    "gross_loss": -6.0,
                    "net_pnl": -2.0,
                    "avg_win": 1.0,
                    "avg_loss": -1.0,
                    "win_rate": 0.4,
                    "expectancy": -0.2,
                    "largest_loss": -3.0,
                    "largest_win": 1.0,
                    "recent_5_outcomes": [{"profit": -1.0}] * 5,
                    "strategy_id": "mean_rev",
                },
            },
            "symbol_scorecards": {},
            "context_scorecards": {},
        }

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_returns_snapshot_structure(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        snapshot = build_expectancy_snapshot()
        assert snapshot["schema_version"] == "expectancy_snapshot_v1"
        assert "generated_utc" in snapshot
        assert "summary" in snapshot
        assert "by_strategy" in snapshot
        assert "by_strategy_venue" in snapshot
        assert "by_strategy_symbol" in snapshot
        assert "by_strategy_context" in snapshot

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_strategies_sorted_by_expectancy(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        snapshot = build_expectancy_snapshot()
        items = snapshot["by_strategy"]["items"]
        assert len(items) == 2
        # trend_follow has higher expectancy (0.4) than mean_rev (-0.2)
        assert items[0]["strategy_id"] == "trend_follow"
        assert items[1]["strategy_id"] == "mean_rev"

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_summary_counts(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        snapshot = build_expectancy_snapshot()
        summary = snapshot["summary"]
        assert summary["strategies_count"] == 2
        assert summary["positive_expectancy_strategies_count"] == 1

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_top_strategy_is_best(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        snapshot = build_expectancy_snapshot()
        top = snapshot["summary"]["top_strategy"]
        assert top is not None
        assert top["strategy_id"] == "trend_follow"

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_writes_5_files(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        build_expectancy_snapshot()
        assert mock_write.call_count == 5  # 4 slice files + snapshot
        assert mock_ndjson.call_count == 1

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_empty_scorecards(self, mock_read, mock_ndjson, mock_write):
        mock_read.return_value = {"scorecards": {}, "symbol_scorecards": {}, "context_scorecards": {}}
        snapshot = build_expectancy_snapshot()
        assert snapshot["summary"]["strategies_count"] == 0
        assert snapshot["summary"]["top_strategy"] is None

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_min_sample_target_passed_through(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        snapshot = build_expectancy_snapshot(min_sample_target=50)
        assert snapshot["min_sample_target"] == 50

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_ndjson_report_content(self, mock_read, mock_ndjson, mock_write, mock_scorecards):
        mock_read.return_value = mock_scorecards
        build_expectancy_snapshot()
        ndjson_args = mock_ndjson.call_args[0][1]
        assert ndjson_args["type"] == "expectancy_refresh"
        assert ndjson_args["strategies_count"] == 2
        assert ndjson_args["positive_expectancy_strategies_count"] == 1
        assert ndjson_args["top_strategy_id"] == "trend_follow"

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_with_symbol_scorecards(self, mock_read, mock_ndjson, mock_write):
        mock_read.return_value = {
            "scorecards": {},
            "symbol_scorecards": {
                "trend::ibkr::SPY": {
                    "strategy_id": "trend",
                    "venue": "ibkr",
                    "family": "trend",
                    "symbol": "SPY",
                    "scope": "equity",
                    "wins": 3,
                    "losses": 1,
                    "entries_resolved": 4,
                    "expectancy": 0.5,
                }
            },
            "context_scorecards": {},
        }
        snapshot = build_expectancy_snapshot()
        assert snapshot["by_strategy_symbol"]["count"] == 1
        assert snapshot["by_strategy_symbol"]["items"][0]["symbol"] == "SPY"

    @patch("brain_v9.trading.expectancy_engine.write_json")
    @patch("brain_v9.trading.expectancy_engine._append_ndjson")
    @patch("brain_v9.trading.expectancy_engine.read_scorecards")
    def test_with_context_scorecards(self, mock_read, mock_ndjson, mock_write):
        mock_read.return_value = {
            "scorecards": {},
            "symbol_scorecards": {},
            "context_scorecards": {
                "trend::ibkr::SPY::5m::v1": {
                    "strategy_id": "trend",
                    "venue": "ibkr",
                    "family": "trend",
                    "symbol": "SPY",
                    "scope": "equity",
                    "timeframe": "5m",
                    "setup_variant": "v1",
                    "wins": 2,
                    "losses": 1,
                    "entries_resolved": 3,
                    "expectancy": 0.3,
                }
            },
        }
        snapshot = build_expectancy_snapshot()
        assert snapshot["by_strategy_context"]["count"] == 1
        ctx_item = snapshot["by_strategy_context"]["items"][0]
        assert ctx_item["timeframe"] == "5m"
        assert ctx_item["setup_variant"] == "v1"


# ── Read Functions ───────────────────────────────────────────────────────────


class TestReadExpectancySnapshot:
    @patch("brain_v9.trading.expectancy_engine.build_expectancy_snapshot")
    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_returns_cached_if_exists(self, mock_read, mock_build):
        mock_read.return_value = {"schema_version": "expectancy_snapshot_v1"}
        result = read_expectancy_snapshot()
        assert result["schema_version"] == "expectancy_snapshot_v1"
        mock_build.assert_not_called()

    @patch("brain_v9.trading.expectancy_engine.build_expectancy_snapshot")
    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_builds_if_empty(self, mock_read, mock_build):
        mock_read.return_value = {}
        mock_build.return_value = {"schema_version": "expectancy_snapshot_v1", "fresh": True}
        result = read_expectancy_snapshot()
        assert result["fresh"] is True
        mock_build.assert_called_once()

    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_read_by_strategy_default(self, mock_read):
        mock_read.return_value = {"group_by": "strategy", "count": 0, "items": []}
        result = read_expectancy_by_strategy()
        assert result["group_by"] == "strategy"

    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_read_by_venue_default(self, mock_read):
        mock_read.return_value = {"group_by": "strategy_venue", "count": 0, "items": []}
        result = read_expectancy_by_strategy_venue()
        assert result["group_by"] == "strategy_venue"

    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_read_by_symbol_default(self, mock_read):
        mock_read.return_value = {"group_by": "strategy_venue_symbol", "count": 0, "items": []}
        result = read_expectancy_by_strategy_symbol()
        assert result["group_by"] == "strategy_venue_symbol"

    @patch("brain_v9.trading.expectancy_engine.read_json")
    def test_read_by_context_default(self, mock_read):
        mock_read.return_value = {"group_by": "strategy_venue_symbol_timeframe_setup", "count": 0, "items": []}
        result = read_expectancy_by_strategy_context()
        assert result["group_by"] == "strategy_venue_symbol_timeframe_setup"


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_base_metrics_with_none_values_everywhere(self):
        """Card where every numeric field is None — should not crash."""
        card: Dict[str, Any] = {
            "wins": None,
            "losses": None,
            "draws": None,
            "entries_taken": None,
            "entries_resolved": None,
            "gross_profit": None,
            "gross_loss": None,
            "net_pnl": None,
            "avg_win": None,
            "avg_loss": None,
            "win_rate": None,
            "expectancy": None,
            "largest_loss": None,
            "largest_win": None,
            "recent_5_outcomes": None,
        }
        metrics = _base_metrics(card)
        assert metrics["wins"] == 0
        assert metrics["expectancy"] == 0.0
        assert metrics["recent_5_outcomes"] == []

    def test_drawdown_penalty_custom_max(self):
        card: Dict[str, Any] = {"gross_profit": 100.0, "gross_loss": -100.0, "largest_loss": -10.0}
        # turnover = 200, largest = 10, proxy = 0.05
        # default max = 0.20 → 0.05/0.20 = 0.25
        result_default = _drawdown_penalty(card)
        # custom max = 0.05 → 0.05/0.05 = 1.0
        result_strict = _drawdown_penalty(card, max_allowed_drawdown_pct=0.05)
        assert result_strict > result_default

    def test_consistency_score_clamped_at_one(self):
        # Even with extreme values, should not exceed 1.0
        result = _consistency_score(1.0, 100.0, 1.0, 1.0)
        assert result <= 1.0

    def test_recent_stability_all_negative_profits(self):
        items = [{"profit": -1.0}] * 5
        result = _recent_stability(items)
        # All same magnitude → high stability
        assert result == 1.0
