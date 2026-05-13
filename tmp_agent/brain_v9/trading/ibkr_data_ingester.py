"""
Brain V9 — trading/ibkr_data_ingester.py
P7-03: Real-time market data ingestion from IBKR via ib_insync.

Connects to IB Gateway, requests market-data snapshots for a watchlist,
and writes the probe artifact that feature_engine.py already consumes.

Usage patterns:
  - run_ibkr_snapshot() — one-shot: connect, snapshot, disconnect.
  - IBKRDataIngester — persistent background task for the autonomy manager.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain_v9.config import (
    IBKR_HOST,
    IBKR_PORT,
    IBKR_PROBE_ARTIFACT,
    IBKR_ROOM_DIR,
)
from brain_v9.core.state_io import write_json

log = logging.getLogger("ibkr_data_ingester")


# ── Watchlist ─────────────────────────────────────────────────────────────────
# Each entry: (label, ib_insync Contract kwargs)
# Labels must match the convention in feature_engine._ibkr_symbol_map.

_WATCHLIST: List[Dict[str, Any]] = [
    {
        "label": "SPY_ETF",
        "contract": {"symbol": "SPY", "secType": "STK", "exchange": "SMART", "currency": "USD"},
    },
    {
        "label": "AAPL_STK",
        "contract": {"symbol": "AAPL", "secType": "STK", "exchange": "SMART", "currency": "USD"},
    },
    {
        "label": "AAPL_OPT_20260417_200C",
        "contract": {
            "symbol": "AAPL",
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "lastTradeDateOrContractMonth": "20260417",
            "strike": 200.0,
            "right": "C",
        },
    },
    {
        "label": "EURUSD_FX",
        "contract": {"symbol": "EUR", "secType": "CASH", "exchange": "IDEALPRO", "currency": "USD"},
    },
    # BTCUSD_CRYPTO removed — PAXOS crypto not available on paper accounts,
    # always returns error 200 "No security definition". Wastes 2s per cycle.
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tick_to_dict(ticker: Any) -> Dict[str, Any]:
    """Extract numeric fields from an ib_insync Ticker into a flat dict."""
    def _val(v: Any) -> Any:
        """Return None for NaN / unset values, else the raw value."""
        if v is None:
            return None
        try:
            import math
            if isinstance(v, float) and math.isnan(v):
                return None
        except Exception as exc:
            log.debug("_val check failed for %r: %s", v, exc)
        return v

    return {
        "bid": _val(ticker.bid),
        "ask": _val(ticker.ask),
        "last": _val(ticker.last),
        "close": _val(ticker.close),
        "bidSize": _val(ticker.bidSize),
        "askSize": _val(ticker.askSize),
        "lastSize": _val(ticker.lastSize),
        "has_any_tick": any(
            _val(getattr(ticker, f, None)) is not None
            for f in ("bid", "ask", "last")
        ),
    }


# ── One-shot snapshot ─────────────────────────────────────────────────────────

# Client ID range for snapshot connections: 195-293 (excludes 294 = order executor)
_SNAPSHOT_CID_MIN = 195
_SNAPSHOT_CID_MAX = 293

def _random_client_id() -> int:
    """Generate a random client ID for snapshot connections to avoid collisions."""
    return random.randint(_SNAPSHOT_CID_MIN, _SNAPSHOT_CID_MAX)

def run_ibkr_snapshot(
    host: str = IBKR_HOST,
    port: int = IBKR_PORT,
    client_id: int = 0,  # 0 = auto-random
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Connect to IB Gateway, request snapshots for the watchlist, write
    the probe artifact, and disconnect.

    Returns the full probe dict (also persisted to IBKR_PROBE_ARTIFACT).
    Uses a random *client_id* in range [195..293] to avoid collisions with
    the order executor (client_id 294) or stale previous connections.
    If *client_id* is 0 (default), a random one is chosen automatically.
    """
    from ib_insync import IB, Contract

    if client_id == 0:
        client_id = _random_client_id()

    started = _utc_now()
    ib: Optional[IB] = None
    errors: List[Dict[str, Any]] = []

    def _on_error(reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
        errors.append({"reqId": reqId, "errorCode": errorCode, "errorString": errorString})

    symbols: Dict[str, Dict[str, Any]] = {}

    # Retry connection up to 3 times with 3-second delays
    MAX_CONNECT_RETRIES = 3
    RETRY_DELAY = 3.0
    connected = False

    try:
        for attempt in range(1, MAX_CONNECT_RETRIES + 1):
            try:
                ib = IB()
                ib.errorEvent += _on_error
                ib.connect(host, port, clientId=client_id, timeout=timeout)
                if ib.isConnected():
                    connected = True
                    break
                else:
                    log.warning("IBKR connect attempt %d/%d: connected but isConnected()=False",
                                attempt, MAX_CONNECT_RETRIES)
                    try:
                        ib.disconnect()
                    except Exception:
                        pass
                    ib = None
            except Exception as conn_exc:
                log.warning("IBKR connect attempt %d/%d failed: %s",
                            attempt, MAX_CONNECT_RETRIES, conn_exc)
                if ib is not None:
                    try:
                        ib.disconnect()
                    except Exception:
                        pass
                    ib = None
                if attempt < MAX_CONNECT_RETRIES:
                    import time
                    time.sleep(RETRY_DELAY)

        if not connected:
            raise ConnectionError(
                f"Failed to connect to {host}:{port} after {MAX_CONNECT_RETRIES} attempts"
            )

        managed = ib.managedAccounts()
        server_time = int(datetime.now(timezone.utc).timestamp())

        # Request snapshots for each watchlist item
        for entry in _WATCHLIST:
            label = entry["label"]
            ckw = entry["contract"]
            contract = Contract(**ckw)

            try:
                # reqMktData with snapshot=True returns one-shot market data.
                # ib_insync resolves ticks into the Ticker object.
                ticker = ib.reqMktData(contract, snapshot=True)
                ib.sleep(2)  # give IB time to fill ticks
                symbols[label] = _tick_to_dict(ticker)
                ib.cancelMktData(contract)
            except Exception as exc:
                log.warning("Snapshot failed for %s: %s", label, exc)
                symbols[label] = {
                    "bid": None, "ask": None, "last": None, "close": None,
                    "bidSize": None, "askSize": None, "lastSize": None,
                    "has_any_tick": False,
                }
                errors.append({"reqId": -1, "errorCode": -1, "errorString": f"{label}: {exc}"})

        payload: Dict[str, Any] = {
            "schema_version": "ibkr_marketdata_probe_status_v2",
            "checked_utc": _utc_now(),
            "started_utc": started,
            "provider": "ibkr",
            "host": host,
            "port": port,
            "client_id": client_id,
            "connected": True,
            "managed_accounts": managed[0] if managed else "",
            "server_time": server_time,
            "symbols": symbols,
            "errors": errors,
        }

    except Exception as exc:
        log.error("IBKR snapshot connection error: %s", exc)
        payload = {
            "schema_version": "ibkr_marketdata_probe_status_v2",
            "checked_utc": _utc_now(),
            "started_utc": started,
            "provider": "ibkr",
            "host": host,
            "port": port,
            "client_id": client_id,
            "connected": False,
            "managed_accounts": "",
            "server_time": 0,
            "symbols": {},
            "errors": errors + [{"reqId": -1, "errorCode": -1, "errorString": str(exc)}],
        }

    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception as disc_exc:
                log.debug("IBKR disconnect cleanup: %s", disc_exc)

    # Persist the probe artifact
    IBKR_ROOM_DIR.mkdir(parents=True, exist_ok=True)
    write_json(IBKR_PROBE_ARTIFACT, payload)
    log.info(
        "IBKR snapshot: %d symbols, %d with ticks, %d errors",
        len(symbols),
        sum(1 for s in symbols.values() if s.get("has_any_tick")),
        len(errors),
    )
    return payload


# ── Async wrapper for autonomy loop ──────────────────────────────────────────

async def run_ibkr_snapshot_async(
    host: str = IBKR_HOST,
    port: int = IBKR_PORT,
    client_id: int = 0,  # 0 = auto-random
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Run run_ibkr_snapshot in a thread so it doesn't block the event loop.

    ib_insync uses its own event loop internally; running it in a thread
    avoids nested-loop conflicts with the asyncio-based autonomy manager.
    We must ensure the worker thread has a fresh event loop because
    ThreadPoolExecutor threads do not get one by default.
    """
    def _thread_target() -> Dict[str, Any]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return run_ibkr_snapshot(host, port, client_id, timeout)
        finally:
            loop.close()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _thread_target)


# ── Background ingester ──────────────────────────────────────────────────────

class IBKRDataIngester:
    """Periodic background task that refreshes IBKR market-data probe."""

    DEFAULT_INTERVAL = 120  # 2 minutes (was 5 min, reduced for fresher data)

    def __init__(self, interval: int = DEFAULT_INTERVAL):
        self.interval = interval
        self.running = False
        self._last_result: Optional[Dict[str, Any]] = None
        self._consecutive_failures = 0

    async def start(self) -> None:
        """Run the ingestion loop until stop() is called."""
        self.running = True
        log.info("IBKRDataIngester started (interval=%ds)", self.interval)
        while self.running:
            try:
                result = await run_ibkr_snapshot_async()
                self._last_result = result
                if result.get("connected"):
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
            except Exception as exc:
                log.error("IBKRDataIngester cycle failed: %s", exc)
                self._consecutive_failures += 1

            # Back off if repeated failures (max 15 min)
            sleep_time = min(
                self.interval * (2 ** min(self._consecutive_failures, 3)),
                900,
            ) if self._consecutive_failures > 0 else self.interval
            await asyncio.sleep(sleep_time)

    def stop(self) -> None:
        self.running = False
        log.info("IBKRDataIngester stopped")

    def get_status(self) -> Dict[str, Any]:
        last = self._last_result or {}
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "consecutive_failures": self._consecutive_failures,
            "last_checked_utc": last.get("checked_utc"),
            "last_connected": last.get("connected", False),
            "last_symbol_count": len(last.get("symbols", {})),
            "last_error_count": len(last.get("errors", [])),
        }


# Singleton
_ingester: Optional[IBKRDataIngester] = None


def get_ibkr_data_ingester(interval: int = IBKRDataIngester.DEFAULT_INTERVAL) -> IBKRDataIngester:
    global _ingester
    if _ingester is None:
        _ingester = IBKRDataIngester(interval=interval)
    return _ingester
