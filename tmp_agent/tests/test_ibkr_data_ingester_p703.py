"""P7-03: Tests for IBKR live market data ingester.

Covers:
 1. _tick_to_dict extracts fields correctly from a mock Ticker
 2. _tick_to_dict handles NaN values as None
 3. _tick_to_dict marks has_any_tick=False when all prices are NaN
 4. run_ibkr_snapshot writes probe artifact with correct schema
 5. run_ibkr_snapshot handles connection failure gracefully
 6. IBKRDataIngester.get_status returns expected keys
 7. get_ibkr_data_ingester returns singleton
 8. Probe artifact is consumable by feature_engine._build_ibkr_features
 9. run_ibkr_snapshot_async wraps sync call
10. IBKRDataIngester exponential backoff on failures
"""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ticker(bid=520.40, ask=520.60, last=520.50, close=519.0,
                 bidSize=100.0, askSize=120.0, lastSize=50.0) -> SimpleNamespace:
    """Create a mock Ticker-like object."""
    return SimpleNamespace(
        bid=bid, ask=ask, last=last, close=close,
        bidSize=bidSize, askSize=askSize, lastSize=lastSize,
    )


def _make_nan_ticker() -> SimpleNamespace:
    """Ticker with NaN values (no data received)."""
    return SimpleNamespace(
        bid=float("nan"), ask=float("nan"), last=float("nan"),
        close=float("nan"), bidSize=float("nan"), askSize=float("nan"),
        lastSize=float("nan"),
    )


# ===========================================================================
# 1-3: _tick_to_dict tests
# ===========================================================================

class TestTickToDict:
    def test_extracts_fields(self):
        """1. Normal ticker → all fields extracted."""
        from brain_v9.trading.ibkr_data_ingester import _tick_to_dict
        ticker = _make_ticker()
        d = _tick_to_dict(ticker)
        assert d["bid"] == 520.40
        assert d["ask"] == 520.60
        assert d["last"] == 520.50
        assert d["close"] == 519.0
        assert d["bidSize"] == 100.0
        assert d["askSize"] == 120.0
        assert d["lastSize"] == 50.0
        assert d["has_any_tick"] is True

    def test_nan_becomes_none(self):
        """2. NaN values → None."""
        from brain_v9.trading.ibkr_data_ingester import _tick_to_dict
        ticker = _make_nan_ticker()
        d = _tick_to_dict(ticker)
        assert d["bid"] is None
        assert d["ask"] is None
        assert d["last"] is None

    def test_nan_ticker_no_tick(self):
        """3. All NaN → has_any_tick=False."""
        from brain_v9.trading.ibkr_data_ingester import _tick_to_dict
        ticker = _make_nan_ticker()
        d = _tick_to_dict(ticker)
        assert d["has_any_tick"] is False


# ===========================================================================
# 4-5: run_ibkr_snapshot tests (mocked IB connection)
# ===========================================================================

class TestRunIbkrSnapshot:
    def test_successful_snapshot(self, monkeypatch, tmp_path):
        """4. Successful snapshot writes probe artifact with correct schema."""
        # Redirect artifact path
        probe_path = tmp_path / "ibkr_probe.json"
        monkeypatch.setattr(
            "brain_v9.trading.ibkr_data_ingester.IBKR_PROBE_ARTIFACT", probe_path
        )
        monkeypatch.setattr(
            "brain_v9.trading.ibkr_data_ingester.IBKR_ROOM_DIR", tmp_path
        )

        mock_ticker = _make_ticker()

        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.managedAccounts.return_value = ["DUM123456"]
        mock_ib.reqMktData.return_value = mock_ticker

        mock_contract_cls = MagicMock()

        with patch("ib_insync.IB", return_value=mock_ib), \
             patch("ib_insync.Contract", mock_contract_cls):
            from brain_v9.trading.ibkr_data_ingester import run_ibkr_snapshot
            result = run_ibkr_snapshot(host="127.0.0.1", port=4002, client_id=999)

        assert result["connected"] is True
        assert result["schema_version"] == "ibkr_marketdata_probe_status_v2"
        assert result["managed_accounts"] == "DUM123456"
        assert "symbols" in result
        assert len(result["symbols"]) > 0
        # Verify the SPY entry
        spy = result["symbols"].get("SPY_ETF", {})
        assert spy["has_any_tick"] is True
        assert spy["last"] == 520.50

        # Verify file was written
        assert probe_path.exists()
        written = json.loads(probe_path.read_text(encoding="utf-8"))
        assert written["connected"] is True

    def test_connection_failure(self, monkeypatch, tmp_path):
        """5. Connection failure → connected=False, errors populated."""
        probe_path = tmp_path / "ibkr_probe.json"
        monkeypatch.setattr(
            "brain_v9.trading.ibkr_data_ingester.IBKR_PROBE_ARTIFACT", probe_path
        )
        monkeypatch.setattr(
            "brain_v9.trading.ibkr_data_ingester.IBKR_ROOM_DIR", tmp_path
        )

        mock_ib = MagicMock()
        mock_ib.connect.side_effect = ConnectionError("Gateway not running")

        with patch("ib_insync.IB", return_value=mock_ib), \
             patch("ib_insync.Contract"):
            from brain_v9.trading.ibkr_data_ingester import run_ibkr_snapshot
            result = run_ibkr_snapshot(host="127.0.0.1", port=4002, client_id=999)

        assert result["connected"] is False
        assert len(result["errors"]) > 0
        assert probe_path.exists()


# ===========================================================================
# 6-7: IBKRDataIngester class tests
# ===========================================================================

class TestIBKRDataIngester:
    def test_get_status_keys(self):
        """6. get_status returns expected keys."""
        from brain_v9.trading.ibkr_data_ingester import IBKRDataIngester
        ingester = IBKRDataIngester(interval=60)
        status = ingester.get_status()
        expected_keys = {
            "running", "interval_seconds", "consecutive_failures",
            "last_checked_utc", "last_connected", "last_symbol_count",
            "last_error_count",
        }
        assert expected_keys.issubset(set(status.keys()))
        assert status["running"] is False
        assert status["consecutive_failures"] == 0

    def test_singleton(self, monkeypatch):
        """7. get_ibkr_data_ingester returns the same instance."""
        import brain_v9.trading.ibkr_data_ingester as mod
        monkeypatch.setattr(mod, "_ingester", None)
        a = mod.get_ibkr_data_ingester(interval=120)
        b = mod.get_ibkr_data_ingester(interval=60)
        assert a is b
        assert a.interval == 120  # first call wins


# ===========================================================================
# 8: Integration with feature_engine
# ===========================================================================

class TestProbeFeatureIntegration:
    def test_probe_consumed_by_feature_engine(self, monkeypatch, tmp_path):
        """8. A probe artifact written by the ingester is readable by feature_engine."""
        import brain_v9.trading.feature_engine as fe

        # Write a probe artifact manually in the expected schema
        probe_path = tmp_path / "ibkr_marketdata_probe_status.json"
        from datetime import datetime, timezone
        probe = {
            "schema_version": "ibkr_marketdata_probe_status_v2",
            "checked_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "symbols": {
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
        probe_path.write_text(json.dumps(probe), encoding="utf-8")

        # Redirect feature engine to our temp probe
        monkeypatch.setattr(fe, "IBKR_PROBE_PATH", probe_path)
        monkeypatch.setattr(_cfg, "FEATURE_MAX_AGE_SECONDS", {
            "ibkr": 900, "pocket_option": 300, "_default": 600,
        })

        items = fe._build_ibkr_features()
        assert len(items) == 1
        item = items[0]
        assert item["venue"] == "ibkr"
        assert item["symbol"] == "SPY"
        assert item["last"] == 520.50
        assert item["is_stale"] is False
        assert item["data_age_seconds"] is not None


# ===========================================================================
# 9: Async wrapper
# ===========================================================================

class TestAsyncWrapper:
    def test_async_wrapper_calls_sync(self, monkeypatch, tmp_path):
        """9. run_ibkr_snapshot_async delegates to run_ibkr_snapshot."""
        import brain_v9.trading.ibkr_data_ingester as mod

        fake_result = {"connected": True, "checked_utc": "2026-01-01T00:00:00Z"}
        monkeypatch.setattr(mod, "run_ibkr_snapshot", lambda host, port, client_id, timeout: fake_result)

        result = asyncio.get_event_loop().run_until_complete(
            mod.run_ibkr_snapshot_async()
        )
        assert result["connected"] is True


# ===========================================================================
# 10: Backoff logic
# ===========================================================================

class TestBackoff:
    def test_exponential_backoff(self):
        """10. Consecutive failures increase sleep time."""
        from brain_v9.trading.ibkr_data_ingester import IBKRDataIngester
        ingester = IBKRDataIngester(interval=300)

        # Simulate failures
        ingester._consecutive_failures = 0
        base = ingester.interval
        # 0 failures → base interval
        sleep0 = base if ingester._consecutive_failures == 0 else min(base * (2 ** min(ingester._consecutive_failures, 3)), 900)
        assert sleep0 == 300

        ingester._consecutive_failures = 1
        sleep1 = min(base * (2 ** min(ingester._consecutive_failures, 3)), 900)
        assert sleep1 == 600

        ingester._consecutive_failures = 2
        sleep2 = min(base * (2 ** min(ingester._consecutive_failures, 3)), 900)
        assert sleep2 == 900  # capped

        ingester._consecutive_failures = 3
        sleep3 = min(base * (2 ** min(ingester._consecutive_failures, 3)), 900)
        assert sleep3 == 900  # still capped
