"""
Tests for brain_v9.trading.paper_execution — Sprint 2 (P3-02), updated 9X-01.

Covers:
  - _build_deferred_entry: ALL trades produce pending_resolution
  - resolve_pending_paper_trades: forward-looking resolver
  - execute_signal_paper_trade: ALL venues use deferred_forward_v1
  - execute_paper_trade: agent tool wrapper
  - No circular alignment: old _alignment_outcome removed
  - No _history_resolution: removed in 9X-01
  - Trade deduplication guard (9X-02)
"""
import json
from unittest.mock import patch, MagicMock
import pytest

import brain_v9.config as _cfg
from brain_v9.trading.paper_execution import (
    _build_deferred_entry,
    _read_ledger,
    _update_platform_metrics,
    _update_strategy_scorecards,
    _write_ledger,
    _VENUE_TO_PLATFORM,
    execute_paper_trade,
    execute_signal_paper_trade,
    persist_trade_execution_metadata,
    resolve_pending_paper_trades,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_strategy(venue="pocket_option", family="trend_following", strategy_id="test_strat"):
    return {"strategy_id": strategy_id, "venue": venue, "family": family}


def _make_signal(direction="call", confidence=0.7, symbol="EURUSD_otc",
                 execution_ready=True, feature_key="po::EURUSD_otc::1m"):
    return {
        "direction": direction,
        "confidence": confidence,
        "symbol": symbol,
        "execution_ready": execution_ready,
        "signal_score": 0.5,
        "timeframe": "1m",
        "setup_variant": "base",
        "asset_class": "otc_binary",
        "reasons": ["test_reason"],
        "blockers": [],
        "feature_key": feature_key,
    }


def _make_feature(last=1.08500, payout_pct=82.0, price_available=True):
    return {
        "last": last,
        "mid": last,
        "price_available": price_available,
        "last_vs_close_pct": 0.15,
        "bid_ask_imbalance": 0.1,
        "payout_pct": payout_pct,
    }


def _make_lane(platform="po_paper"):
    return {"platform": platform}


def _seed_pending_entry(
    direction="call", entry_price=1.08500, feature_key="po::EURUSD_otc::1m",
    confidence=0.7, payout_pct=82.0, family="trend_following",
):
    """Write a single pending entry to the ledger."""
    entry = {
        "timestamp": "2026-03-25T12:00:00Z",
        "symbol": "EURUSD_otc",
        "direction": direction,
        "result": "pending_resolution",
        "profit": 0.0,
        "entry_price": entry_price,
        "entry_payout_pct": payout_pct,
        "paper_shadow": True,
        "paper_only": True,
        "strategy_id": "test_strat",
        "venue": "pocket_option",
        "family": family,
        "timeframe": "1m",
        "setup_variant": "base",
        "asset_class": "otc_binary",
        "confidence": confidence,
        "signal_score": 0.5,
        "resolution_mode": "deferred_forward_v1",
        "signal_reasons": [],
        "signal_blockers": [],
        "feature_key": feature_key,
        "resolved": False,
        "executor_platform": "po_paper",
    }
    ledger = {
        "schema_version": "signal_paper_execution_ledger_v1",
        "updated_utc": "2026-03-25T12:00:00Z",
        "entries": [entry],
    }
    _write_ledger(ledger)
    return entry


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _build_deferred_entry
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildDeferredEntry:

    def test_returns_pending_resolution(self):
        entry = _build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        assert entry["result"] == "pending_resolution"
        assert entry["resolved"] is False

    def test_records_entry_price(self):
        entry = _build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(last=1.23456),
        )
        assert entry["entry_price"] == 1.23456

    def test_records_payout_pct(self):
        entry = _build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(payout_pct=85.0),
        )
        assert entry["entry_payout_pct"] == 85.0

    def test_records_strategy_fields(self):
        entry = _build_deferred_entry(
            _make_strategy(venue="pocket_option", family="breakout", strategy_id="s1"),
            _make_signal(direction="put"),
            _make_feature(),
        )
        assert entry["venue"] == "pocket_option"
        assert entry["family"] == "breakout"
        assert entry["strategy_id"] == "s1"
        assert entry["direction"] == "put"

    def test_resolution_mode_is_deferred(self):
        entry = _build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        assert entry["resolution_mode"] == "deferred_forward_v1"

    def test_profit_is_zero_while_pending(self):
        entry = _build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        assert entry["profit"] == 0.0

    def test_has_feature_key(self):
        entry = _build_deferred_entry(
            _make_strategy(),
            _make_signal(feature_key="po::GBPUSD::5m"),
            _make_feature(),
        )
        assert entry["feature_key"] == "po::GBPUSD::5m"

    def test_persist_trade_execution_metadata_updates_matching_ledger_row(self):
        entry = _build_deferred_entry(
            _make_strategy(strategy_id="po_breakout"),
            _make_signal(symbol="AUDNZD_otc", feature_key="po::AUDNZD_otc::1m"),
            _make_feature(last=1.16951, payout_pct=92.0),
        )
        _write_ledger({
            "schema_version": "signal_paper_execution_ledger_v1",
            "updated_utc": entry["timestamp"],
            "entries": [entry],
        })

        enriched_trade = dict(entry)
        enriched_trade["browser_command_status"] = "ui_trade_confirmed"
        enriched_trade["browser_trade_confirmed"] = True
        enriched_trade["browser_trade_id"] = "po_demo_trade_123"
        enriched_trade["browser_command_dispatched"] = True
        enriched_trade["executor_platform"] = "pocket_option_demo_executor"

        assert persist_trade_execution_metadata(enriched_trade) is True

        persisted = _read_ledger()["entries"][0]
        assert persisted["browser_command_status"] == "ui_trade_confirmed"
        assert persisted["browser_trade_confirmed"] is True
        assert persisted["browser_trade_id"] == "po_demo_trade_123"
        assert persisted["browser_command_dispatched"] is True
        assert persisted["executor_platform"] == "pocket_option_demo_executor"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_pending_paper_trades
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolvePendingTrades:

    @pytest.fixture(autouse=True)
    def _disable_timeout(self, monkeypatch):
        """P5-10 added timeout expiry. Old tests need it disabled so they
        exercise the price-based resolution path, not the timeout path."""
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 999_999)

    def test_call_wins_when_price_rises(self):
        _seed_pending_entry(direction="call", entry_price=1.00000)
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.00100, "mid": 1.00100},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 1
        assert summary["remaining"] == 0

        ledger = _read_ledger()
        entry = ledger["entries"][0]
        assert entry["result"] == "win"
        assert entry["resolved"] is True
        assert entry["profit"] > 0
        assert entry["exit_price"] == pytest.approx(1.001, abs=0.0001)

    def test_call_loses_when_price_drops(self):
        _seed_pending_entry(direction="call", entry_price=1.00000)
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 0.99800, "mid": 0.99800},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 1

        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "loss"
        assert entry["profit"] < 0

    def test_put_wins_when_price_drops(self):
        _seed_pending_entry(direction="put", entry_price=1.00000)
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 0.99800, "mid": 0.99800},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "win"
        assert entry["profit"] > 0

    def test_put_loses_when_price_rises(self):
        _seed_pending_entry(direction="put", entry_price=1.00000)
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.00200, "mid": 1.00200},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "loss"

    def test_skips_when_price_change_too_small(self):
        # P-OP29: Use a RECENT timestamp so the trade is within its holding
        # period (not yet at binary-expiry).  The 0.05% threshold only applies
        # BEFORE the holding duration; after that, binary expiry resolves it.
        from datetime import datetime, timezone
        recent_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = _seed_pending_entry(direction="call", entry_price=1.00000)
        # Override timestamp to be recent
        ledger = _read_ledger()
        ledger["entries"][0]["timestamp"] = recent_ts
        ledger["entries"][0]["duration_seconds"] = 300
        _write_ledger(ledger)

        # 0.005% change — below the 0.05% threshold, and trade is < 300s old
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.00005, "mid": 1.00005},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 0
        assert summary["skipped"] == 1
        assert summary["remaining"] == 1

        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "pending_resolution"
        assert entry["resolved"] is False

    def test_binary_expiry_resolves_call_win(self):
        """P-OP29a: After holding duration, resolve by price direction.
        P-OP34: Price change must be >= BINARY_EXPIRY_MIN_RELIABLE_PCT (0.025%)
        for the directional resolver to trust the result as a win."""
        _seed_pending_entry(direction="call", entry_price=1.00000)
        # Seed has old timestamp (2026-03-25), so age >> duration_seconds
        # Set duration_seconds so binary expiry kicks in
        ledger = _read_ledger()
        ledger["entries"][0]["duration_seconds"] = 300
        _write_ledger(ledger)

        # Upward move of 0.05% — above P-OP34 reliable threshold (0.025%)
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.00050, "mid": 1.00050},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 1

        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "win"
        assert entry["resolved"] is True
        assert entry["resolution_mode"] == "binary_expiry"
        assert entry["resolution_tag"] == "directional"
        assert entry["exit_price"] == 1.0005

    def test_binary_expiry_resolves_put_loss(self):
        """P-OP29a: PUT with price going up should be a loss at binary expiry.
        P-OP34: Use a price change above reliable threshold so it resolves directionally."""
        _seed_pending_entry(direction="put", entry_price=1.00000)
        ledger = _read_ledger()
        ledger["entries"][0]["duration_seconds"] = 300
        _write_ledger(ledger)

        # Price UP by 0.05% — above P-OP34 threshold, PUT direction → loss
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.00050},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 1

        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "loss"
        assert entry["resolution_mode"] == "binary_expiry"
        assert entry["resolution_tag"] == "directional"

    def test_skips_when_no_matching_feature(self):
        _seed_pending_entry(feature_key="po::NZDUSD::1m")
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": True,
                 "last": 1.10000},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 0
        assert summary["skipped"] == 1

    def test_skips_when_feature_price_not_available(self):
        _seed_pending_entry()
        feature_snapshot = {
            "items": [
                {"key": "po::EURUSD_otc::1m", "price_available": False,
                 "last": None},
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 0
        assert summary["skipped"] == 1

    def test_does_not_re_resolve_already_resolved(self):
        """Once resolved, a second call should not touch it."""
        _seed_pending_entry(direction="call", entry_price=1.00000)
        feature_up = {"items": [{"key": "po::EURUSD_otc::1m", "price_available": True, "last": 1.00200}]}
        resolve_pending_paper_trades(feature_up)

        # Now pass a feature that shows price dropped — should NOT change result
        feature_down = {"items": [{"key": "po::EURUSD_otc::1m", "price_available": True, "last": 0.99000}]}
        summary = resolve_pending_paper_trades(feature_down)
        assert summary["resolved"] == 0

        entry = _read_ledger()["entries"][0]
        assert entry["result"] == "win"  # unchanged

    def test_empty_ledger_returns_zeros(self):
        _write_ledger({"schema_version": "v1", "updated_utc": None, "entries": []})
        summary = resolve_pending_paper_trades({"items": []})
        assert summary == {"resolved": 0, "skipped": 0, "remaining": 0, "expired": 0}

    def test_multiple_pending_resolved_independently(self):
        """Two pending entries — one resolves, one skips (no matching feature)."""
        entry_a = _seed_pending_entry(direction="call", entry_price=1.00, feature_key="key_a")
        entry_b = dict(entry_a)
        entry_b["feature_key"] = "key_b"
        entry_b["direction"] = "put"
        ledger = _read_ledger()
        ledger["entries"].append(entry_b)
        _write_ledger(ledger)

        feature_snapshot = {
            "items": [
                {"key": "key_a", "price_available": True, "last": 1.01},
                # key_b not in features
            ]
        }
        summary = resolve_pending_paper_trades(feature_snapshot)
        assert summary["resolved"] == 1
        assert summary["skipped"] == 1
        assert summary["remaining"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: execute_signal_paper_trade
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecuteSignalPaperTrade:

    def test_non_ibkr_produces_pending(self):
        """Non-IBKR trades should produce pending_resolution (deferred)."""
        result = execute_signal_paper_trade(
            _make_strategy(venue="pocket_option"),
            _make_signal(),
            _make_feature(),
            _make_lane(),
        )
        assert result["success"] is True
        trade = result["trade"]
        assert trade["result"] == "pending_resolution"
        assert trade["resolved"] is False
        assert trade["resolution_mode"] == "deferred_forward_v1"

    def test_rejects_signal_not_ready(self):
        result = execute_signal_paper_trade(
            _make_strategy(),
            _make_signal(execution_ready=False),
            _make_feature(),
            _make_lane(),
        )
        assert result["success"] is False
        assert result["error"] == "signal_not_ready_for_execution"

    def test_rejects_no_price(self):
        result = execute_signal_paper_trade(
            _make_strategy(),
            _make_signal(),
            _make_feature(price_available=False),
            _make_lane(),
        )
        assert result["success"] is False
        assert result["error"] == "no_price_context_for_signal_execution"

    def test_trade_appended_to_ledger(self):
        execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(), _make_lane(),
        )
        ledger = _read_ledger()
        assert len(ledger["entries"]) >= 1
        assert ledger["entries"][-1]["strategy_id"] == "test_strat"

    def test_executor_platform_set(self):
        result = execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(),
            _make_lane(platform="custom_lane"),
        )
        assert result["trade"]["executor_platform"] == "custom_lane"

    def test_ibkr_uses_deferred_forward(self):
        """IBKR venue now uses deferred_forward_v1 like all other venues (9X-01)."""
        result = execute_signal_paper_trade(
            _make_strategy(venue="ibkr"),
            _make_signal(),
            _make_feature(),
            _make_lane(),
        )
        assert result["success"] is True
        trade = result["trade"]
        assert trade["result"] == "pending_resolution"
        assert trade["resolved"] is False
        assert trade["resolution_mode"] == "deferred_forward_v1"

    def test_ibkr_no_history_resolution_function(self):
        """_history_resolution was removed in 9X-01 — verify it doesn't exist."""
        import brain_v9.trading.paper_execution as mod
        assert not hasattr(mod, "_history_resolution")

    def test_trade_deduplication_cooldown(self, monkeypatch):
        """9X-02: second trade for same strategy+symbol within cooldown is rejected."""
        monkeypatch.setattr(_cfg, "AUTONOMY_CONFIG", {**_cfg.AUTONOMY_CONFIG, "trade_cooldown_seconds": 120})
        # First trade succeeds
        result1 = execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(), _make_lane(),
        )
        assert result1["success"] is True

        # Second trade within cooldown is rejected
        result2 = execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(), _make_lane(),
        )
        assert result2["success"] is False
        assert result2["error"] == "trade_cooldown_active"

    def test_trade_dedup_allows_different_symbol(self, monkeypatch):
        """9X-02: cooldown only blocks same strategy+symbol pair."""
        monkeypatch.setattr(_cfg, "AUTONOMY_CONFIG", {**_cfg.AUTONOMY_CONFIG, "trade_cooldown_seconds": 120})
        result1 = execute_signal_paper_trade(
            _make_strategy(), _make_signal(symbol="EURUSD_otc"), _make_feature(), _make_lane(),
        )
        assert result1["success"] is True

        # Different symbol should succeed
        result2 = execute_signal_paper_trade(
            _make_strategy(),
            _make_signal(symbol="GBPUSD_otc", feature_key="po::GBPUSD_otc::1m"),
            _make_feature(), _make_lane(),
        )
        assert result2["success"] is True

    def test_trade_dedup_disabled_when_zero(self, monkeypatch):
        """9X-02: cooldown of 0 disables deduplication."""
        monkeypatch.setattr(_cfg, "AUTONOMY_CONFIG", {**_cfg.AUTONOMY_CONFIG, "trade_cooldown_seconds": 0})
        result1 = execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(), _make_lane(),
        )
        assert result1["success"] is True

        # Second trade should also succeed when cooldown is 0
        result2 = execute_signal_paper_trade(
            _make_strategy(), _make_signal(), _make_feature(), _make_lane(),
        )
        assert result2["success"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: execute_paper_trade (agent tool wrapper)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecutePaperTrade:

    def test_returns_pending_for_non_ibkr(self):
        result = execute_paper_trade(
            strategy={"strategy_id": "agent_manual", "family": "trend_following",
                       "venue": "internal", "preferred_symbol": "EURUSD_otc"},
            signal={"direction": "call", "confidence": 0.5, "symbol": "EURUSD_otc"},
            feature={"price_available": True, "last": 1.085, "mid": 1.085,
                      "last_vs_close_pct": 0.0, "bid_ask_imbalance": 0.0,
                      "payout_pct": 80.0},
        )
        assert result["success"] is True
        assert result["result"] == "pending_resolution"
        assert result["profit"] == 0.0

    def test_enriches_signal_defaults(self):
        """execute_paper_trade should add execution_ready if missing."""
        result = execute_paper_trade(
            strategy={"strategy_id": "x", "venue": "internal"},
            signal={"direction": "put"},
            feature={"price_available": True, "last": 100.0},
        )
        assert result["success"] is True
        # The trade should exist in the ledger
        ledger = _read_ledger()
        assert len(ledger["entries"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: no random.choice, no circular alignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoFabrication:

    def test_no_random_import_in_module(self):
        """paper_execution.py must not import random."""
        import brain_v9.trading.paper_execution as mod
        import inspect
        source = inspect.getsource(mod)
        assert "import random" not in source
        assert "random.choice" not in source

    def test_no_alignment_outcome_function(self):
        """The old _alignment_outcome function should be removed."""
        import brain_v9.trading.paper_execution as mod
        assert not hasattr(mod, "_alignment_outcome")

    def test_no_random_import_in_platform_accumulators(self):
        """platform_accumulators.py must not import random."""
        import brain_v9.autonomy.platform_accumulators as mod
        import inspect
        source = inspect.getsource(mod)
        assert "import random" not in source
        assert "random.choice" not in source


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _update_platform_metrics (9X-fix — platform metrics bridge)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdatePlatformMetrics:

    def test_venue_to_platform_mapping(self):
        """Verify the mapping table covers all known venues."""
        assert _VENUE_TO_PLATFORM["pocket_option"] == "pocket_option"
        assert _VENUE_TO_PLATFORM["ibkr"] == "ibkr"
        assert _VENUE_TO_PLATFORM["internal"] == "internal_paper"
        assert _VENUE_TO_PLATFORM["internal_paper"] == "internal_paper"

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_calls_record_trade_for_win(self, mock_get_pm):
        """A resolved win should call record_trade with correct args."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        entries = [{
            "venue": "pocket_option",
            "result": "win",
            "profit": 6.56,
            "symbol": "EURUSD_otc",
            "strategy_id": "po_breakout_v1",
        }]
        _update_platform_metrics(entries)

        mock_pm.record_trade.assert_called_once_with(
            "pocket_option", "win", 6.56, "EURUSD_otc", "po_breakout_v1",
        )

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_calls_record_trade_for_loss_abs_profit(self, mock_get_pm):
        """A loss has negative profit in ledger; record_trade gets abs value."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        entries = [{
            "venue": "ibkr",
            "result": "loss",
            "profit": -10.0,
            "symbol": "AAPL",
            "strategy_id": "ibkr_strat_1",
        }]
        _update_platform_metrics(entries)

        mock_pm.record_trade.assert_called_once_with(
            "ibkr", "loss", 10.0, "AAPL", "ibkr_strat_1",
        )

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_maps_internal_venue_to_internal_paper(self, mock_get_pm):
        """Venue 'internal' maps to platform 'internal_paper'."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        entries = [{
            "venue": "internal",
            "result": "win",
            "profit": 5.0,
            "symbol": "SPY",
            "strategy_id": "internal_strat",
        }]
        _update_platform_metrics(entries)

        mock_pm.record_trade.assert_called_once_with(
            "internal_paper", "win", 5.0, "SPY", "internal_strat",
        )

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_handles_multiple_entries(self, mock_get_pm):
        """Multiple resolved entries each produce a record_trade call."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        entries = [
            {"venue": "pocket_option", "result": "win", "profit": 6.0,
             "symbol": "EURUSD_otc", "strategy_id": "s1"},
            {"venue": "ibkr", "result": "loss", "profit": -10.0,
             "symbol": "AAPL", "strategy_id": "s2"},
        ]
        _update_platform_metrics(entries)

        assert mock_pm.record_trade.call_count == 2

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_empty_list_skips_entirely(self, mock_get_pm):
        """Empty list should not even instantiate PlatformManager."""
        _update_platform_metrics([])
        mock_get_pm.assert_not_called()

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_unknown_venue_falls_back_to_internal_paper(self, mock_get_pm):
        """An unrecognized venue defaults to internal_paper."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        entries = [{
            "venue": "unknown_exchange",
            "result": "loss",
            "profit": -3.0,
            "symbol": "XYZ",
            "strategy_id": "mystery",
        }]
        _update_platform_metrics(entries)

        mock_pm.record_trade.assert_called_once_with(
            "internal_paper", "loss", 3.0, "XYZ", "mystery",
        )

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_single_entry_failure_does_not_block_others(self, mock_get_pm):
        """If record_trade raises on one entry, the next entry still runs."""
        mock_pm = MagicMock()
        mock_pm.record_trade.side_effect = [RuntimeError("boom"), None]
        mock_get_pm.return_value = mock_pm

        entries = [
            {"venue": "pocket_option", "result": "win", "profit": 5.0,
             "symbol": "A", "strategy_id": "s1"},
            {"venue": "ibkr", "result": "loss", "profit": -10.0,
             "symbol": "B", "strategy_id": "s2"},
        ]
        _update_platform_metrics(entries)

        assert mock_pm.record_trade.call_count == 2

    @patch("brain_v9.trading.platform_manager.get_platform_manager", side_effect=ImportError("no module"))
    def test_import_failure_does_not_crash(self, mock_get_pm):
        """If PlatformManager can't be imported, function logs and returns."""
        entries = [{"venue": "ibkr", "result": "win", "profit": 5.0,
                     "symbol": "X", "strategy_id": "s"}]
        # Should not raise
        _update_platform_metrics(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _update_strategy_scorecards (9X — scorecard resolution bridge)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_blank_scorecard(strategy_id="test_strat", venue="pocket_option"):
    """Minimal scorecard with entries_taken=1, entries_open=1 (as if a
    pending trade was already recorded at creation time)."""
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": "trend_following",
        "entries_taken": 1,
        "entries_open": 1,
        "entries_resolved": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "net_pnl": 0.0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "expectancy": 0.0,
        "profit_factor": 0.0,
        "sample_quality": 0.0,
        "consistency_score": 0.0,
        "recent_5_outcomes": [],
        "last_trade_utc": "2026-03-25T12:00:00Z",
        "success_criteria": {},
        "promotion_state": "evaluating",
        "governance_state": "active",
        "freeze_recommended": False,
        "promote_candidate": False,
        "watch_recommended": False,
    }


def _make_scorecards_payload(strategy_id="test_strat", venue="pocket_option"):
    """Build a full scorecards payload with one aggregate card."""
    card = _make_blank_scorecard(strategy_id, venue)
    sym_key = f"{venue}::{strategy_id}::EURUSD_otc"
    sym_card = dict(card, symbol="EURUSD_otc")
    ctx_key = f"{venue}::{strategy_id}::EURUSD_otc::1m::base"
    ctx_card = dict(card, symbol="EURUSD_otc", timeframe="1m", setup_variant="base")
    return {
        "schema_version": "strategy_scorecards_v3",
        "updated_utc": "2026-03-25T12:00:00Z",
        "scorecards": {strategy_id: card},
        "symbol_scorecards": {sym_key: sym_card},
        "context_scorecards": {ctx_key: ctx_card},
    }


def _resolved_entry(result="win", profit=6.56, strategy_id="test_strat",
                     venue="pocket_option", symbol="EURUSD_otc",
                     timeframe="1m", setup_variant="base", direction="call"):
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "symbol": symbol,
        "timeframe": timeframe,
        "setup_variant": setup_variant,
        "direction": direction,
        "result": result,
        "profit": profit,
        "resolved_utc": "2026-03-25T13:00:00Z",
        "timestamp": "2026-03-25T12:00:00Z",
    }


class TestUpdateStrategyScorecards:
    """Tests for the resolution-only scorecard bridge."""

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_win_increments_wins_and_resolves(self, mock_read, mock_write):
        """A resolved win should increment wins, entries_resolved, decrement entries_open."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=6.56)])

        card = payload["scorecards"]["test_strat"]
        assert card["entries_resolved"] == 1
        assert card["entries_open"] == 0
        assert card["wins"] == 1
        assert card["losses"] == 0
        assert card["gross_profit"] == 6.56
        assert card["net_pnl"] == 6.56
        assert card["entries_taken"] == 1  # NOT incremented — no double-count

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_loss_increments_losses(self, mock_read, mock_write):
        """A resolved loss should increment losses and gross_loss."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="loss", profit=-8.0)])

        card = payload["scorecards"]["test_strat"]
        assert card["entries_resolved"] == 1
        assert card["entries_open"] == 0
        assert card["losses"] == 1
        assert card["wins"] == 0
        assert card["gross_loss"] == 8.0
        assert card["largest_loss"] == 8.0
        assert card["net_pnl"] == -8.0
        assert card["entries_taken"] == 1  # NOT double-counted

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_draw_increments_draws(self, mock_read, mock_write):
        """A resolved draw increments draws, not wins or losses."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="draw", profit=0.0)])

        card = payload["scorecards"]["test_strat"]
        assert card["draws"] == 1
        assert card["wins"] == 0
        assert card["losses"] == 0

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_recompute_sets_win_rate_and_expectancy(self, mock_read, mock_write):
        """After resolution, _recompute should set win_rate and expectancy."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=10.0)])

        card = payload["scorecards"]["test_strat"]
        assert card["win_rate"] == 1.0
        assert card["expectancy"] == 10.0
        assert card["sample_quality"] > 0.0

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_updates_symbol_and_context_cards(self, mock_read, mock_write):
        """Resolution should also update symbol and context scorecards."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=5.0)])

        sym_key = "pocket_option::test_strat::EURUSD_otc"
        ctx_key = "pocket_option::test_strat::EURUSD_otc::1m::base"
        assert payload["symbol_scorecards"][sym_key]["wins"] == 1
        assert payload["symbol_scorecards"][sym_key]["entries_resolved"] == 1
        assert payload["context_scorecards"][ctx_key]["wins"] == 1
        assert payload["context_scorecards"][ctx_key]["entries_resolved"] == 1

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_multiple_entries_accumulate(self, mock_read, mock_write):
        """Multiple resolved entries accumulate correctly."""
        # Start with entries_taken=3, entries_open=3 (3 pending trades)
        payload = _make_scorecards_payload()
        for card_dict in [payload["scorecards"], payload["symbol_scorecards"], payload["context_scorecards"]]:
            for card in card_dict.values():
                card["entries_taken"] = 3
                card["entries_open"] = 3
        mock_read.return_value = payload

        entries = [
            _resolved_entry(result="win", profit=6.0),
            _resolved_entry(result="loss", profit=-8.0),
            _resolved_entry(result="win", profit=4.0),
        ]
        _update_strategy_scorecards(entries)

        card = payload["scorecards"]["test_strat"]
        assert card["entries_taken"] == 3  # unchanged
        assert card["entries_open"] == 0
        assert card["entries_resolved"] == 3
        assert card["wins"] == 2
        assert card["losses"] == 1
        assert card["net_pnl"] == 2.0  # 6 - 8 + 4

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_entries_open_does_not_go_negative(self, mock_read, mock_write):
        """If entries_open is already 0, it should stay at 0."""
        payload = _make_scorecards_payload()
        payload["scorecards"]["test_strat"]["entries_open"] = 0
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=5.0)])

        card = payload["scorecards"]["test_strat"]
        assert card["entries_open"] == 0
        assert card["entries_resolved"] == 1

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_empty_list_skips_entirely(self, mock_read, mock_write):
        """Empty list should not even load scorecards."""
        _update_strategy_scorecards([])
        mock_read.assert_not_called()
        mock_write.assert_not_called()

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_missing_strategy_skipped(self, mock_read, mock_write):
        """Entry with a strategy_id not in scorecards is skipped."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(strategy_id="nonexistent")])

        card = payload["scorecards"]["test_strat"]
        assert card["entries_resolved"] == 0  # unchanged
        # write_json still NOT called since no cards were modified
        mock_write.assert_not_called()

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_recent_5_outcomes_appended(self, mock_read, mock_write):
        """Resolved entries should be appended to recent_5_outcomes."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=5.0)])

        card = payload["scorecards"]["test_strat"]
        assert len(card["recent_5_outcomes"]) == 1
        assert card["recent_5_outcomes"][0]["result"] == "win"
        assert card["recent_5_outcomes"][0]["resolved"] is True

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_single_entry_failure_does_not_block_others(self, mock_read, mock_write):
        """If one entry throws during processing, the next one still runs."""
        payload = _make_scorecards_payload()
        # Add a second strategy
        payload["scorecards"]["strat2"] = _make_blank_scorecard("strat2")
        mock_read.return_value = payload

        entries = [
            # First entry: strategy exists, but we'll sabotage the card
            _resolved_entry(result="win", profit=5.0, strategy_id="test_strat"),
            # Second entry: valid
            _resolved_entry(result="loss", profit=-3.0, strategy_id="strat2"),
        ]

        # Sabotage: make the first card raise during _recompute
        # by setting a field to a non-numeric value
        payload["scorecards"]["test_strat"]["wins"] = "not_a_number"

        _update_strategy_scorecards(entries)

        # Second strategy should still be updated
        assert payload["scorecards"]["strat2"]["losses"] == 1

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_largest_win_tracks_max(self, mock_read, mock_write):
        """largest_win should be the max of all wins seen."""
        payload = _make_scorecards_payload()
        payload["scorecards"]["test_strat"]["entries_taken"] = 2
        payload["scorecards"]["test_strat"]["entries_open"] = 2
        mock_read.return_value = payload

        entries = [
            _resolved_entry(result="win", profit=3.0),
            _resolved_entry(result="win", profit=7.5),
        ]
        _update_strategy_scorecards(entries)

        card = payload["scorecards"]["test_strat"]
        assert card["largest_win"] == 7.5
        assert card["gross_profit"] == 10.5

    @patch("brain_v9.trading.paper_execution.write_json")
    @patch("brain_v9.trading.strategy_scorecard.read_json")
    def test_writes_updated_payload(self, mock_read, mock_write):
        """After modifications, payload should be written to disk."""
        payload = _make_scorecards_payload()
        mock_read.return_value = payload

        _update_strategy_scorecards([_resolved_entry(result="win", profit=5.0)])

        mock_write.assert_called_once()
        # First arg should be the SCORECARDS_PATH, second the payload
        written_payload = mock_write.call_args[0][1]
        assert "updated_utc" in written_payload
        assert written_payload["scorecards"]["test_strat"]["wins"] == 1
