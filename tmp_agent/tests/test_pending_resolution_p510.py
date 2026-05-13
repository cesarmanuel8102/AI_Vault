"""P5-10: Tests for pending trade resolution fixes.

Covers:
 1. Config: RESOLUTION_PRICE_THRESHOLD_PCT default is 0.05
 2. Config: PENDING_TRADE_TIMEOUT_SECONDS default is 3600
 3. Resolver: trade with price change above threshold is resolved
 4. Resolver: trade with price change below threshold is skipped
 5. Resolver: old hardcoded 0.01% no longer resolves (threshold raised)
 6. Resolver: trade older than timeout is auto-expired as loss
 7. Resolver: expired trade has resolution_mode=timeout_expired
 8. Resolver: trade within timeout is NOT expired
 9. Resolver: stale feature data causes skip (is_stale=True)
10. Resolver: missing feature_key causes skip (PO bridge down)
11. Resolver: price_available=False causes skip
12. Resolver: return dict includes 'expired' count
13. Resolver: return dict key is 'resolved' (not 'resolved_count')
14. Resolver: configurable threshold via monkeypatch
15. Resolver: configurable timeout via monkeypatch
16. Resolver: already-resolved entries are not re-processed
17. Resolver: direction='call' win when price goes up
18. Resolver: direction='put' win when price goes down
19. Resolver: missing direction skips gracefully
20. Bug fix: rebalance_capital_exposure reads 'resolved' key correctly
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _make_pending_entry(
    *,
    symbol: str = "EURUSD_otc",
    direction: str = "call",
    entry_price: float = 1.08500,
    payout_pct: float = 80.0,
    confidence: float = 0.65,
    feature_key: str = "pocket_option::EURUSD_otc::1m",
    strategy_id: str = "po_scalper_v1",
    venue: str = "pocket_option",
    timestamp: str | None = None,
) -> Dict[str, Any]:
    return {
        "timestamp": timestamp or _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=60)),
        "symbol": symbol,
        "direction": direction,
        "result": "pending_resolution",
        "profit": 0.0,
        "entry_price": entry_price,
        "entry_payout_pct": payout_pct,
        "paper_shadow": True,
        "paper_only": True,
        "strategy_id": strategy_id,
        "venue": venue,
        "family": "binary_scalper",
        "timeframe": "1m",
        "setup_variant": "base",
        "asset_class": "otc_binary",
        "confidence": confidence,
        "signal_score": 0.72,
        "resolution_mode": "deferred_forward_v1",
        "signal_reasons": [],
        "signal_blockers": [],
        "feature_key": feature_key,
        "resolved": False,
    }


def _make_feature(
    *,
    key: str = "pocket_option::EURUSD_otc::1m",
    last: float = 1.08600,
    price_available: bool = True,
    is_stale: bool = False,
) -> Dict[str, Any]:
    return {
        "key": key,
        "venue": "pocket_option",
        "symbol": "EURUSD_otc",
        "timeframe": "1m",
        "price_available": price_available,
        "is_stale": is_stale,
        "last": last,
        "mid": last,
    }


def _make_snapshot(features: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {"items": features or []}


def _setup_ledger(monkeypatch, tmp_path, entries: List[Dict[str, Any]]) -> None:
    """Write ledger and patch paper_execution paths to tmp_path."""
    import brain_v9.trading.paper_execution as pe
    state = tmp_path / "tmp_agent" / "state"
    engine = state / "strategy_engine"
    engine.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pe, "STATE_PATH", state)
    monkeypatch.setattr(pe, "ENGINE_PATH", engine)
    monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH", engine / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH", engine / "signal_paper_execution_cursor.json")

    ledger = {
        "schema_version": "signal_paper_execution_ledger_v1",
        "updated_utc": _utc_iso(datetime.now(timezone.utc)),
        "entries": entries,
    }
    (engine / "signal_paper_execution_ledger.json").write_text(
        json.dumps(ledger), encoding="utf-8",
    )


# ===========================================================================
# 1-2: Config tests
# ===========================================================================

class TestConfigDefaults:

    def test_resolution_threshold_default(self):
        """1. Default threshold is 0.05%."""
        assert _cfg.RESOLUTION_PRICE_THRESHOLD_PCT == 0.05

    def test_pending_timeout_default(self):
        """2. Default timeout is 360s (P-OP26: 5m timeframe, was 120s)."""
        assert _cfg.PENDING_TRADE_TIMEOUT_SECONDS == 360


# ===========================================================================
# 3-19: Resolver tests
# ===========================================================================

class TestResolverThreshold:

    def test_above_threshold_resolves(self, monkeypatch, tmp_path):
        """3. Price change above threshold resolves the trade."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price moved 0.092% — above 0.05%
        feature = _make_feature(last=1.08600)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1
        assert result["skipped"] == 0

    def test_below_threshold_skipped(self, monkeypatch, tmp_path):
        """4. Price change below threshold is skipped."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price moved 0.009% — below 0.05%
        feature = _make_feature(last=1.08501)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1

    def test_old_hardcoded_001_no_longer_resolves(self, monkeypatch, tmp_path):
        """5. A 0.02% move would have resolved at old 0.01% but not at new 0.05%."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price moved 0.018% — would pass old 0.01%, fails new 0.05%
        feature = _make_feature(last=1.08520)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1


class TestResolverTimeout:

    def test_expired_trade_auto_loss(self, monkeypatch, tmp_path):
        """6. Trade older than timeout is auto-expired as loss."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=7200))
        entry = _make_pending_entry(timestamp=old_ts)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        snapshot = _make_snapshot([])  # No features — doesn't matter, timeout fires first

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1
        assert result["expired"] == 1
        assert result["remaining"] == 0

    def test_expired_trade_has_timeout_mode(self, monkeypatch, tmp_path):
        """7. Expired trade has resolution_mode=timeout_expired."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=7200))
        entry = _make_pending_entry(timestamp=old_ts)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        resolve_pending_paper_trades(_make_snapshot([]))

        ledger = _read_ledger()
        expired_entry = ledger["entries"][0]
        assert expired_entry["resolved"] is True
        assert expired_entry["result"] == "loss"
        assert expired_entry["resolution_mode"] == "timeout_expired"
        assert expired_entry["profit"] < 0
        assert "resolution_age_seconds" in expired_entry

    def test_within_timeout_not_expired(self, monkeypatch, tmp_path):
        """8. Trade within timeout is NOT expired (just skipped if no features)."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        recent_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=600))
        entry = _make_pending_entry(timestamp=recent_ts)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        snapshot = _make_snapshot([])  # No features

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["expired"] == 0
        assert result["remaining"] == 1


class TestResolverDataQuality:

    def test_stale_feature_causes_skip(self, monkeypatch, tmp_path):
        """9. Stale feature data (is_stale=True) causes skip."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        feature = _make_feature(last=1.08700, is_stale=True)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1

    def test_missing_feature_key_causes_skip(self, monkeypatch, tmp_path):
        """10. Missing feature_key (PO bridge down) causes skip."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(feature_key="pocket_option::EURUSD_otc::1m")
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Snapshot has NO matching feature key
        other_feature = _make_feature(key="ibkr::SPY::spot", last=520.0)
        snapshot = _make_snapshot([other_feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1

    def test_price_unavailable_causes_skip(self, monkeypatch, tmp_path):
        """11. price_available=False causes skip."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        feature = _make_feature(last=1.08700, price_available=False)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1


class TestResolverReturnDict:

    def test_return_includes_expired(self, monkeypatch, tmp_path):
        """12. Return dict includes 'expired' count."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        _setup_ledger(monkeypatch, tmp_path, [])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(_make_snapshot([]))
        assert "expired" in result
        assert "resolved" in result
        assert "skipped" in result
        assert "remaining" in result

    def test_return_key_is_resolved_not_resolved_count(self, monkeypatch, tmp_path):
        """13. Return dict key is 'resolved' (not 'resolved_count')."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        _setup_ledger(monkeypatch, tmp_path, [])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(_make_snapshot([]))
        assert "resolved" in result
        assert "resolved_count" not in result


class TestResolverConfigurable:

    def test_threshold_via_monkeypatch(self, monkeypatch, tmp_path):
        """14. Custom threshold: 0.10% requires larger move."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.10)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price moved 0.064% — above default 0.05% but below custom 0.10%
        feature = _make_feature(last=1.08570)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1

    def test_timeout_via_monkeypatch(self, monkeypatch, tmp_path):
        """15. Custom timeout: 600s expires a 900s-old trade."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 600)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=900))
        entry = _make_pending_entry(timestamp=old_ts)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(_make_snapshot([]))
        assert result["expired"] == 1
        assert result["resolved"] == 1


class TestResolverEdgeCases:

    def test_already_resolved_not_reprocessed(self, monkeypatch, tmp_path):
        """16. Already-resolved entries are not re-processed."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(entry_price=1.08500)
        entry["resolved"] = True
        entry["result"] = "win"
        _setup_ledger(monkeypatch, tmp_path, [entry])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(_make_snapshot([]))
        assert result["resolved"] == 0
        assert result["remaining"] == 0

    def test_call_wins_when_price_up(self, monkeypatch, tmp_path):
        """17. direction='call' wins when price goes up."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(direction="call", entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        feature = _make_feature(last=1.08700)  # up 0.184%
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        resolve_pending_paper_trades(snapshot)
        ledger = _read_ledger()
        assert ledger["entries"][0]["result"] == "win"
        assert ledger["entries"][0]["profit"] > 0

    def test_put_wins_when_price_down(self, monkeypatch, tmp_path):
        """18. direction='put' wins when price goes down."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(direction="put", entry_price=1.08500)
        _setup_ledger(monkeypatch, tmp_path, [entry])

        feature = _make_feature(last=1.08300)  # down 0.184%
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        resolve_pending_paper_trades(snapshot)
        ledger = _read_ledger()
        assert ledger["entries"][0]["result"] == "win"
        assert ledger["entries"][0]["profit"] > 0

    def test_missing_direction_skipped(self, monkeypatch, tmp_path):
        """19. Entry with no direction is gracefully skipped."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)

        entry = _make_pending_entry(direction="call", entry_price=1.08500)
        del entry["direction"]
        _setup_ledger(monkeypatch, tmp_path, [entry])

        feature = _make_feature(last=1.08700)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 0
        assert result["skipped"] == 1


# ===========================================================================
# 20: Bug fix test — rebalance_capital_exposure uses correct key
# ===========================================================================

class TestRebalanceBugFix:

    def test_rebalance_reads_resolved_key(self):
        """20. rebalance_capital_exposure reads 'resolved' not 'resolved_count'."""
        import brain_v9.autonomy.action_executor as ae
        import inspect
        source = inspect.getsource(ae.rebalance_capital_exposure)
        # The correct key should be present
        assert '.get("resolved"' in source or ".get('resolved'" in source
        # The wrong dict-key access must NOT be present (local var name is OK)
        assert '.get("resolved_count"' not in source
        assert ".get('resolved_count'" not in source


# ===========================================================================
# 21-25: P-OP34 — Binary expiry minimum reliable threshold tests
# ===========================================================================

class TestBinaryExpiryReliableThreshold:
    """P-OP34: When binary-expiry price change < BINARY_EXPIRY_MIN_RELIABLE_PCT,
    resolve conservatively as loss with resolution_tag='unreliable_margin'.
    """

    def test_config_default(self):
        """21. BINARY_EXPIRY_MIN_RELIABLE_PCT default is 0.001 (P-OP34b)."""
        assert _cfg.BINARY_EXPIRY_MIN_RELIABLE_PCT == 0.001

    def test_tiny_change_resolves_as_loss(self, monkeypatch, tmp_path):
        """22. Binary expiry with change < 0.025% → loss + unreliable_margin tag."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)
        monkeypatch.setattr(_cfg, "BINARY_EXPIRY_MIN_RELIABLE_PCT", 0.025)

        # Trade created 400s ago with 300s duration → age(400) >= duration(300) → binary expiry
        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=400))
        entry = _make_pending_entry(direction="call", entry_price=1.08500, timestamp=old_ts)
        entry["duration_seconds"] = 300
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price change = 0.0092% → below 0.025% threshold
        feature = _make_feature(last=1.08510)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1

        ledger = _read_ledger()
        resolved = ledger["entries"][0]
        assert resolved["result"] == "loss"
        assert resolved["profit"] < 0
        assert resolved["resolution_mode"] == "binary_expiry"
        assert resolved["resolution_tag"] == "unreliable_margin"

    def test_sufficient_change_resolves_directionally(self, monkeypatch, tmp_path):
        """23. Binary expiry with change >= 0.025% → normal directional resolution."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)
        monkeypatch.setattr(_cfg, "BINARY_EXPIRY_MIN_RELIABLE_PCT", 0.025)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=400))
        entry = _make_pending_entry(direction="call", entry_price=1.08500, timestamp=old_ts)
        entry["duration_seconds"] = 300
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price change = 0.184% → well above 0.025% → directional call win
        feature = _make_feature(last=1.08700)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1

        ledger = _read_ledger()
        resolved = ledger["entries"][0]
        assert resolved["result"] == "win"
        assert resolved["profit"] > 0
        assert resolved["resolution_mode"] == "binary_expiry"
        assert resolved["resolution_tag"] == "directional"

    def test_put_unreliable_margin_also_loss(self, monkeypatch, tmp_path):
        """24. PUT with tiny price change also resolves as loss (unreliable_margin)."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)
        monkeypatch.setattr(_cfg, "BINARY_EXPIRY_MIN_RELIABLE_PCT", 0.025)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=400))
        entry = _make_pending_entry(direction="put", entry_price=1.08500, timestamp=old_ts)
        entry["duration_seconds"] = 300
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price down 0.009% → below threshold
        feature = _make_feature(last=1.08490)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1

        ledger = _read_ledger()
        resolved = ledger["entries"][0]
        assert resolved["result"] == "loss"
        assert resolved["resolution_tag"] == "unreliable_margin"

    def test_exact_threshold_resolves_directionally(self, monkeypatch, tmp_path):
        """25. Price change exactly at threshold resolves normally (not unreliable)."""
        monkeypatch.setattr(_cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.05)
        monkeypatch.setattr(_cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 3600)
        monkeypatch.setattr(_cfg, "BINARY_EXPIRY_MIN_RELIABLE_PCT", 0.025)

        old_ts = _utc_iso(datetime.now(timezone.utc) - timedelta(seconds=400))
        entry = _make_pending_entry(direction="call", entry_price=1.00000, timestamp=old_ts)
        entry["duration_seconds"] = 300
        _setup_ledger(monkeypatch, tmp_path, [entry])

        # Price change = exactly 0.025% (1.00000 → 1.00025)
        feature = _make_feature(last=1.00025)
        snapshot = _make_snapshot([feature])

        from brain_v9.trading.paper_execution import resolve_pending_paper_trades, _read_ledger
        result = resolve_pending_paper_trades(snapshot)
        assert result["resolved"] == 1

        ledger = _read_ledger()
        resolved = ledger["entries"][0]
        # At exactly the threshold, should NOT be unreliable_margin
        assert resolved["resolution_tag"] == "directional"
        assert resolved["result"] == "win"  # call + price up
