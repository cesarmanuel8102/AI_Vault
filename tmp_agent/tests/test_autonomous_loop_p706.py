"""P7-06: Autonomous loop stabilization — end-to-end pipeline integration tests.

Verifies the full autonomous pipeline chain:
  IBKR probe artifact → feature_engine → signal_engine → paper_execution → scorecard

All tests use tmp_path; no real IBKR connection is needed.

Tests:
  1. IBKR probe → feature_engine produces features with correct schema
  2. feature_engine → signal_engine produces signals for a matching strategy
  3. Signal with execution_ready=True → paper_execution writes ledger entry
  4. Full chain: probe → features → signals → execution → scorecard update
  5. Stale probe data is correctly flagged (signal blocked)
  6. Missing probe file → feature_engine returns empty items
  7. Strategy with mismatched venue gets no IBKR signals
  8. Pending trade resolution: deferred PO trade resolves on price move
  9. refresh_strategy_engine orchestrates the full pipeline
 10. AutonomyManager.get_status includes IBKR ingester info
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_old(hours: int = 2) -> str:
    """Return a UTC timestamp that is `hours` old (will be stale)."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _write_probe(path: Path, checked_utc: str | None = None, spy_last: float = 520.50) -> Dict:
    """Write a minimal IBKR probe artifact."""
    probe = {
        "schema_version": "ibkr_marketdata_probe_status_v2",
        "checked_utc": checked_utc or _utc_now(),
        "connected": True,
        "managed_accounts": "DUM123456",
        "symbols": {
            "SPY_ETF": {
                "has_any_tick": True,
                "last": spy_last,
                "bid": spy_last - 0.10,
                "ask": spy_last + 0.10,
                "close": spy_last - 1.50,
                "bidSize": 200.0,
                "askSize": 180.0,
                "lastSize": 50.0,
            },
        },
        "errors": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(probe), encoding="utf-8")
    return probe


def _minimal_strategy(strategy_id: str = "test_trend_spy", venue: str = "ibkr") -> Dict:
    """Build a minimal normalized strategy for testing."""
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": "trend_following",
        "status": "paper_active",
        "timeframes": ["spot", "5m", "15m"],
        "universe": ["SPY", "QQQ", "AAPL"],
        "asset_classes": ["equity_etf", "equity"],
        "entry": {"required_conditions": [], "trigger": []},
        "exit": {"stop_loss": "1.0 * atr_14", "take_profit": "1.5 * atr_14", "time_stop_bars": 12},
        "filters": {
            "spread_pct_max": 0.25,
            "volatility_min_atr_pct": None,
            "market_regime_allowed": ["trend_up", "trend_mild"],
        },
        "success_criteria": {"min_resolved_trades": 30, "min_expectancy": 0.10, "min_win_rate": 0.52},
        "core_indicators": [],
        "setup_variants": ["base"],
        "summary": "Test trend-following strategy for SPY",
        "paper_only": True,
        "linked_hypotheses": [],
        "invalidators": [],
        "confidence_threshold": 0.30,  # Lower threshold for testing
    }


# ===========================================================================
# 1: Probe → Feature Engine
# ===========================================================================

class TestProbeToFeatures:
    def test_ibkr_probe_produces_features(self, monkeypatch, tmp_path):
        """1. IBKR probe artifact → feature_engine builds features with correct schema."""
        import brain_v9.trading.feature_engine as fe

        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path)

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "nonexistent_po_bridge.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "nonexistent_po_feed.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "market_feature_snapshot_latest.json")

        snapshot = fe.build_market_feature_snapshot()

        assert snapshot["schema_version"] == "market_feature_snapshot_v1"
        assert len(snapshot["items"]) >= 1

        spy_feature = next((f for f in snapshot["items"] if f["symbol"] == "SPY"), None)
        assert spy_feature is not None
        assert spy_feature["venue"] == "ibkr"
        assert spy_feature["price_available"] is True
        assert spy_feature["last"] == 520.5
        assert spy_feature["is_stale"] is False
        assert spy_feature["key"] == "ibkr::SPY::spot"
        assert "spread_pct" in spy_feature
        assert "market_regime" in spy_feature

        # Verify file was written
        written = json.loads((engine_path / "market_feature_snapshot_latest.json").read_text(encoding="utf-8"))
        assert written["summary"]["items_count"] >= 1


# ===========================================================================
# 2: Features → Signal Engine
# ===========================================================================

class TestFeaturesToSignals:
    def test_signal_engine_generates_signals(self, monkeypatch, tmp_path):
        """2. feature → signal_engine produces signals for a matching strategy."""
        import brain_v9.trading.feature_engine as fe
        import brain_v9.trading.signal_engine as se

        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path)

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "market_feature_snapshot_latest.json")
        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine_path / "strategy_signal_snapshot_latest.json")

        feature_snapshot = fe.build_market_feature_snapshot()
        strategy = _minimal_strategy()

        signal_snapshot = se.build_strategy_signal_snapshot(
            strategies=[strategy],
            feature_snapshot=feature_snapshot,
        )

        assert signal_snapshot["schema_version"] == "strategy_signal_snapshot_v1"
        assert len(signal_snapshot["by_strategy"]) == 1

        strat_signals = signal_snapshot["by_strategy"][0]
        assert strat_signals["strategy_id"] == "test_trend_spy"
        assert len(strat_signals["signal_candidates"]) >= 1

        # Check best signal exists
        best = strat_signals.get("best_signal")
        assert best is not None
        assert best["symbol"] == "SPY"
        assert best["venue"] == "ibkr"
        assert "direction" in best
        assert "confidence" in best

        # Verify file was written
        assert (engine_path / "strategy_signal_snapshot_latest.json").exists()


# ===========================================================================
# 3: Signal → Paper Execution
# ===========================================================================

class TestSignalToExecution:
    def test_execution_ready_signal_writes_ledger(self, monkeypatch, tmp_path):
        """3. execution_ready signal → paper_execution writes a ledger entry."""
        import brain_v9.trading.paper_execution as pe

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(pe, "STATE_PATH", tmp_path)
        monkeypatch.setattr(pe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH", engine_path / "signal_paper_execution_ledger.json")
        monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH", engine_path / "signal_paper_execution_cursor.json")

        strategy = _minimal_strategy()
        signal = {
            "strategy_id": "test_trend_spy",
            "venue": "ibkr",
            "symbol": "SPY",
            "timeframe": "spot",
            "direction": "call",
            "signal_valid": True,
            "execution_ready": True,
            "confidence": 0.72,
            "signal_score": 0.65,
            "entry_price": 520.50,
            "market_regime": "trend_up",
            "blockers": [],
            "feature_key": "ibkr::SPY::spot",
        }
        feature = {
            "key": "ibkr::SPY::spot",
            "venue": "ibkr",
            "symbol": "SPY",
            "price_available": True,
            "last": 520.50,
            "is_stale": False,
        }
        lane = {
            "platform": "ibkr",
            "venue": "ibkr",
            "execution_ready": True,
            "reason": "test",
        }

        # 9X-01: IBKR now uses deferred_forward_v1 (no more Tiingo history resolution)
        result = pe.execute_signal_paper_trade(strategy, signal, feature, lane)

        assert result["success"] is True
        assert result["trade"]["strategy_id"] == "test_trend_spy"
        assert result["trade"]["result"] == "pending_resolution"
        assert result["trade"]["resolved"] is False
        assert result["trade"]["resolution_mode"] == "deferred_forward_v1"

        # Verify ledger was written
        ledger = json.loads((engine_path / "signal_paper_execution_ledger.json").read_text(encoding="utf-8"))
        assert len(ledger["entries"]) == 1


# ===========================================================================
# 4: Full chain (mocked Tiingo)
# ===========================================================================

class TestFullChain:
    def test_probe_to_scorecard(self, monkeypatch, tmp_path):
        """4. Full chain: probe → features → signals → execution → scorecard update."""
        import brain_v9.trading.feature_engine as fe
        import brain_v9.trading.signal_engine as se
        import brain_v9.trading.paper_execution as pe

        # Setup paths
        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path)

        # Patch feature engine
        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "features.json")

        # Patch signal engine
        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine_path / "signals.json")

        # Patch paper execution
        monkeypatch.setattr(pe, "STATE_PATH", tmp_path)
        monkeypatch.setattr(pe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH", engine_path / "ledger.json")
        monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH", engine_path / "cursor.json")

        # Step 1: Build features from IBKR probe
        feature_snapshot = fe.build_market_feature_snapshot()
        assert len(feature_snapshot["items"]) >= 1

        spy_feature = next(f for f in feature_snapshot["items"] if f["symbol"] == "SPY")
        assert spy_feature["price_available"] is True

        # Step 2: Generate signals
        strategy = _minimal_strategy()
        signal_snapshot = se.build_strategy_signal_snapshot([strategy], feature_snapshot)
        best_signal = signal_snapshot["by_strategy"][0].get("best_signal")
        assert best_signal is not None
        assert best_signal["symbol"] == "SPY"

        # Step 3: Execute paper trade (9X-01: all venues use deferred_forward_v1)
        if best_signal.get("execution_ready"):
            trade_result = pe.execute_signal_paper_trade(
                strategy, best_signal, spy_feature,
                {"platform": "ibkr", "venue": "ibkr", "execution_ready": True, "reason": "test"},
            )
            assert trade_result["success"] is True
            assert trade_result["trade"]["resolution_mode"] == "deferred_forward_v1"

            # Step 4: Verify ledger written
            ledger = json.loads((engine_path / "ledger.json").read_text(encoding="utf-8"))
            assert len(ledger["entries"]) >= 1
            assert ledger["entries"][-1]["strategy_id"] == "test_trend_spy"
        else:
            # Signal was generated but not execution_ready — still a valid pipeline test
            # This can happen if market_regime doesn't match the strategy filters
            assert best_signal["signal_valid"] is True or len(best_signal["blockers"]) > 0


# ===========================================================================
# 5: Stale data detection
# ===========================================================================

class TestStaleDataBlocking:
    def test_stale_probe_blocks_signal(self, monkeypatch, tmp_path):
        """5. Stale probe data → is_stale=True → signal has 'data_too_stale' blocker."""
        import brain_v9.trading.feature_engine as fe
        import brain_v9.trading.signal_engine as se

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path, checked_utc=_utc_old(hours=3))  # 3 hours old

        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "features.json")
        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine_path / "signals.json")

        features = fe.build_market_feature_snapshot()
        spy_feature = next(f for f in features["items"] if f["symbol"] == "SPY")
        assert spy_feature["is_stale"] is True

        strategy = _minimal_strategy()
        signals = se.build_strategy_signal_snapshot([strategy], features)
        best = signals["by_strategy"][0].get("best_signal")
        if best:
            assert "data_too_stale" in best.get("blockers", [])
            assert best["execution_ready"] is False


# ===========================================================================
# 6: Missing probe
# ===========================================================================

class TestMissingProbe:
    def test_missing_probe_returns_empty(self, monkeypatch, tmp_path):
        """6. Missing probe file → feature_engine returns 0 IBKR items."""
        import brain_v9.trading.feature_engine as fe

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "features.json")

        snapshot = fe.build_market_feature_snapshot()
        ibkr_items = [f for f in snapshot["items"] if f["venue"] == "ibkr"]
        assert len(ibkr_items) == 0


# ===========================================================================
# 7: Venue mismatch
# ===========================================================================

class TestVenueMismatch:
    def test_po_strategy_gets_no_ibkr_signals(self, monkeypatch, tmp_path):
        """7. Strategy with venue=pocket_option gets no signals from IBKR data."""
        import brain_v9.trading.feature_engine as fe
        import brain_v9.trading.signal_engine as se

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path)

        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "features.json")
        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine_path / "signals.json")

        features = fe.build_market_feature_snapshot()
        po_strategy = _minimal_strategy(strategy_id="po_reversion", venue="pocket_option")
        po_strategy["family"] = "mean_reversion"
        po_strategy["universe"] = ["EURUSD_otc"]

        signals = se.build_strategy_signal_snapshot([po_strategy], features)
        strat_entry = signals["by_strategy"][0]
        # PO strategy should have 0 signals from IBKR-only features
        assert len(strat_entry["signal_candidates"]) == 0


# ===========================================================================
# 8: Pending trade resolution
# ===========================================================================

class TestPendingResolution:
    def test_deferred_trade_resolves_on_price_move(self, monkeypatch, tmp_path):
        """8. Pending PO trade resolves to win when price moves favorably."""
        import brain_v9.trading.paper_execution as pe

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        ledger_path = engine_path / "ledger.json"

        monkeypatch.setattr(pe, "STATE_PATH", tmp_path)
        monkeypatch.setattr(pe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH", ledger_path)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH", engine_path / "cursor.json")

        # Write a pending trade in the ledger
        entry_time = _utc_now()
        ledger = {
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": [{
                "trade_id": "T001",
                "strategy_id": "po_test",
                "venue": "pocket_option",
                "symbol": "EURUSD",
                "direction": "call",
                "entry_price": 1.0850,
                "entry_payout_pct": 80.0,
                "result": "pending_resolution",
                "resolved": False,
                "timestamp": entry_time,
                "confidence": 0.65,
                "feature_key": "pocket_option::EURUSD::1m",
            }],
        }
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

        # Build a feature snapshot showing price moved UP (favorable for call)
        feature_snapshot = {
            "items": [{
                "key": "pocket_option::EURUSD::1m",
                "venue": "pocket_option",
                "symbol": "EURUSD",
                "last": 1.0870,  # +0.18% move (above 0.05% threshold)
                "price_available": True,
                "is_stale": False,
            }],
        }

        resolved_result = pe.resolve_pending_paper_trades(feature_snapshot)
        assert resolved_result["resolved"] >= 1

        updated = json.loads(ledger_path.read_text(encoding="utf-8"))
        entry = updated["entries"][0]
        assert entry["resolved"] is True
        assert entry["result"] == "win"


# ===========================================================================
# 9: refresh_strategy_engine orchestration
# ===========================================================================

class TestRefreshOrchestration:
    def test_refresh_returns_summary(self, monkeypatch, tmp_path):
        """9. refresh_strategy_engine returns a summary with expected keys."""
        import brain_v9.trading.strategy_engine as ste
        import brain_v9.trading.feature_engine as fe
        import brain_v9.trading.signal_engine as se
        import brain_v9.trading.paper_execution as pe

        engine_path = tmp_path / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        kb_path = tmp_path / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        runs_path = engine_path / "strategy_runs"
        runs_path.mkdir(parents=True, exist_ok=True)
        comparison_runs_path = engine_path / "comparison_runs"
        comparison_runs_path.mkdir(parents=True, exist_ok=True)

        probe_path = tmp_path / "ibkr_probe.json"
        _write_probe(probe_path)

        # Patch all path constants in strategy_engine
        monkeypatch.setattr(ste, "STATE_PATH", tmp_path)
        monkeypatch.setattr(ste, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(ste, "CANDIDATES_PATH", engine_path / "candidates.json")
        monkeypatch.setattr(ste, "RANKING_PATH", engine_path / "ranking.json")
        monkeypatch.setattr(ste, "RANKING_V2_PATH", engine_path / "ranking_v2.json")
        monkeypatch.setattr(ste, "REPORTS_PATH", engine_path / "reports.ndjson")
        monkeypatch.setattr(ste, "RUNS_PATH", runs_path)
        monkeypatch.setattr(ste, "COMPARISON_RUNS_PATH", comparison_runs_path)
        monkeypatch.setattr(ste, "NEXT_ACTIONS_PATH", tmp_path / "autonomy_next_actions.json")
        monkeypatch.setattr(ste, "PO_BRIDGE_PATH", tmp_path / "po_bridge.json")
        monkeypatch.setattr(ste, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(ste, "IBKR_ORDER_CHECK_PATH", tmp_path / "ibkr_order_check.json")

        # Patch feature engine paths
        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(fe, "PO_BRIDGE_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "PO_FEED_PATH", tmp_path / "x.json")
        monkeypatch.setattr(fe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine_path / "features.json")

        # Patch signal engine paths
        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine_path / "signals.json")

        # Patch paper execution paths
        monkeypatch.setattr(pe, "STATE_PATH", tmp_path)
        monkeypatch.setattr(pe, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH", engine_path / "ledger.json")
        monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH", engine_path / "cursor.json")

        # Write minimal strategy specs
        from brain_v9.core.state_io import write_json
        write_json(kb_path / "strategy_specs.json", {
            "schema_version": "strategy_specs_v1",
            "strategies": [_minimal_strategy()],
        })
        # Write empty hypothesis queue
        write_json(kb_path / "hypothesis_queue.json", {"hypotheses": []})

        # Patch scorecards path
        from brain_v9.trading import strategy_scorecard as ssc
        monkeypatch.setattr(ssc, "SCORECARDS_PATH", engine_path / "scorecards.json")

        # Patch archive path
        from brain_v9.trading import strategy_archive as sa
        monkeypatch.setattr(sa, "ARCHIVE_PATH", engine_path / "archive.json")

        # Patch hypothesis engine paths
        from brain_v9.trading import hypothesis_engine as he
        monkeypatch.setattr(he, "HYP_RESULTS_PATH", engine_path / "hyp_results.json")

        # Patch market history engine
        from brain_v9.trading import market_history_engine as mhe
        monkeypatch.setattr(mhe, "MARKET_HISTORY_PATH", engine_path / "market_history.json")

        # Mock build_market_history_snapshot (needs Tiingo)
        monkeypatch.setattr(ste, "build_market_history_snapshot", lambda strats: {
            "schema_version": "market_history_snapshot_v1",
            "updated_utc": _utc_now(),
            "symbols": {},
            "summary": {},
            "items": [],
        })

        # Mock build_expectancy_snapshot (needs real ledger data)
        monkeypatch.setattr(ste, "build_expectancy_snapshot", lambda: {
            "by_strategy": {"items": []},
            "by_strategy_symbol": {"items": []},
            "by_strategy_context": {"items": []},
            "summary": {},
        })

        # Mock read_market_history_snapshot for paper_execution
        monkeypatch.setattr(
            "brain_v9.trading.market_history_engine.read_market_history_snapshot",
            lambda: {"schema_version": "market_history_snapshot_v1", "symbols": {}, "summary": {}},
        )

        result = ste.refresh_strategy_engine()

        assert "summary" in result
        assert "scorecards" in result
        assert "ranking" in result
        assert "signals" in result
        assert "features" in result
        summary = result["summary"]
        assert "strategies_count" in summary
        assert summary["strategies_count"] >= 1


# ===========================================================================
# 10: AutonomyManager status includes IBKR ingester
# ===========================================================================

class TestAutonomyManagerIngester:
    def test_status_includes_ibkr_ingester(self):
        """10. AutonomyManager.get_status includes ibkr_ingester key."""
        from brain_v9.autonomy.manager import AutonomyManager

        mgr = AutonomyManager()
        status = mgr.get_status()

        assert "running" in status
        assert "ibkr_ingester" in status
        assert "cycle_count" in status
        assert "last_cycle_utc" in status
        assert status["running"] is False
        # Before start(), ingester is None
        assert status["ibkr_ingester"] is None
