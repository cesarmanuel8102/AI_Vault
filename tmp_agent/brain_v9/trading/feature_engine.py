"""
Brain V9 - Feature engine
Construye snapshots de mercado utilizables por el signal engine.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import brain_v9.config as _cfg
from brain_v9.config import (
    STRATEGY_ENGINE_PATH,
    IBKR_PROBE_ARTIFACT, PO_BRIDGE_LATEST_ARTIFACT, PO_FEED_ARTIFACT,
    get_current_session,
)
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.asset_class_layer import classify_symbol

ENGINE_PATH = STRATEGY_ENGINE_PATH

IBKR_PROBE_PATH = IBKR_PROBE_ARTIFACT
PO_BRIDGE_PATH = PO_BRIDGE_LATEST_ARTIFACT
PO_FEED_PATH = PO_FEED_ARTIFACT
log = logging.getLogger("feature_engine")

FEATURE_SNAPSHOT_PATH = ENGINE_PATH / "market_feature_snapshot_latest.json"

# ---------------------------------------------------------------------------
# P-OP33: Candlestick aggregation — convert tick stream to 1-minute OHLC
# candles so that technical indicators operate on meaningful time periods.
# Without this, RSI(14) over 14 ticks (~10s) is noise; with 1m candles,
# RSI(14) analyses 14 minutes of price action — appropriate for a 5m trade.
# ---------------------------------------------------------------------------

_CANDLE_INTERVAL_SECONDS = 60  # 1-minute candles
_CANDLE_BUFFER_MAX = 120       # 120 candles = 2 hours — needed for EMA(100)
_CANDLE_PERSIST_PATH = ENGINE_PATH / "po_candle_buffer.json"
_CANDLE_GAP_THRESHOLD = 900    # P-OP55a: Raised from 300→900 (15 min). OTC markets have natural lulls.
_FROZEN_PRICE_MIN_CANDLES = 10 # P-OP44: if last N candles have zero variance → frozen

# P-OP55a: Path for historical candle data received from the PO bridge
_HISTORY_CANDLES_PATH = _cfg.PO_ROOM_DIR / "po_history_candles_latest.json"
_HISTORY_CANDLES_LOADED_TS: float = 0.0  # Track when we last loaded history


def _candle_alive_ratio(
    highs: list | None, lows: list | None, window: int = 20
) -> float:
    """Return fraction of recent candles with real price movement (H != L).

    P-OP54o: Indicators computed over mostly-frozen candles produce artificial
    extremes.  This metric lets signal_engine gate on data quality.
    Returns 1.0 when no candle data is available (conservative: don't block
    tick-based fallback path).
    """
    if not highs or not lows:
        return 1.0
    n = min(window, len(highs), len(lows))
    if n == 0:
        return 1.0
    tail_h = highs[-n:]
    tail_l = lows[-n:]
    alive = sum(1 for h, l in zip(tail_h, tail_l) if abs(h - l) > 1e-7)
    return alive / n


class _CandleBuffer:
    """Aggregate raw ticks into 1-minute OHLC candles with persistence.

    Each candle: {"t": minute_start_epoch, "o": open, "h": high, "l": low, "c": close, "n": tick_count}

    The buffer survives Brain V9 restarts via JSON persistence.  On each call
    to ``update(rows)`` the ticks are bucketed into 1-minute slots, merged
    with any existing partial candle, and the rolling buffer is trimmed to
    ``_CANDLE_BUFFER_MAX`` completed candles.
    """

    def __init__(self) -> None:
        self._candles: List[Dict[str, Any]] = []  # completed candles (oldest first)
        self._partial: Dict[str, Any] | None = None  # current incomplete candle
        self._symbol: str | None = None  # P-OP45: last processed symbol
        self._loaded = False

    # -- persistence --

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            data = read_json(_CANDLE_PERSIST_PATH, {})
            if isinstance(data, dict):
                saved = data.get("candles", [])
                if isinstance(saved, list):
                    self._candles = saved[-_CANDLE_BUFFER_MAX:]
                partial = data.get("partial")
                if isinstance(partial, dict) and partial.get("t"):
                    self._partial = partial
                # P-OP45: restore last processed symbol
                sym = data.get("symbol")
                if isinstance(sym, str) and sym:
                    self._symbol = sym
        except Exception as exc:
            log.debug("CandleBuffer: load failed: %s", exc)

    def _persist(self) -> None:
        try:
            write_json(_CANDLE_PERSIST_PATH, {
                "candles": self._candles[-_CANDLE_BUFFER_MAX:],
                "partial": self._partial,
                "symbol": self._symbol,  # P-OP45
                "updated_utc": _utc_now(),
            })
        except Exception as exc:
            log.debug("CandleBuffer: persist failed: %s", exc)

    # -- core logic --

    def _minute_bucket(self, ts_iso: str) -> int | None:
        """Parse ISO timestamp → epoch floored to the minute."""
        try:
            text = str(ts_iso).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            epoch = int(dt.timestamp())
            return epoch - (epoch % _CANDLE_INTERVAL_SECONDS)
        except Exception:
            return None

    def update(self, rows: List[Dict[str, Any]], symbol: str = "") -> None:
        """Ingest tick rows and aggregate into candles.

        Each row must have ``price`` (float) and ``captured_utc`` (ISO string).

        Strategy: rebuild candles from the feed rows each call, then merge
        with any existing partial candle, and the rolling buffer is trimmed to
        ``_CANDLE_BUFFER_MAX`` completed candles.
        """
        self._ensure_loaded()
        if not rows:
            return

        # -- P-OP45: Symbol switch detection --
        # If the stream symbol changed (e.g. EURUSD_otc → AEDCNY_otc), the
        # persisted candles belong to the OLD symbol.  Mixing prices from
        # different symbols causes degenerate indicators (RSI=100, ADX=100,
        # absurd BB bandwidth).  Discard all pre-switch data.
        if symbol and self._symbol and symbol != self._symbol:
            log.info(
                "CandleBuffer P-OP45: symbol switch detected (%s → %s), "
                "discarding %d candles from previous symbol",
                self._symbol, symbol, len(self._candles),
            )
            self._candles = []
            self._partial = None
        if symbol:
            self._symbol = symbol

        # -- Step 1: bucket all ticks from the feed into minute candles --
        feed_buckets: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            price = _safe_float(row.get("price"), 0.0)
            if price <= 0:
                continue
            ts = row.get("captured_utc")
            if not ts:
                continue
            bucket = self._minute_bucket(str(ts))
            if bucket is None:
                continue

            if bucket in feed_buckets:
                c = feed_buckets[bucket]
                c["h"] = max(c["h"], price)
                c["l"] = min(c["l"], price)
                c["c"] = price
                c["n"] += 1
            else:
                feed_buckets[bucket] = {
                    "t": bucket, "o": price, "h": price,
                    "l": price, "c": price, "n": 1,
                }

        if not feed_buckets:
            return

        # -- Step 2: separate completed candles from the latest (partial) --
        sorted_ts = sorted(feed_buckets.keys())
        latest_ts = sorted_ts[-1]
        feed_completed = {ts: feed_buckets[ts] for ts in sorted_ts[:-1]}
        feed_partial = feed_buckets[latest_ts]

        # -- Step 3: merge with historical candles --
        # Keep historical candles whose timestamp is NOT in the feed
        # (they've aged out of the 500-row window).
        # P-OP54q: Skip frozen historical candles (H == L) that predate the
        # feed window.  These accumulate when the tick stream was broken and
        # pollute the candle_alive_ratio for hours.  Only discard candles
        # whose timestamp is OLDER than the earliest feed candle — recent
        # single-tick candles (also H==L) are kept because they represent
        # real-time low-activity minutes.
        _feed_min_ts = sorted_ts[0] if sorted_ts else 0
        merged: Dict[int, Dict[str, Any]] = {}
        _discarded_frozen = 0
        for c in self._candles:
            t = c.get("t")
            if t is None:
                continue
            if t in feed_buckets:
                continue  # will be overwritten by feed data
            # Discard frozen candles older than the feed window
            if t < _feed_min_ts and abs(c.get("h", 0) - c.get("l", 0)) < 1e-7:
                _discarded_frozen += 1
                continue
            merged[t] = c
        if _discarded_frozen:
            log.info(
                "CandleBuffer P-OP54q: discarded %d frozen pre-feed candles",
                _discarded_frozen,
            )

        # Add all completed candles from the feed (overwrite any stale history)
        merged.update(feed_completed)

        # Rebuild the candle list sorted by time
        self._candles = [merged[t] for t in sorted(merged.keys())]

        # P-OP43: Detect session gaps and discard pre-gap candles.
        # A gap > _CANDLE_GAP_THRESHOLD (5 min) between consecutive candles
        # means a session break. Indicators computed across the gap produce
        # degenerate values (e.g., ADX spikes from artificial price shock).
        # Keep only candles AFTER the last gap.
        if len(self._candles) >= 2:
            last_gap_idx = -1
            for i in range(len(self._candles) - 1):
                t_curr = self._candles[i].get("t", 0)
                t_next = self._candles[i + 1].get("t", 0)
                if (t_next - t_curr) > _CANDLE_GAP_THRESHOLD:
                    last_gap_idx = i + 1  # discard everything before this index
            if last_gap_idx > 0:
                log.info(
                    "CandleBuffer: session gap detected, discarding %d pre-gap candles (keeping %d)",
                    last_gap_idx, len(self._candles) - last_gap_idx,
                )
                self._candles = self._candles[last_gap_idx:]

        # Trim to max
        if len(self._candles) > _CANDLE_BUFFER_MAX:
            self._candles = self._candles[-_CANDLE_BUFFER_MAX:]

        # The latest bucket is partial (still accumulating ticks)
        self._partial = feed_partial

        self._persist()

    def get_candles(self, count: int = _CANDLE_BUFFER_MAX) -> List[Dict[str, Any]]:
        """Return up to ``count`` completed candles (oldest first)."""
        self._ensure_loaded()
        return list(self._candles[-count:])

    def get_closes(self, count: int = _CANDLE_BUFFER_MAX) -> List[float]:
        """Return close prices from completed candles."""
        return [c["c"] for c in self.get_candles(count)]

    def get_highs(self, count: int = _CANDLE_BUFFER_MAX) -> List[float]:
        """Return high prices from completed candles."""
        return [c["h"] for c in self.get_candles(count)]

    def get_lows(self, count: int = _CANDLE_BUFFER_MAX) -> List[float]:
        """Return low prices from completed candles."""
        return [c["l"] for c in self.get_candles(count)]

    @property
    def candle_count(self) -> int:
        self._ensure_loaded()
        return len(self._candles)

    def seed_from_history(self, candles: List[Dict[str, Any]], symbol: str = "") -> int:
        """Merge historical OHLC candles into the buffer.

        P-OP55a: Called when the bridge receives chart history from PocketOption's
        loadHistoryPeriod WS response.  This seeds the buffer instantly with
        60-120+ candles instead of waiting 15+ minutes of live ticks.

        Returns the number of new candles added.
        """
        self._ensure_loaded()

        # Symbol switch check
        if symbol and self._symbol and symbol != self._symbol:
            log.info(
                "CandleBuffer P-OP55a: history seed symbol mismatch (%s vs %s), "
                "resetting buffer for new symbol",
                self._symbol, symbol,
            )
            self._candles = []
            self._partial = None
        if symbol:
            self._symbol = symbol

        # Build a set of existing timestamps to avoid duplicates
        existing_ts = {c.get("t") for c in self._candles}
        added = 0
        for c in candles:
            t = c.get("t")
            if t is None or t in existing_ts:
                continue
            # Validate the candle has required fields
            if not all(k in c for k in ("o", "h", "l", "c")):
                continue
            self._candles.append({
                "t": int(t),
                "o": float(c["o"]),
                "h": float(c["h"]),
                "l": float(c["l"]),
                "c": float(c["c"]),
                "n": int(c.get("n", 1)),
            })
            existing_ts.add(t)
            added += 1

        if added > 0:
            # Re-sort by timestamp
            self._candles.sort(key=lambda x: x.get("t", 0))
            # Trim to max
            if len(self._candles) > _CANDLE_BUFFER_MAX:
                self._candles = self._candles[-_CANDLE_BUFFER_MAX:]
            self._persist()
            log.info(
                "CandleBuffer P-OP55a: seeded %d historical candles (total now: %d)",
                added, len(self._candles),
            )
        return added


# Module-level singleton — shared across all calls within a Brain cycle.
_po_candle_buffer = _CandleBuffer()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _compute_data_age(captured_utc: Any, venue: str) -> tuple[float | None, bool]:
    """Return (data_age_seconds, is_stale) for a feature item.

    * captured_utc — ISO-8601 timestamp from the data source (may be None)
    * venue — e.g. "ibkr" or "pocket_option", looked up in
      FEATURE_MAX_AGE_SECONDS with "_default" fallback.

    Returns (None, True) when captured_utc is missing/unparseable — missing
    timestamps are treated as stale so the signal engine won't accidentally
    pass data that has no provenance.
    """
    if not captured_utc:
        return None, True
    try:
        text = str(captured_utc).replace("Z", "+00:00")
        captured = datetime.fromisoformat(text)
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - captured).total_seconds()
    except Exception as exc:
        log.debug("Staleness check failed for captured_utc=%r: %s", captured_utc, exc)
        return None, True
    max_age = _cfg.FEATURE_MAX_AGE_SECONDS.get(
        venue,
        _cfg.FEATURE_MAX_AGE_SECONDS.get("_default", 600),
    )
    return round(age, 1), age > max_age


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception as exc:
        log.debug("_safe_float conversion failed for %r: %s", value, exc)
        return default


def _round(value: float, digits: int = 6) -> float:
    return round(_safe_float(value), digits)


def _seconds_to_timeframe(seconds: int) -> str:
    if seconds <= 0:
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 3600 == 0:
        return f"{int(seconds / 3600)}h"
    if seconds % 60 == 0:
        return f"{int(seconds / 60)}m"
    return f"{seconds}s"


def _duration_label_to_seconds(label: Any) -> int | None:
    text = str(label or "").strip().lower()
    if not text:
        return None
    compact = text.replace(" ", "")
    # Handle HH:MM:SS or MM:SS format from PO visible_time_panel
    if ":" in compact:
        parts = compact.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            log.debug("_duration_label_to_seconds: failed to parse colon format: %s", compact)
    if compact.startswith("m") and compact[1:].isdigit():
        return int(compact[1:]) * 60
    for suffixes, multiplier in (
        (("s", "sec", "secs", "second", "seconds"), 1),
        (("m", "min", "mins", "minute", "minutes"), 60),
        (("h", "hr", "hrs", "hour", "hours"), 3600),
    ):
        for suffix in suffixes:
            if compact.endswith(suffix):
                number = compact[: -len(suffix)]
                if number.isdigit():
                    return int(number) * multiplier
    return None


def _spread_pct(bid: float, ask: float, last: float) -> float:
    mid = ((bid + ask) / 2.0) if bid and ask else last
    if mid <= 0:
        return 0.0
    return _round(((ask - bid) / mid) * 100.0, 6)


def _spread_bps(bid: float, ask: float, last: float) -> float:
    mid = ((bid + ask) / 2.0) if bid and ask else last
    if mid <= 0:
        return 0.0
    return _round(((ask - bid) / mid) * 10000.0, 3)


def _imbalance(bid_size: float, ask_size: float) -> float:
    total = bid_size + ask_size
    if total <= 0:
        return 0.0
    return _round((bid_size - ask_size) / total, 4)


def _last_vs_close_pct(last: float, close: float) -> float:
    if close <= 0:
        return 0.0
    return _round(((last - close) / close) * 100.0, 4)


def _infer_market_regime(last_vs_close_pct: float, spread_pct: float, price_available: bool) -> str:
    """Classify market regime based on price movement from previous close.

    FIX v2 (2026-03-30): Now direction-aware at ALL levels.
    "trend_strong" split into "trend_strong_up"/"trend_strong_down".
    "trend_mild" split into "trend_up"/"trend_down_mild".
    "range_break_down" reserved for >= 1.0% negative moves only.
    """
    if not price_available:
        return "unknown"
    magnitude = abs(last_vs_close_pct)
    if spread_pct > 0.25:
        return "dislocated"
    # Large move: genuine trend day — direction matters
    if magnitude >= 1.5:
        return "trend_strong_up" if last_vs_close_pct > 0 else "trend_strong_down"
    if magnitude >= 1.0:
        return "trend_up" if last_vs_close_pct > 0 else "range_break_down"
    # Moderate move: directional but not extreme
    if magnitude >= 0.35:
        return "trend_up" if last_vs_close_pct > 0 else "trend_down_mild"
    if magnitude <= 0.1:
        return "range"
    return "mild"


def _ibkr_symbol_map(label: str) -> str:
    if label == "SPY_ETF":
        return "SPY"
    if label == "AAPL_STK":
        return "AAPL"
    if label.startswith("AAPL_OPT"):
        return "AAPL_20260417_200C"
    if label == "EURUSD_FX":
        return "EURUSD"
    if label == "BTCUSD_CRYPTO":
        return "BTCUSD"
    return label


def _build_ibkr_features() -> List[Dict[str, Any]]:
    probe = read_json(IBKR_PROBE_PATH, {})
    symbols = probe.get("symbols", {}) if isinstance(probe, dict) else {}
    items: List[Dict[str, Any]] = []
    checked_utc = probe.get("checked_utc")
    for label, row in symbols.items():
        if not isinstance(row, dict):
            continue
        last = _safe_float(row.get("last"))
        bid = _safe_float(row.get("bid"))
        ask = _safe_float(row.get("ask"))
        close = _safe_float(row.get("close"))
        bid_size = _safe_float(row.get("bidSize"))
        ask_size = _safe_float(row.get("askSize"))
        price_available = bool(row.get("has_any_tick")) and last > 0
        symbol = _ibkr_symbol_map(label)
        spread_pct = _spread_pct(bid, ask, last)
        data_age_seconds, is_stale = _compute_data_age(checked_utc, "ibkr")
        items.append({
            "key": f"ibkr::{symbol}::spot",
            "captured_utc": checked_utc,
            "data_age_seconds": data_age_seconds,
            "is_stale": is_stale,
            "venue": "ibkr",
            "symbol": symbol,
            "timeframe": "spot",
            "asset_class": classify_symbol(symbol, "ibkr"),
            "price_available": price_available,
            "last": _round(last, 4),
            "bid": _round(bid, 4),
            "ask": _round(ask, 4),
            "close": _round(close, 4),
            "mid": _round(((bid + ask) / 2.0) if bid and ask else last, 4),
            "spread_pct": spread_pct,
            "spread_bps": _spread_bps(bid, ask, last),
            "bid_ask_imbalance": _imbalance(bid_size, ask_size),
            "last_vs_close_pct": _last_vs_close_pct(last, close),
            "volatility_proxy_pct": _round(abs(_last_vs_close_pct(last, close)), 4),
            "liquidity_score": _round(1.0 if ask > 0 and bid > 0 and spread_pct <= 0.05 else 0.65 if spread_pct <= 0.25 else 0.25, 4),
            "market_regime": _infer_market_regime(_last_vs_close_pct(last, close), spread_pct, price_available),
            "source_artifact": str(IBKR_PROBE_PATH),
        })
    return items


def _latest_price_from_po_feed(symbol: str) -> float | None:
    feed = read_json(PO_FEED_PATH, {})
    rows = feed.get("rows", []) if isinstance(feed, dict) else []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        if row.get("symbol") != symbol:
            continue
        price = row.get("price")
        if price is None:
            continue
        value = _safe_float(price, 0.0)
        if value > 0:
            return value
    return None


def _po_recent_rows(symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
    feed = read_json(PO_FEED_PATH, {})
    rows = feed.get("rows", []) if isinstance(feed, dict) else []
    matched: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("symbol") != symbol:
            continue
        price = _safe_float(row.get("price"), 0.0)
        if price <= 0:
            continue
        if row.get("stream_symbol_match") is False:
            continue
        matched.append(row)
    return matched[-limit:]


def _compute_rsi(prices: List[float], period: int = 14) -> float:
    """Compute RSI from a price series. Returns 50.0 if insufficient data."""
    if len(prices) < period + 1:
        return 50.0
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_bollinger(prices: List[float], period: int = 20, num_std: float = 2.0) -> Dict[str, float]:
    """Compute Bollinger Bands. Returns mid, upper, lower, pct_b, bandwidth."""
    if len(prices) < period:
        return {"bb_mid": 0.0, "bb_upper": 0.0, "bb_lower": 0.0, "bb_pct_b": 0.5, "bb_bandwidth": 0.0}
    window = prices[-period:]
    mid = sum(window) / period
    variance = sum((p - mid) ** 2 for p in window) / period
    std = math.sqrt(max(variance, 0.0))
    upper = mid + num_std * std
    lower = mid - num_std * std
    band_width = upper - lower
    pct_b = ((prices[-1] - lower) / band_width) if band_width > 0 else 0.5
    bandwidth_pct = (band_width / mid * 100.0) if mid > 0 else 0.0
    return {
        "bb_mid": _round(mid, 5),
        "bb_upper": _round(upper, 5),
        "bb_lower": _round(lower, 5),
        "bb_pct_b": _round(pct_b, 4),
        "bb_bandwidth": _round(bandwidth_pct, 4),
    }


def _compute_stochastic(prices: List[float], k_period: int = 14, d_period: int = 3,
                         highs: List[float] | None = None, lows: List[float] | None = None) -> Dict[str, float]:
    """Compute Stochastic %K and %D.

    When ``highs`` and ``lows`` are provided (OHLC candle data), uses true
    high/low for each period window — matching Lane's original design.
    When only ``prices`` (closes) are provided, falls back to using close
    prices for high/low estimation (legacy tick-based behaviour).
    """
    if len(prices) < k_period:
        return {"stoch_k": 50.0, "stoch_d": 50.0}
    _highs = highs if highs and len(highs) == len(prices) else prices
    _lows = lows if lows and len(lows) == len(prices) else prices
    # Compute raw %K values for enough points to smooth into %D
    raw_k_values: List[float] = []
    for i in range(k_period - 1, len(prices)):
        window_high = max(_highs[i - k_period + 1: i + 1])
        window_low = min(_lows[i - k_period + 1: i + 1])
        diff = window_high - window_low
        k_val = ((prices[i] - window_low) / diff * 100.0) if diff > 0 else 50.0
        raw_k_values.append(k_val)
    k = raw_k_values[-1] if raw_k_values else 50.0
    d = (sum(raw_k_values[-d_period:]) / min(d_period, len(raw_k_values))) if raw_k_values else 50.0
    return {"stoch_k": _round(k, 2), "stoch_d": _round(d, 2)}


def _compute_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
    """Compute MACD line, signal line, and histogram."""
    if len(prices) < slow + signal:
        return {"macd_line": 0.0, "macd_signal": 0.0, "macd_histogram": 0.0}

    def _ema(data: List[float], period: int) -> List[float]:
        multiplier = 2.0 / (period + 1)
        result = [sum(data[:period]) / period]
        for i in range(period, len(data)):
            result.append((data[i] - result[-1]) * multiplier + result[-1])
        return result

    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    # Align: ema_fast starts at index fast-1, ema_slow at slow-1
    offset = slow - fast
    macd_line_series = [ema_fast[i + offset] - ema_slow[i] for i in range(len(ema_slow))]
    if len(macd_line_series) < signal:
        return {"macd_line": macd_line_series[-1] if macd_line_series else 0.0, "macd_signal": 0.0, "macd_histogram": 0.0}
    signal_line_series = _ema(macd_line_series, signal)
    macd_val = macd_line_series[-1]
    signal_val = signal_line_series[-1]
    histogram = macd_val - signal_val
    return {
        "macd_line": _round(macd_val, 6),
        "macd_signal": _round(signal_val, 6),
        "macd_histogram": _round(histogram, 6),
    }


def _compute_ema(prices: List[float], period: int = 100) -> float:
    """Compute Exponential Moving Average for the last price.

    P-OP35b: EMA used as macro trend filter.  Returns 0.0 when there
    are fewer than *period* data points (not enough history)."""
    if len(prices) < period:
        return 0.0
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for i in range(period, len(prices)):
        ema = (prices[i] - ema) * multiplier + ema
    return ema


def _compute_adx(highs: List[float], lows: List[float], closes: List[float],
                 period: int = 10) -> Dict[str, float]:
    """Compute ADX, +DI, -DI using Wilder's smoothing.

    P-OP36a: ADX as quantitative regime filter.
    - ADX < 20  → range (good for mean reversion)
    - ADX 20-25 → transition (caution)
    - ADX > 25  → trend (avoid reversion)
    +DI > -DI → bullish pressure, -DI > +DI → bearish pressure.

    Returns {"adx": float, "plus_di": float, "minus_di": float}.
    All values in [0, 100].  Returns zeros when insufficient data.
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}

    # Step 1: True Range, +DM, -DM
    tr_list: List[float] = []
    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []
    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]
        plus_dm = max(high_diff, 0.0) if high_diff > low_diff else 0.0
        minus_dm = max(low_diff, 0.0) if low_diff > high_diff else 0.0
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(tr_list) < period:
        return {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}

    # Step 2: Wilder smoothing of TR, +DM, -DM (first value = SMA)
    smoothed_tr = sum(tr_list[:period])
    smoothed_plus_dm = sum(plus_dm_list[:period])
    smoothed_minus_dm = sum(minus_dm_list[:period])

    dx_list: List[float] = []
    # First DI values
    plus_di = (smoothed_plus_dm / smoothed_tr * 100.0) if smoothed_tr > 0 else 0.0
    minus_di = (smoothed_minus_dm / smoothed_tr * 100.0) if smoothed_tr > 0 else 0.0
    di_sum = plus_di + minus_di
    dx_list.append(abs(plus_di - minus_di) / di_sum * 100.0 if di_sum > 0 else 0.0)

    for i in range(period, len(tr_list)):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr_list[i]
        smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm_list[i]
        smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm_list[i]
        plus_di = (smoothed_plus_dm / smoothed_tr * 100.0) if smoothed_tr > 0 else 0.0
        minus_di = (smoothed_minus_dm / smoothed_tr * 100.0) if smoothed_tr > 0 else 0.0
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100.0 if di_sum > 0 else 0.0
        dx_list.append(dx)

    # Step 3: Smooth DX into ADX (Wilder smoothing again)
    if len(dx_list) < period:
        return {"adx": 0.0, "plus_di": _round(plus_di, 2), "minus_di": _round(minus_di, 2)}

    adx = sum(dx_list[:period]) / period
    for i in range(period, len(dx_list)):
        adx = (adx * (period - 1) + dx_list[i]) / period

    return {
        "adx": _round(adx, 2),
        "plus_di": _round(plus_di, 2),
        "minus_di": _round(minus_di, 2),
    }


def _po_price_context(symbol: str) -> Dict[str, Any]:
    rows = _po_recent_rows(symbol)
    prices = [_safe_float(row.get("price"), 0.0) for row in rows if _safe_float(row.get("price"), 0.0) > 0]
    empty_indicators = {
        "rsi_14": 50.0, "bb_mid": 0.0, "bb_upper": 0.0, "bb_lower": 0.0,
        "bb_pct_b": 0.5, "bb_bandwidth": 0.0,
        "stoch_k": 50.0, "stoch_d": 50.0,
        "macd_line": 0.0, "macd_signal": 0.0, "macd_histogram": 0.0,
        "indicator_confluence": 0,
        "ema_50": 0.0,             # P-OP36b (was ema_100)
        "ema_50_trend": "unknown", # P-OP36b (was ema_100_trend)
        "adx": 0.0,               # P-OP36a
        "plus_di": 0.0,           # P-OP36a
        "minus_di": 0.0,          # P-OP36a
        "candle_count": 0,
    }
    if len(prices) < 5:
        return {
            "rows_count": len(prices),
            "price_available": False,
            "last": None,
            "window_open": None,
            "window_change_pct": 0.0,
            "window_range_pct": 0.0,
            "volatility_proxy_pct": 0.0,
            "price_zscore": 0.0,
            "recent_micro_move_pct": 0.0,
            "market_regime": "unknown",
            **empty_indicators,
        }

    last = prices[-1]
    window = prices[-20:] if len(prices) >= 20 else prices
    window_open = window[0]
    window_mean = sum(window) / len(window)
    variance = sum((price - window_mean) ** 2 for price in window) / len(window)
    std_dev = math.sqrt(max(variance, 0.0))
    window_change_pct = ((last - window_open) / window_open) * 100.0 if window_open > 0 else 0.0
    window_high = max(window)
    window_low = min(window)
    window_range_pct = ((window_high - window_low) / window_mean) * 100.0 if window_mean > 0 else 0.0
    micro_ref = window[-5] if len(window) >= 5 else window[0]
    recent_micro_move_pct = ((last - micro_ref) / micro_ref) * 100.0 if micro_ref > 0 else 0.0
    price_zscore = ((last - window_mean) / std_dev) if std_dev > 0 else 0.0

    regime = "range"
    abs_change = abs(window_change_pct)
    abs_zscore = abs(price_zscore)
    # trend_strong: large directional move with statistical significance
    if abs_change >= 0.15 and abs_zscore >= 1.8:
        regime = "trend_strong"
    # trend_mild / range_break_down: moderate move OR statistically significant
    elif abs_change >= 0.06 or abs_zscore >= 1.2:
        regime = "trend_mild" if window_change_pct > 0 else "range_break_down"
    elif window_range_pct >= 0.10:
        regime = "mild"

    # P-OP33: Aggregate ticks into 1-minute OHLC candles, then compute
    # indicators on candle closes/highs/lows.  This ensures RSI(14) analyses
    # 14 minutes (not 14 ticks = ~10 seconds) — appropriate for 5m trades.
    # Feed the full row set (with timestamps) to the candle buffer.

    # P-OP55a: Seed from historical candle data if available from bridge.
    # The bridge receives chart history from PocketOption's loadHistoryPeriod
    # WS response and saves it.  We load it once (or when it changes).
    global _HISTORY_CANDLES_LOADED_TS
    try:
        if _HISTORY_CANDLES_PATH.exists():
            _hist_mtime = _HISTORY_CANDLES_PATH.stat().st_mtime
            if _hist_mtime > _HISTORY_CANDLES_LOADED_TS:
                _hist_data = read_json(_HISTORY_CANDLES_PATH, {})
                _hist_candles = _hist_data.get("candles", [])
                _hist_symbol = _hist_data.get("symbol", "")
                if _hist_candles and isinstance(_hist_candles, list):
                    _added = _po_candle_buffer.seed_from_history(
                        _hist_candles, symbol=_hist_symbol
                    )
                    if _added > 0:
                        log.info(
                            "P-OP55a: Loaded %d historical candles from bridge for %s",
                            _added, _hist_symbol,
                        )
                _HISTORY_CANDLES_LOADED_TS = _hist_mtime
    except Exception as exc:
        log.debug("P-OP55a: Failed to load history candles: %s", exc)

    _po_candle_buffer.update(rows, symbol=symbol)
    candles = _po_candle_buffer.get_candles()
    candle_closes = _po_candle_buffer.get_closes()
    candle_highs = _po_candle_buffer.get_highs()
    candle_lows = _po_candle_buffer.get_lows()
    n_candles = len(candle_closes)

    # Minimum candles for indicator quality:
    # RSI(14) needs 15, BB(20) needs 20, MACD(12,26,9) needs 35, Stoch(14) needs 14.
    # With < 15 candles, fall back to tick-based (better than nothing at startup).
    _MIN_CANDLES_FOR_INDICATORS = 15
    use_candles = n_candles >= _MIN_CANDLES_FOR_INDICATORS

    # P-OP44: Frozen-price detection.
    # If the last _FROZEN_PRICE_MIN_CANDLES candle closes are identical
    # (zero variance), the feed is frozen/stale.  Indicators computed on
    # constant-price data are mathematically degenerate (BB width=0, ADX→100,
    # RSI→0 or 100).  Return empty indicators with a frozen flag so the
    # signal engine knows not to trust these features.
    _frozen = False
    if use_candles:
        _tail = candle_closes[-_FROZEN_PRICE_MIN_CANDLES:]
        if len(_tail) >= _FROZEN_PRICE_MIN_CANDLES:
            _tail_set = set(round(p, 6) for p in _tail)
            if len(_tail_set) <= 1:
                _frozen = True
                log.info(
                    "P-OP44: Frozen price detected — last %d candles all %.5f. "
                    "Returning empty indicators.",
                    _FROZEN_PRICE_MIN_CANDLES, _tail[0],
                )

    # Also check raw tick window: if the last 20 prices have zero range,
    # the feed is clearly frozen even if candle count is low.
    # P-OP52d: Only apply the tick-window frozen check when we are NOT
    # using candles for indicator computation. When use_candles=True,
    # indicators are derived from candle closes (which may have variation
    # even when recent ticks are flat). OTC markets frequently produce
    # repeated ticks at the same price for 30-60 seconds between moves;
    # this is normal behaviour, not a frozen feed.
    if not _frozen and not use_candles and window_range_pct == 0.0 and len(window) >= 15:
        _frozen = True
        log.info("P-OP44: Frozen price detected via tick window (range_pct=0).")

    if _frozen:
        return {
            "rows_count": len(prices),
            "price_available": True,
            "price_frozen": True,
            "last": _round(last, 5),
            "window_open": _round(window_open, 5),
            "window_change_pct": 0.0,
            "window_range_pct": 0.0,
            "volatility_proxy_pct": 0.0,
            "price_zscore": 0.0,
            "recent_micro_move_pct": 0.0,
            "market_regime": "frozen",
            **empty_indicators,
            "candle_count": n_candles,
        }

    if use_candles:
        ind_prices = candle_closes
        ind_highs = candle_highs
        ind_lows = candle_lows
    else:
        ind_prices = prices
        ind_highs = None
        ind_lows = None

    # P-OP9: Compute technical indicators
    rsi = _compute_rsi(ind_prices, 14)
    bb = _compute_bollinger(ind_prices, 20, 2.5)  # P-OP35a: 2.0→2.5 to match PO chart & reduce false extremes
    stoch = _compute_stochastic(ind_prices, 14, 3, highs=ind_highs, lows=ind_lows)
    macd = _compute_macd(ind_prices, 12, 26, 9)

    # P-OP36b: EMA 50 — macro trend filter (was EMA 100 in P-OP35b).
    # On M1 candles, EMA 50 = 50 minutes — more reactive for 5m binary trades.
    # When price > EMA50 → uptrend, price < EMA50 → downtrend.
    ema_50 = _compute_ema(ind_prices, 50)
    if ema_50 > 0 and last > 0:
        ema_50_trend = "bullish" if last > ema_50 else "bearish"
    else:
        ema_50_trend = "unknown"  # not enough data for EMA 50

    # P-OP36a: ADX (10,10) + DI — quantitative regime filter.
    # Requires candle highs/lows. Falls back to zeros when unavailable.
    adx_result = _compute_adx(
        ind_highs or [], ind_lows or [], ind_prices, period=10
    ) if ind_highs and ind_lows else {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}

    # P-OP9: Indicator confluence — count how many indicators agree on direction.
    # Positive = bullish (call), negative = bearish (put).
    # Each indicator contributes +1 (bullish) or -1 (bearish) or 0 (neutral).
    # P-OP32o: Aligned thresholds with signal_engine mild zones so that
    # confluence (which drives direction) triggers in the same range that
    # the signal engine considers "extreme enough" for setup strength.
    confluence = 0
    # RSI: oversold (<35) = bullish bounce expected, overbought (>65) = bearish
    # P-OP35d: aligned with config mild thresholds 35/65 (was 38/62)
    if rsi < 35:
        confluence += 1
    elif rsi > 65:
        confluence -= 1
    # Bollinger %B: below 0.15 = bullish reversion, above 0.85 = bearish reversion
    if bb["bb_pct_b"] < 0.15:
        confluence += 1
    elif bb["bb_pct_b"] > 0.85:
        confluence -= 1
    # Stochastic: oversold (<30) = bullish, overbought (>70) = bearish
    if stoch["stoch_k"] < 30:
        confluence += 1
    elif stoch["stoch_k"] > 70:
        confluence -= 1
    # MACD histogram: positive = bullish momentum, negative = bearish
    if macd["macd_histogram"] > 0:
        confluence += 1
    elif macd["macd_histogram"] < 0:
        confluence -= 1

    return {
        "rows_count": len(prices),
        "price_available": True,
        "last": _round(last, 5),
        "window_open": _round(window_open, 5),
        "window_change_pct": _round(window_change_pct, 4),
        "window_range_pct": _round(window_range_pct, 4),
        "volatility_proxy_pct": _round(window_range_pct, 4),
        "price_zscore": _round(price_zscore, 4),
        "recent_micro_move_pct": _round(recent_micro_move_pct, 4),
        "market_regime": regime,
        # P-OP9: Computed indicators (now from candles when available)
        "rsi_14": _round(rsi, 2),
        **bb,
        **stoch,
        **macd,
        "indicator_confluence": confluence,
        # P-OP36b: EMA 50 macro trend filter (was EMA 100)
        "ema_50": _round(ema_50, 5),
        "ema_50_trend": ema_50_trend,
        # P-OP36a: ADX regime filter + directional indicators
        **adx_result,
        # P-OP33: candle metadata
        "candle_count": n_candles,
        # P-OP54o: Candle alive ratio — proportion of recent candles with real
        # price movement (range > 0).  Indicators computed on mostly-frozen
        # candles produce artificial extremes (e.g. RSI 86 from 1 real candle
        # after 13 flat ones).  Exposed so signal_engine can gate on quality.
        "candle_alive_ratio": _candle_alive_ratio(candle_highs, candle_lows, window=20),
    }


def _build_pocket_option_features() -> List[Dict[str, Any]]:
    bridge = read_json(PO_BRIDGE_PATH, {})
    current = bridge.get("current", {}) if isinstance(bridge.get("current"), dict) else {}
    dom = bridge.get("dom", {}) if isinstance(bridge.get("dom"), dict) else {}
    ws = bridge.get("ws", {}) if isinstance(bridge.get("ws"), dict) else {}
    symbol = current.get("symbol")
    if not symbol:
        return []
    price_context = _po_price_context(symbol)
    price = price_context.get("last")
    if price is None:
        price = _latest_price_from_po_feed(symbol)
    price_available = bool(price_context.get("price_available")) or (price is not None and price > 0)
    payout_pct = _safe_float(current.get("payout_pct"))
    # P-OP42: Fix wrong payout from DOM scraper — extract real payout from pair_candidates
    # The browser extension sometimes scrapes a timer/progress element instead of the actual payout.
    # pair_candidates[].context contains the real payout as "+NN%" strings.
    if payout_pct < 50:
        pair_candidates = dom.get("pair_candidates") if isinstance(dom.get("pair_candidates"), list) else []
        _real_payouts = []
        for pc in pair_candidates:
            if isinstance(pc, dict):
                ctx = str(pc.get("context", ""))
                if "%" in ctx:
                    # Extract number before % (e.g. "+92%" -> 92)
                    _num_str = ctx.replace("+", "").replace("%", "").strip()
                    try:
                        _val = float(_num_str)
                        if 50 <= _val <= 100:
                            _real_payouts.append(_val)
                    except (ValueError, TypeError):
                        pass
        if _real_payouts:
            _old_payout = payout_pct
            payout_pct = max(_real_payouts)
            log.info(
                "P-OP42: Corrected payout_pct from DOM scraper: %.0f -> %.0f (from pair_candidates)",
                _old_payout, payout_pct
            )
    current_seconds = int(_safe_float(current.get("expiry_seconds"), 0))
    duration_candidates = dom.get("duration_candidates") if isinstance(dom.get("duration_candidates"), list) else []
    indicator_candidates = dom.get("indicator_candidates") if isinstance(dom.get("indicator_candidates"), list) else []
    indicator_readouts = dom.get("indicator_readouts") if isinstance(dom.get("indicator_readouts"), list) else []
    stream_symbol_match = ws.get("stream_symbol_match")
    last_stream_symbol = ws.get("last_stream_symbol")
    visible_symbol = ws.get("visible_symbol") or symbol
    available_seconds = []
    for item in duration_candidates:
        if isinstance(item, dict):
            seconds = _duration_label_to_seconds(item.get("label"))
        else:
            seconds = _duration_label_to_seconds(item)
        if seconds and seconds not in available_seconds:
            available_seconds.append(seconds)
    if current_seconds > 0 and current_seconds not in available_seconds:
        available_seconds.insert(0, current_seconds)
    if not available_seconds:
        available_seconds = [60]
    available_timeframes = [_seconds_to_timeframe(seconds) for seconds in available_seconds]

    items: List[Dict[str, Any]] = []
    captured_utc_po = bridge.get("captured_utc")
    data_age_seconds, is_stale = _compute_data_age(captured_utc_po, "pocket_option")
    # P-OP22: session awareness — derive hour and session from current UTC time
    _now = datetime.now(timezone.utc)
    _hour_utc = _now.hour
    _session_info = get_current_session(_hour_utc)
    for seconds in available_seconds:
        timeframe = _seconds_to_timeframe(seconds)
        items.append({
            "key": f"pocket_option::{symbol}::{timeframe}",
            "captured_utc": captured_utc_po,
            "data_age_seconds": data_age_seconds,
            "is_stale": is_stale,
            # P-OP22: session awareness fields
            "hour_utc": _hour_utc,
            "session_name": _session_info["session_name"],
            "session_quality": _session_info["quality"],
            "venue": "pocket_option",
            "symbol": symbol,
            "timeframe": timeframe,
            "asset_class": classify_symbol(symbol, "pocket_option"),
            "price_available": price_available,
            "price_frozen": bool(price_context.get("price_frozen")),  # P-OP44
            "candle_alive_ratio": price_context.get("candle_alive_ratio", 1.0),  # P-OP54o
            "last": _round(price, 5) if price_available else None,
            "bid": None,
            "ask": None,
            "close": price_context.get("window_open"),
            "mid": _round(price, 5) if price_available else None,
            "spread_pct": 0.0,
            "spread_bps": 0.0,
            "bid_ask_imbalance": 0.0,
            "last_vs_close_pct": price_context.get("window_change_pct", 0.0),
            "volatility_proxy_pct": price_context.get("volatility_proxy_pct", 0.0),
            "window_range_pct": price_context.get("window_range_pct", 0.0),
            "price_zscore": price_context.get("price_zscore", 0.0),
            "recent_micro_move_pct": price_context.get("recent_micro_move_pct", 0.0),
            "price_rows_count": price_context.get("rows_count", 0),
            "candle_count": price_context.get("candle_count", 0),
            # P-OP9: Computed technical indicators
            "rsi_14": price_context.get("rsi_14", 50.0),
            "bb_mid": price_context.get("bb_mid", 0.0),
            "bb_upper": price_context.get("bb_upper", 0.0),
            "bb_lower": price_context.get("bb_lower", 0.0),
            "bb_pct_b": price_context.get("bb_pct_b", 0.5),
            "bb_bandwidth": price_context.get("bb_bandwidth", 0.0),
            "stoch_k": price_context.get("stoch_k", 50.0),
            "stoch_d": price_context.get("stoch_d", 50.0),
            "macd_line": price_context.get("macd_line", 0.0),
            "macd_signal": price_context.get("macd_signal", 0.0),
            "macd_histogram": price_context.get("macd_histogram", 0.0),
            "indicator_confluence": price_context.get("indicator_confluence", 0),
            # P-OP36b: EMA 50 macro trend filter (was EMA 100)
            "ema_50": price_context.get("ema_50", 0.0),
            "ema_50_trend": price_context.get("ema_50_trend", "unknown"),
            # P-OP36a: ADX regime filter + directional indicators
            "adx": price_context.get("adx", 0.0),
            "plus_di": price_context.get("plus_di", 0.0),
            "minus_di": price_context.get("minus_di", 0.0),
            "window_change_pct": price_context.get("window_change_pct", 0.0),
            "liquidity_score": _round(min(max(payout_pct / 100.0, 0.0), 1.0), 4),
            "market_regime": price_context.get("market_regime", "unknown" if not price_available else "range"),
            "payout_pct": payout_pct,
            "expiry_seconds": seconds,
            "is_current_duration": seconds == current_seconds,
            "available_timeframes": available_timeframes,
            "duration_candidates": duration_candidates[:20],
            "indicator_candidates": indicator_candidates[:30],
            "indicator_readouts": indicator_readouts[:20],
            "indicator_count": len(indicator_candidates),
            "indicator_readout_count": len(indicator_readouts),
            "indicator_access_ready": len(indicator_candidates) > 0,
            "visible_symbol": visible_symbol,
            "last_stream_symbol": last_stream_symbol,
            "stream_symbol_match": stream_symbol_match,
            "source_artifact": str(PO_BRIDGE_PATH),
        })
    return items


def build_market_feature_snapshot() -> Dict[str, Any]:
    ibkr_items = _build_ibkr_features()
    po_items = _build_pocket_option_features()
    items = ibkr_items + po_items
    snapshot = {
        "schema_version": "market_feature_snapshot_v1",
        "generated_utc": _utc_now(),
        "items": items,
        "summary": {
            "items_count": len(items),
            "venues": sorted({item["venue"] for item in items}),
            "symbols_count": len({item["symbol"] for item in items}),
            "price_ready_count": sum(1 for item in items if item.get("price_available")),
            "indicator_ready_count": sum(1 for item in items if item.get("indicator_access_ready")),
            "timeframes_count": len({f"{item['venue']}::{item['timeframe']}" for item in items}),
            "unpriced_symbols": sorted({item["symbol"] for item in items if not item.get("price_available")}),
            "stale_count": sum(1 for item in items if item.get("is_stale")),
            "fresh_count": sum(1 for item in items if not item.get("is_stale")),
        },
        "sources": {
            "ibkr_probe_path": str(IBKR_PROBE_PATH),
            "pocket_option_bridge_path": str(PO_BRIDGE_PATH),
            "pocket_option_feed_path": str(PO_FEED_PATH),
        },
    }
    write_json(FEATURE_SNAPSHOT_PATH, snapshot)
    return snapshot


def read_market_feature_snapshot() -> Dict[str, Any]:
    return read_json(FEATURE_SNAPSHOT_PATH, {
        "schema_version": "market_feature_snapshot_v1",
        "generated_utc": None,
        "items": [],
        "summary": {},
    })
