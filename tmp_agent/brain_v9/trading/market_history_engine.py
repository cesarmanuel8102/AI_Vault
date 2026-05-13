"""
Brain V9 - Market history engine
Construye series históricas de precio para replay paper no aleatorio.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from brain_v9.config import BASE_PATH, SECRETS
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

MARKET_HISTORY_PATH = ENGINE_PATH / "market_history_snapshot_latest.json"
log = logging.getLogger("market_history_engine")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_tiingo_token() -> str:
    try:
        path = SECRETS["tiingo"]
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data.get("token") or data.get("api_key") or "").strip()
    except Exception as exc:
        log.debug("Error loading Tiingo token: %s", exc)
    return ""


def _fetch_tiingo_daily(symbol: str, days: int = 120) -> List[Dict[str, Any]]:
    token = _load_tiingo_token()
    if not token:
        return []
    end = datetime.now().date()
    start = end - timedelta(days=days)
    params = urlencode({"startDate": start.isoformat(), "endDate": end.isoformat()})
    url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?{params}"
    request = Request(url, headers={"Authorization": f"Token {token}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log.warning("Tiingo API request failed for %s: %s", symbol, exc)
        return []
    rows: List[Dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "timestamp": item.get("date"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
            "source": "tiingo_daily",
        })
    return rows


def _extract_symbols(strategies: List[Dict[str, Any]]) -> List[str]:
    symbols: List[str] = []
    for strategy in strategies:
        if strategy.get("venue") != "ibkr":
            continue
        for symbol in strategy.get("universe", []) or []:
            text = str(symbol).strip().upper()
            if text and text not in symbols:
                symbols.append(text)
    return symbols


def build_market_history_snapshot(strategies: List[Dict[str, Any]], days: int = 120) -> Dict[str, Any]:
    cached = read_market_history_snapshot()
    generated = cached.get("generated_utc")
    if generated:
        try:
            generated_dt = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - generated_dt).total_seconds() < 900:
                cached_symbols = set((cached.get("symbols") or {}).keys())
                wanted_symbols = set(_extract_symbols(strategies))
                if wanted_symbols.issubset(cached_symbols):
                    return cached
        except Exception as exc:
            log.debug("Error parsing market history cache timestamp: %s", exc)

    symbols = _extract_symbols(strategies)
    series_by_symbol: Dict[str, Any] = {}
    total_rows = 0
    for symbol in symbols:
        rows = _fetch_tiingo_daily(symbol, days=days)
        total_rows += len(rows)
        series_by_symbol[symbol] = {
            "symbol": symbol,
            "venue": "ibkr",
            "granularity": "1d",
            "rows": rows,
            "row_count": len(rows),
            "history_ready": len(rows) >= 20,
            "source": "tiingo_daily",
        }
    snapshot = {
        "schema_version": "market_history_snapshot_v1",
        "generated_utc": _utc_now(),
        "days_requested": days,
        "symbols": series_by_symbol,
        "summary": {
            "symbols_count": len(series_by_symbol),
            "history_ready_count": sum(1 for item in series_by_symbol.values() if item.get("history_ready")),
            "total_rows": total_rows,
            "granularity": "1d",
            "source": "tiingo_daily",
        },
    }
    write_json(MARKET_HISTORY_PATH, snapshot)
    return snapshot


def read_market_history_snapshot() -> Dict[str, Any]:
    return read_json(MARKET_HISTORY_PATH, {
        "schema_version": "market_history_snapshot_v1",
        "generated_utc": None,
        "symbols": {},
        "summary": {},
    })
