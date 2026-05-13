"""P5-09: Tests for stale data detection — feature freshness computation,
feature-engine enrichment, and signal-engine blocker.

Covers:
 1. _compute_data_age() — fresh timestamp within threshold
 2. _compute_data_age() — stale timestamp exceeds threshold
 3. _compute_data_age() — None captured_utc → (None, True)
 4. _compute_data_age() — unparseable string → (None, True)
 5. _compute_data_age() — per-venue threshold (ibkr vs pocket_option)
 6. _compute_data_age() — "_default" fallback for unknown venue
 7. _compute_data_age() — naive timestamp treated as UTC
 8. Config: FEATURE_MAX_AGE_SECONDS has expected default keys
 9. Feature engine: IBKR items include data_age_seconds and is_stale
10. Feature engine: PO items include data_age_seconds and is_stale
11. Feature engine: snapshot summary includes stale_count / fresh_count
12. Feature engine: missing captured_utc → is_stale=True
13. Signal engine: fresh data passes (no data_too_stale blocker)
14. Signal engine: stale data produces data_too_stale blocker
15. Signal engine: stale data blocks execution_ready
16. Signal engine: signal output includes data_age_seconds and is_stale
17. Signal engine: multiple blockers can coexist with data_too_stale
18. Feature engine: env var override of thresholds
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(
    strategy_id: str = "strat_trend_01",
    venue: str = "ibkr",
    family: str = "trend_following",
    universe: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "family": family,
        "venue": venue,
        "status": "paper_candidate",
        "universe": universe or ["SPY"],
        "asset_classes": ["equity_etf"],
        "timeframes": ["spot"],
        "setup_variants": ["base"],
        "filters": {},
        "core_indicators": [],
        "confidence_threshold": 0.45,
    }


def _utc_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _write_ibkr_probe(base: Path, checked_utc: str | None, symbols: Dict | None = None) -> None:
    """Write a minimal IBKR probe status file."""
    room = base / "tmp_agent" / "state" / "rooms" / "brain_financial_ingestion_fi04_structured_api"
    room.mkdir(parents=True, exist_ok=True)
    probe = {
        "checked_utc": checked_utc,
        "symbols": symbols or {
            "SPY_ETF": {
                "has_any_tick": True,
                "last": 520.50,
                "bid": 520.40,
                "ask": 520.60,
                "close": 519.00,
                "bidSize": 100.0,
                "askSize": 120.0,
            },
        },
    }
    (room / "ibkr_marketdata_probe_status.json").write_text(
        json.dumps(probe), encoding="utf-8",
    )


def _write_po_bridge(base: Path, captured_utc: str | None) -> None:
    """Write a minimal PO bridge file."""
    room = base / "tmp_agent" / "state" / "rooms" / "brain_binary_paper_pb04_demo_execution"
    room.mkdir(parents=True, exist_ok=True)
    bridge = {
        "captured_utc": captured_utc,
        "current": {
            "symbol": "EURUSD_otc",
            "payout_pct": 85,
            "expiry_seconds": 60,
        },
        "dom": {
            "duration_candidates": [{"label": "1m"}],
            "indicator_candidates": [],
            "indicator_readouts": [],
        },
        "ws": {
            "stream_symbol_match": True,
            "last_stream_symbol": "EURUSD_otc",
            "visible_symbol": "EURUSD_otc",
        },
    }
    (room / "browser_bridge_latest.json").write_text(
        json.dumps(bridge), encoding="utf-8",
    )
    # Also write a minimal feed so price context works
    feed = {
        "rows": [
            {"symbol": "EURUSD_otc", "price": 1.08500 + i * 0.00001, "stream_symbol_match": True}
            for i in range(10)
        ],
    }
    (room / "browser_bridge_normalized_feed.json").write_text(
        json.dumps(feed), encoding="utf-8",
    )


def _patch_feature_paths(monkeypatch, base: Path) -> None:
    """Redirect feature engine module-level path constants to the temp dir."""
    import brain_v9.trading.feature_engine as fe
    state = base / "tmp_agent" / "state"
    engine = state / "strategy_engine"
    engine.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fe, "ENGINE_PATH", engine)
    monkeypatch.setattr(fe, "IBKR_PROBE_PATH",
                        state / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json")
    monkeypatch.setattr(fe, "PO_BRIDGE_PATH",
                        state / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json")
    monkeypatch.setattr(fe, "PO_FEED_PATH",
                        state / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_normalized_feed.json")
    monkeypatch.setattr(fe, "FEATURE_SNAPSHOT_PATH", engine / "market_feature_snapshot_latest.json")


def _patch_signal_paths(monkeypatch, base: Path) -> None:
    """Redirect signal engine module-level path constants to the temp dir."""
    import brain_v9.trading.signal_engine as se
    state = base / "tmp_agent" / "state"
    engine = state / "strategy_engine"
    engine.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(se, "STATE_PATH", state)
    monkeypatch.setattr(se, "ENGINE_PATH", engine)
    monkeypatch.setattr(se, "SIGNAL_SNAPSHOT_PATH", engine / "strategy_signal_snapshot_latest.json")


# ===========================================================================
# 1-7: _compute_data_age unit tests
# ===========================================================================

class TestComputeDataAge:
    """Direct tests for the _compute_data_age helper."""

    def test_fresh_timestamp(self, monkeypatch):
        """1. A timestamp 60s old with 900s threshold → fresh."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=60))
        age, stale = _compute_data_age(ts, "ibkr")
        assert age is not None
        assert 50 <= age <= 75  # some tolerance
        assert stale is False

    def test_stale_timestamp(self, monkeypatch):
        """2. A timestamp 1200s old with 900s IBKR threshold → stale."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=1200))
        age, stale = _compute_data_age(ts, "ibkr")
        assert age is not None
        assert age > 900
        assert stale is True

    def test_none_captured_utc(self, monkeypatch):
        """3. None captured_utc → (None, True)."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        age, stale = _compute_data_age(None, "ibkr")
        assert age is None
        assert stale is True

    def test_unparseable_string(self, monkeypatch):
        """4. Garbage string → (None, True)."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        age, stale = _compute_data_age("not-a-date", "ibkr")
        assert age is None
        assert stale is True

    def test_per_venue_threshold_po(self, monkeypatch):
        """5. PO has 300s threshold — 400s old is stale for PO but fresh for IBKR."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=400))
        age_po, stale_po = _compute_data_age(ts, "pocket_option")
        age_ibkr, stale_ibkr = _compute_data_age(ts, "ibkr")
        assert stale_po is True
        assert stale_ibkr is False

    def test_default_fallback_unknown_venue(self, monkeypatch):
        """6. Unknown venue uses _default threshold."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        # 700s old — exceeds _default of 600
        ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=700))
        age, stale = _compute_data_age(ts, "quantconnect")
        assert stale is True

        # 500s old — within _default of 600
        ts2 = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=500))
        age2, stale2 = _compute_data_age(ts2, "quantconnect")
        assert stale2 is False

    def test_naive_timestamp_treated_as_utc(self, monkeypatch):
        """7. Naive ISO timestamp (no tz) is treated as UTC."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        # Produce a naive ISO string (no Z, no +00:00)
        naive = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S")
        age, stale = _compute_data_age(naive, "ibkr")
        assert age is not None
        assert 50 <= age <= 75
        assert stale is False


# ===========================================================================
# 8: Config test
# ===========================================================================

class TestConfigDefaults:
    """8. FEATURE_MAX_AGE_SECONDS has expected keys and sensible defaults."""

    def test_config_has_expected_keys(self):
        assert "ibkr" in _cfg.FEATURE_MAX_AGE_SECONDS
        assert "pocket_option" in _cfg.FEATURE_MAX_AGE_SECONDS
        assert "_default" in _cfg.FEATURE_MAX_AGE_SECONDS

    def test_config_values_are_ints(self):
        for key, val in _cfg.FEATURE_MAX_AGE_SECONDS.items():
            assert isinstance(val, int), f"{key} should be int, got {type(val)}"

    def test_config_ibkr_default(self):
        assert _cfg.FEATURE_MAX_AGE_SECONDS["ibkr"] == 900

    def test_config_po_default(self):
        assert _cfg.FEATURE_MAX_AGE_SECONDS["pocket_option"] == 375  # P-OP26: 5m timeframe

    def test_config_default_fallback(self):
        assert _cfg.FEATURE_MAX_AGE_SECONDS["_default"] == 600


# ===========================================================================
# 9-12: Feature engine integration tests
# ===========================================================================

class TestFeatureEngineStaleFields:
    """Feature engine items include data_age_seconds and is_stale."""

    def test_ibkr_items_have_freshness_fields(self, monkeypatch, tmp_path):
        """9. IBKR feature items include data_age_seconds and is_stale."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        _patch_feature_paths(monkeypatch, tmp_path)
        fresh_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=30))
        _write_ibkr_probe(tmp_path, fresh_ts)

        from brain_v9.trading.feature_engine import _build_ibkr_features
        items = _build_ibkr_features()
        assert len(items) > 0
        for item in items:
            assert "data_age_seconds" in item
            assert "is_stale" in item
            assert item["is_stale"] is False
            assert item["data_age_seconds"] is not None
            assert item["data_age_seconds"] < 900

    def test_po_items_have_freshness_fields(self, monkeypatch, tmp_path):
        """10. PO feature items include data_age_seconds and is_stale."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        _patch_feature_paths(monkeypatch, tmp_path)
        fresh_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=30))
        _write_po_bridge(tmp_path, fresh_ts)

        from brain_v9.trading.feature_engine import _build_pocket_option_features
        items = _build_pocket_option_features()
        assert len(items) > 0
        for item in items:
            assert "data_age_seconds" in item
            assert "is_stale" in item
            assert item["is_stale"] is False

    def test_snapshot_summary_includes_freshness(self, monkeypatch, tmp_path):
        """11. Snapshot summary includes stale_count and fresh_count."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        _patch_feature_paths(monkeypatch, tmp_path)
        # IBKR fresh, PO stale
        fresh_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=30))
        stale_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=600))
        _write_ibkr_probe(tmp_path, fresh_ts)
        _write_po_bridge(tmp_path, stale_ts)

        from brain_v9.trading.feature_engine import build_market_feature_snapshot
        snap = build_market_feature_snapshot()
        summary = snap["summary"]
        assert "stale_count" in summary
        assert "fresh_count" in summary
        assert summary["stale_count"] >= 1  # PO is stale
        assert summary["fresh_count"] >= 1  # IBKR is fresh
        assert summary["stale_count"] + summary["fresh_count"] == summary["items_count"]

    def test_missing_captured_utc_is_stale(self, monkeypatch, tmp_path):
        """12. Missing captured_utc → is_stale=True."""
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })
        _patch_feature_paths(monkeypatch, tmp_path)
        _write_ibkr_probe(tmp_path, None)  # no checked_utc

        from brain_v9.trading.feature_engine import _build_ibkr_features
        items = _build_ibkr_features()
        assert len(items) > 0
        for item in items:
            assert item["is_stale"] is True
            assert item["data_age_seconds"] is None


# ===========================================================================
# 13-17: Signal engine integration tests
# ===========================================================================

class TestSignalEngineStaleness:
    """Signal engine rejects stale data via data_too_stale blocker."""

    def _build_feature(self, *, is_stale: bool = False, data_age: float | None = 30.0,
                       venue: str = "ibkr", price_available: bool = True) -> Dict[str, Any]:
        return {
            "key": f"{venue}::SPY::spot",
            "captured_utc": _utc_iso(datetime.now(timezone.utc)),
            "data_age_seconds": data_age,
            "is_stale": is_stale,
            "venue": venue,
            "symbol": "SPY",
            "timeframe": "spot",
            "asset_class": "equity_etf",
            "price_available": price_available,
            "last": 520.50,
            "bid": 520.40,
            "ask": 520.60,
            "close": 519.00,
            "mid": 520.50,
            "spread_pct": 0.038,
            "spread_bps": 3.8,
            "bid_ask_imbalance": -0.09,
            "last_vs_close_pct": 0.289,
            "volatility_proxy_pct": 0.289,
            "liquidity_score": 0.65,
            "market_regime": "mild",
            "source_artifact": "test",
        }

    def test_fresh_data_no_stale_blocker(self):
        """13. Fresh data → no data_too_stale blocker."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = _make_strategy()
        feature = self._build_feature(is_stale=False, data_age=30.0)
        result = _evaluate_strategy_feature(strategy, feature)
        assert "data_too_stale" not in result["blockers"]

    def test_stale_data_produces_blocker(self):
        """14. Stale data → data_too_stale in blockers."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = _make_strategy()
        feature = self._build_feature(is_stale=True, data_age=1200.0)
        result = _evaluate_strategy_feature(strategy, feature)
        assert "data_too_stale" in result["blockers"]

    def test_stale_data_blocks_execution(self):
        """15. Stale data blocks execution_ready even if signal is otherwise valid."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = _make_strategy()
        feature = self._build_feature(is_stale=True, data_age=1200.0)
        result = _evaluate_strategy_feature(strategy, feature)
        assert result["execution_ready"] is False
        assert result["signal_valid"] is False

    def test_signal_output_includes_freshness(self):
        """16. Signal output dict includes data_age_seconds and is_stale."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = _make_strategy()
        feature = self._build_feature(is_stale=False, data_age=45.2)
        result = _evaluate_strategy_feature(strategy, feature)
        assert "data_age_seconds" in result
        assert "is_stale" in result
        assert result["data_age_seconds"] == 45.2
        assert result["is_stale"] is False

    def test_stale_coexists_with_other_blockers(self):
        """17. data_too_stale can coexist with other blockers."""
        from brain_v9.trading.signal_engine import _evaluate_strategy_feature
        strategy = _make_strategy(universe=["AAPL"])  # SPY not in universe
        feature = self._build_feature(is_stale=True, data_age=1200.0)
        result = _evaluate_strategy_feature(strategy, feature)
        assert "data_too_stale" in result["blockers"]
        assert "symbol_not_in_universe" in result["blockers"]


# ===========================================================================
# 18: Env var override test
# ===========================================================================

class TestEnvVarOverride:
    """18. Environment variables can override FEATURE_MAX_AGE_SECONDS."""

    def test_env_override_ibkr(self, monkeypatch):
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 120, "pocket_option": 300, "_default": 600,
        })
        from brain_v9.trading.feature_engine import _compute_data_age

        # 150s old, threshold set to 120 → stale
        ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=150))
        age, stale = _compute_data_age(ts, "ibkr")
        assert stale is True

        # 100s old, threshold 120 → fresh
        ts2 = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=100))
        age2, stale2 = _compute_data_age(ts2, "ibkr")
        assert stale2 is False
