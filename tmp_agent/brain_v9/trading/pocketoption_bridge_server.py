from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Body, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from brain_v9.core.state_io import read_json, write_json, append_ndjson
import brain_v9.config as _cfg


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pocketoption_bridge")

PORT = urlparse(_cfg.POCKETOPTION_BRIDGE_URL).port or 8765
ROOM_DIR = _cfg.PO_ROOM_DIR
LATEST_PATH = _cfg.PO_BRIDGE_LATEST_ARTIFACT
FEED_PATH = _cfg.PO_FEED_ARTIFACT
EVENTS_PATH = _cfg.PO_EVENTS_ARTIFACT
COMMANDS_PATH = _cfg.PO_COMMANDS_ARTIFACT
LAST_COMMAND_PATH = _cfg.PO_COMMAND_LATEST_ARTIFACT
LAST_RESULT_PATH = _cfg.PO_COMMAND_RESULT_ARTIFACT
COMMAND_REDISPATCH_AFTER_SECONDS = 12
FEATURE_MAX_AGE_SECONDS = int(_cfg.FEATURE_MAX_AGE_SECONDS.get("pocket_option", 300))
_FEED_LOCK = threading.RLock()
_FEED_CACHE: dict[str, Any] | None = None

# P-OP54m: Dedicated file for closed trades scraped from PO UI
CLOSED_TRADES_PATH = ROOM_DIR / "po_closed_trades_latest.json"
_KNOWN_CLOSED_ORDER_IDS: set[str] = set()  # dedup across snapshots

# P-OP55a: Path for historical candle data from chart
HISTORY_CANDLES_PATH = ROOM_DIR / "po_history_candles_latest.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_room_files() -> None:
    global _FEED_CACHE
    ROOM_DIR.mkdir(parents=True, exist_ok=True)
    if not FEED_PATH.exists():
        write_json(
            FEED_PATH,
            {
                "schema_version": "pocketoption_browser_bridge_normalized_feed_v1",
                "updated_utc": utc_now(),
                "row_count": 0,
                "last_row": None,
                "rows": [],
            },
        )
    if _FEED_CACHE is None:
        _FEED_CACHE = read_json(
            FEED_PATH,
            {
                "schema_version": "pocketoption_browser_bridge_normalized_feed_v1",
                "updated_utc": utc_now(),
                "row_count": 0,
                "last_row": None,
                "rows": [],
            },
        )
    if not COMMANDS_PATH.exists():
        write_json(
            COMMANDS_PATH,
            {
                "schema_version": "pocketoption_browser_bridge_commands_v1",
                "updated_utc": utc_now(),
                "commands": [],
            },
        )


def normalize_symbol(value: Any) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    raw = str(value).strip()
    raw = raw.replace("/", "").replace(" ", "")
    if raw.endswith("_otc"):
        base = raw[:-4]
        pair = f"{base.upper()} OTC"
        return f"{base.upper()}_otc", pair
    if raw.upper().endswith("OTC"):
        base = raw[:-3]
        pair = f"{base.upper()} OTC"
        return f"{base.upper()}_otc", pair
    # No _otc suffix detected — keep as-is (non-OTC / regular pair)
    return raw.upper(), raw.upper()


# P-OP46: Server-side price extraction from ws.last_raw_preview.
# When the browser extension's WS handler doesn't capture prices (e.g. non-OTC
# pairs filtered out by the OTC-only check), the price is still visible in the
# raw preview string.  Extract it here so the pipeline isn't blocked by
# extension caching issues.
_RAW_PREVIEW_RE = re.compile(
    r'\["([A-Za-z]{6}(?:_otc)?)"'   # symbol like EURUSD or EURUSD_otc
    r'\s*,\s*'
    r'(\d+(?:\.\d+)?)'               # timestamp
    r'\s*,\s*'
    r'(\d+(?:\.\d+)?)'               # price
    r'\s*\]'
)

# P-OP49: Cache the last successfully extracted price so that when
# last_raw_preview contains a heartbeat ("2"/"3"), we can still use the
# most recent price.  Expires after _PRICE_CACHE_MAX_AGE_S seconds.
_PRICE_CACHE_MAX_AGE_S = 90.0
_price_cache: dict[str, Any] = {
    "symbol": None,
    "timestamp": None,
    "price": None,
    "cached_at": 0.0,
}
import time as _time


def _extract_from_raw_preview(raw_preview: Any) -> tuple[str | None, float | None, float | None]:
    """Parse ws.last_raw_preview to extract (symbol, timestamp, price).

    Returns (None, None, None) if parsing fails.
    """
    if not raw_preview or not isinstance(raw_preview, str):
        return None, None, None
    m = _RAW_PREVIEW_RE.search(str(raw_preview))
    if not m:
        return None, None, None
    sym = m.group(1).upper()
    try:
        ts = float(m.group(2))
        price = float(m.group(3))
        if price > 0:
            return sym, ts, price
    except (ValueError, TypeError):
        pass
    return None, None, None


def build_row(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload.get("current") if isinstance(payload.get("current"), dict) else payload
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    ws = payload.get("ws") if isinstance(payload.get("ws"), dict) else {}
    dom = payload.get("dom") if isinstance(payload.get("dom"), dict) else {}

    symbol, pair = normalize_symbol(current.get("symbol") or current.get("pair") or dom.get("pair"))
    pair = current.get("pair") or pair
    price = current.get("price") or current.get("last_price") or dom.get("visible_price")
    source_ts = current.get("source_timestamp") or current.get("timestamp")
    last_stream_symbol = ws.get("last_stream_symbol")
    stream_symbol_match = ws.get("stream_symbol_match")

    # P-OP46: Server-side fallback — extract price from ws.last_raw_preview
    # when the extension's WS handler didn't capture it (non-OTC filtering).
    if not price:
        # Prefer last_price_raw_preview (P-OP48: only updateStream messages)
        # over last_raw_preview (may contain heartbeats like "2").
        raw_preview = ws.get("last_price_raw_preview") or ws.get("last_raw_preview")
        ws_sym, ws_ts, ws_price = _extract_from_raw_preview(raw_preview)
        if ws_price:
            price = ws_price
            source_ts = source_ts or ws_ts
            last_stream_symbol = ws_sym
            # Compute stream_symbol_match server-side
            if symbol and ws_sym:
                norm_dom = symbol.upper().replace("_OTC", "")
                norm_ws = ws_sym.upper().replace("_OTC", "")
                stream_symbol_match = (norm_dom == norm_ws)
            # P-OP49: Update price cache on successful extraction
            _price_cache["symbol"] = ws_sym
            _price_cache["timestamp"] = ws_ts
            _price_cache["price"] = ws_price
            _price_cache["cached_at"] = _time.monotonic()
            logger.info(
                "P-OP46 fallback: price=%.5f from raw_preview (ws_sym=%s, dom_sym=%s, match=%s)",
                ws_price, ws_sym, symbol, stream_symbol_match,
            )

    # P-OP49: If still no price, use cached price (max _PRICE_CACHE_MAX_AGE_S old)
    if not price and _price_cache["price"]:
        age = _time.monotonic() - _price_cache["cached_at"]
        if age <= _PRICE_CACHE_MAX_AGE_S:
            price = _price_cache["price"]
            source_ts = source_ts or _price_cache["timestamp"]
            last_stream_symbol = last_stream_symbol or _price_cache["symbol"]
            if symbol and _price_cache["symbol"]:
                norm_dom = symbol.upper().replace("_OTC", "")
                norm_ws = _price_cache["symbol"].upper().replace("_OTC", "")
                stream_symbol_match = (norm_dom == norm_ws)
            logger.debug(
                "P-OP49 cache hit: price=%.5f (age=%.1fs)",
                price, age,
            )

    payout = current.get("payout_pct") or dom.get("payout_pct")
    expiry = current.get("expiry_seconds") or dom.get("expiry_seconds")
    balance = dom.get("balance_demo") or payload.get("balance_demo")
    duration_candidates = dom.get("duration_candidates") if isinstance(dom.get("duration_candidates"), list) else []
    indicator_candidates = dom.get("indicator_candidates") if isinstance(dom.get("indicator_candidates"), list) else []
    indicator_readouts = dom.get("indicator_readouts") if isinstance(dom.get("indicator_readouts"), list) else []

    return {
        "captured_utc": payload.get("captured_utc") or runtime.get("captured_utc") or utc_now(),
        "pair": pair,
        "symbol": symbol,
        "source_timestamp": source_ts,
        "price": price,
        "payout_pct": payout,
        "expiry_seconds": expiry,
        "socket_event_count": ws.get("event_count") or payload.get("event_count"),
        "last_socket_event": ws.get("last_event_name") or payload.get("event_name"),
        "last_socket_url": ws.get("last_socket_url") or payload.get("socket_url"),
        "last_stream_symbol": last_stream_symbol,
        "visible_symbol": ws.get("visible_symbol"),
        "stream_symbol_match": stream_symbol_match,
        "balance_demo": balance,
        "visible_price": dom.get("visible_price"),
        "selected_duration_label": dom.get("selected_duration_label"),
        "duration_candidates": duration_candidates,
        "indicator_candidates": indicator_candidates,
        "duration_candidates_count": len(duration_candidates),
        "indicator_candidates_count": len(indicator_candidates),
        "indicator_readouts_count": len(indicator_readouts),
    }


def append_event(payload: dict[str, Any]) -> None:
    append_ndjson(EVENTS_PATH, {"captured_utc": utc_now(), "payload": payload})


def read_commands() -> dict[str, Any]:
    ensure_room_files()
    return read_json(
        COMMANDS_PATH,
        {
            "schema_version": "pocketoption_browser_bridge_commands_v1",
            "updated_utc": utc_now(),
            "commands": [],
        },
    )


def parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        logger.debug("Could not parse UTC value %r: %s", value, exc)
        return None


def write_commands(payload: dict[str, Any]) -> None:
    payload["updated_utc"] = utc_now()
    write_json(COMMANDS_PATH, payload)


def create_command(symbol: str, direction: str, amount: float, duration: int) -> dict[str, Any]:
    commands_payload = read_commands()
    command = {
        "command_id": f"pocmd_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "created_utc": utc_now(),
        "status": "queued",
        "paper_only": True,
        "live_trading_forbidden": True,
        "action": "place_demo_trade",
        "trade": {
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "duration": duration,
        },
        "dispatched_utc": None,
        "result_utc": None,
        "result": None,
    }
    commands = commands_payload.get("commands", [])
    commands.append(command)
    commands_payload["commands"] = commands[-100:]
    write_commands(commands_payload)
    write_json(LAST_COMMAND_PATH, command)
    append_event({"type": "bridge_command_created", "command": command})
    return command


def next_pending_command() -> dict[str, Any] | None:
    commands_payload = read_commands()
    commands = commands_payload.get("commands", [])
    selected = None
    now = datetime.now(timezone.utc)
    for command in commands:
        if command.get("status") == "queued":
            command["status"] = "dispatched"
            command["dispatched_utc"] = utc_now()
            command["dispatch_attempts"] = int(command.get("dispatch_attempts", 0)) + 1
            selected = command
            break
    if selected is None:
        for command in commands:
            if command.get("status") != "dispatched" or command.get("result_utc"):
                continue
            dispatched_utc = parse_utc(command.get("dispatched_utc"))
            if not dispatched_utc:
                continue
            age = now - dispatched_utc
            if age >= timedelta(seconds=COMMAND_REDISPATCH_AFTER_SECONDS):
                command["dispatched_utc"] = utc_now()
                command["redispatched_utc"] = command["dispatched_utc"]
                command["dispatch_attempts"] = int(command.get("dispatch_attempts", 1)) + 1
                selected = command
                append_event({
                    "type": "bridge_command_redispatched",
                    "command_id": command.get("command_id"),
                    "dispatch_attempts": command.get("dispatch_attempts"),
                    "age_seconds": round(age.total_seconds(), 1),
                })
                break
    if selected:
        commands_payload["commands"] = commands
        write_commands(commands_payload)
        write_json(LAST_COMMAND_PATH, selected)
        append_event({"type": "bridge_command_dispatched", "command": selected})
    return selected


def command_status(command_id: str) -> dict[str, Any] | None:
    commands_payload = read_commands()
    for command in commands_payload.get("commands", []):
        if command.get("command_id") == command_id:
            return command
    return None


def register_command_result(payload: dict[str, Any]) -> dict[str, Any]:
    command_id = payload.get("command_id")
    commands_payload = read_commands()
    commands = commands_payload.get("commands", [])
    updated = None
    for command in commands:
        if command.get("command_id") == command_id:
            command["status"] = "completed" if payload.get("success") else "failed"
            command["result_utc"] = utc_now()
            command["result"] = payload
            updated = command
            break
    if updated is None:
        updated = {
            "command_id": command_id,
            "created_utc": None,
            "status": "completed" if payload.get("success") else "failed",
            "paper_only": True,
            "live_trading_forbidden": True,
            "action": "place_demo_trade",
            "trade": payload.get("trade") or {},
            "dispatched_utc": None,
            "result_utc": utc_now(),
            "result": payload,
        }
        commands.append(updated)
    commands_payload["commands"] = commands[-100:]
    write_commands(commands_payload)
    write_json(LAST_RESULT_PATH, updated)
    append_event({"type": "bridge_command_result", "command": updated})
    return updated


def update_feed(row: dict[str, Any]) -> dict[str, Any]:
    global _FEED_CACHE
    ensure_room_files()
    with _FEED_LOCK:
        feed = _FEED_CACHE if isinstance(_FEED_CACHE, dict) else {}
        if not feed:
            feed = {
                "schema_version": "pocketoption_browser_bridge_normalized_feed_v1",
                "updated_utc": utc_now(),
                "row_count": 0,
                "last_row": None,
                "rows": [],
            }
        rows = list(feed.get("rows") or [])
        rows.append(row)
        rows = rows[-5000:]  # P-OP55a: Raised from 500 → 5000 (~20 min of ticks at 4/sec)
        feed["rows"] = rows
        feed["row_count"] = len(rows)
        feed["last_row"] = row
        feed["updated_utc"] = utc_now()
        _FEED_CACHE = feed
        write_json(FEED_PATH, feed)
        return feed


app = FastAPI(title="PocketOption Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_room_files()
    logger.info("PocketOption bridge listening on %s", PORT)


@app.get("/health")
@app.get("/healthz")
def health() -> dict[str, Any]:
    latest = read_json(LATEST_PATH, {})
    latest_result = read_json(LAST_RESULT_PATH, {})
    latest_result_payload = latest_result.get("result") if isinstance(latest_result.get("result"), dict) else {}
    current = latest.get("current") if isinstance(latest.get("current"), dict) else {}
    dom = latest.get("dom") if isinstance(latest.get("dom"), dict) else {}
    duration_candidates = dom.get("duration_candidates") if isinstance(dom.get("duration_candidates"), list) else []
    indicator_candidates = dom.get("indicator_candidates") if isinstance(dom.get("indicator_candidates"), list) else []
    indicator_readouts = dom.get("indicator_readouts") if isinstance(dom.get("indicator_readouts"), list) else []
    captured_utc = parse_utc(latest.get("captured_utc"))
    data_age_seconds = None
    is_fresh = False
    if captured_utc:
        data_age_seconds = max(0.0, (datetime.now(timezone.utc) - captured_utc).total_seconds())
        is_fresh = data_age_seconds <= FEATURE_MAX_AGE_SECONDS
    return {
        "ok": True,
        "service": "pocketoption_bridge",
        "mode": "paper_only",
        "status": "available" if is_fresh else "stale",
        "connected": bool(captured_utc and is_fresh),
        "latest_pair": current.get("pair") or latest.get("dom", {}).get("pair"),
        "latest_symbol": current.get("symbol"),
        "latest_capture_utc": latest.get("captured_utc"),
        "data_age_seconds": round(data_age_seconds, 3) if data_age_seconds is not None else None,
        "is_fresh": is_fresh,
        "stale_after_seconds": FEATURE_MAX_AGE_SECONDS,
        "demo_order_api_ready": bool(latest_result_payload.get("accepted_click")),
        "demo_order_ui_confirmation_ready": bool(latest_result_payload.get("ui_trade_confirmed")),
        "last_command_status": latest_result.get("status"),
        "last_command_result_utc": latest_result.get("result_utc"),
        "last_command_result_status": latest_result_payload.get("status"),
        "last_command_click_submitted": bool(latest_result_payload.get("accepted_click")),
        "last_command_ui_trade_confirmed": bool(latest_result_payload.get("ui_trade_confirmed")),
        "last_stream_symbol": latest.get("ws", {}).get("last_stream_symbol"),
        "visible_symbol": latest.get("ws", {}).get("visible_symbol"),
        "stream_symbol_match": latest.get("ws", {}).get("stream_symbol_match"),
        "selected_duration_label": dom.get("selected_duration_label"),
        "duration_candidates_count": len(duration_candidates),
        "indicator_candidates_count": len(indicator_candidates),
        "indicator_readouts_count": len(indicator_readouts),
        "bridge_port": PORT,
    }


@app.get("/balance")
def balance() -> dict[str, Any]:
    latest = read_json(LATEST_PATH, {})
    dom = latest.get("dom") if isinstance(latest.get("dom"), dict) else {}
    return {
        "ok": True,
        "mode": "paper_only",
        "balance": dom.get("balance_demo"),
        "balance_demo": dom.get("balance_demo"),
        "currency": "USD",
        "captured_utc": latest.get("captured_utc"),
    }


@app.get("/normalized")
def normalized() -> dict[str, Any]:
    ensure_room_files()
    with _FEED_LOCK:
        if isinstance(_FEED_CACHE, dict):
            return dict(_FEED_CACHE)
    return read_json(FEED_PATH, {})


@app.get("/csv")
def csv_export() -> Response:
    feed = read_json(FEED_PATH, {"rows": []})
    output = io.StringIO()
    fieldnames = [
        "captured_utc",
        "pair",
        "symbol",
        "source_timestamp",
        "price",
        "payout_pct",
        "expiry_seconds",
        "socket_event_count",
        "last_socket_event",
        "last_socket_url",
        "balance_demo",
        "visible_price",
        "selected_duration_label",
        "duration_candidates_count",
        "indicator_candidates_count",
        "indicator_readouts_count",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in feed.get("rows", []):
        writer.writerow({name: row.get(name) for name in fieldnames})
    return PlainTextResponse(output.getvalue(), media_type="text/csv")


@app.get("/trades/open")
def open_trades() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "paper_only",
        "trades": [],
        "count": 0,
    }


@app.get("/trades/history")
def trade_history(limit: int = 100) -> dict[str, Any]:
    feed = normalized()
    rows = feed.get("rows", [])[-limit:]
    return {
        "ok": True,
        "mode": "paper_only",
        "trades": rows,
        "count": len(rows),
    }


@app.post("/trade")
def trade_command(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    symbol = payload.get("symbol")
    direction = payload.get("direction")
    amount = float(payload.get("amount", 0))
    duration = int(payload.get("duration", 0))
    command = create_command(symbol=symbol, direction=direction, amount=amount, duration=duration)
    return {
        "success": True,
        "ok": True,
        "mode": "paper_only",
        "status": "queued",
        "command_id": command["command_id"],
        "trade_id": command["command_id"],
        "message": "Demo trade command queued for browser bridge execution.",
        "paper_only": True,
        "live_trading_forbidden": True,
        "command": command,
    }


@app.get("/commands/next")
def commands_next() -> dict[str, Any]:
    command = next_pending_command()
    return {
        "ok": True,
        "mode": "paper_only",
        "command": command,
    }


@app.get("/commands/status/{command_id}")
def commands_status(command_id: str) -> dict[str, Any]:
    command = command_status(command_id)
    return {
        "ok": command is not None,
        "mode": "paper_only",
        "command": command,
    }


@app.post("/commands/result")
def commands_result(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    updated = register_command_result(payload)
    return {
        "ok": True,
        "mode": "paper_only",
        "command": updated,
    }


@app.post("/")
@app.post("/capture")
@app.post("/snapshot")
@app.post("/bridge/snapshot")
@app.post("/ingest")
async def ingest(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    ensure_room_files()
    effective_payload = payload or {}
    if not effective_payload:
        try:
            effective_payload = await request.json()
        except Exception as exc:
            logger.debug("Failed to parse request body as JSON: %s", exc)
            effective_payload = {}

    if not isinstance(effective_payload, dict):
        effective_payload = {"raw": effective_payload}

    if "captured_utc" not in effective_payload:
        effective_payload["captured_utc"] = utc_now()

    # P-OP6: Only overwrite browser_bridge_latest.json when the snapshot
    # contains real market data (at minimum a symbol).  Empty/heartbeat
    # snapshots that lack symbol/pair/price would erase the good snapshot
    # and cause the feature engine to return zero features, blocking all
    # PocketOption signal generation until the next good snapshot arrives.
    _cur = effective_payload.get("current") if isinstance(effective_payload.get("current"), dict) else effective_payload
    _dom = effective_payload.get("dom") if isinstance(effective_payload.get("dom"), dict) else {}
    _has_market_data = bool(
        _cur.get("symbol") or _cur.get("pair") or _dom.get("pair") or _dom.get("visible_price")
    )
    if _has_market_data:
        write_json(LATEST_PATH, effective_payload)
    else:
        logger.debug(
            "Snapshot skipped (no market data, preserving existing): keys=%s",
            list(effective_payload.keys()),
        )

    append_event(effective_payload)
    row = build_row(effective_payload)
    feed = update_feed(row)

    # P-OP54m: Persist closed trades from extension scraping.
    # The extension parses the "Closed" panel in PO UI and sends
    # structured trade data (order_price, closing_price, difference_pts).
    # We accumulate unique trades (by order_id) for correlation analysis.
    _closed_trades_raw = effective_payload.get("closed_trades")
    if _closed_trades_raw and isinstance(_closed_trades_raw, list):
        _new_count = 0
        existing = read_json(CLOSED_TRADES_PATH, {"trades": [], "updated_utc": None})
        existing_trades = existing.get("trades", [])
        existing_ids = {t.get("order_id") for t in existing_trades if t.get("order_id")}
        _KNOWN_CLOSED_ORDER_IDS.update(existing_ids)

        for ct in _closed_trades_raw:
            oid = ct.get("order_id")
            if oid and oid not in _KNOWN_CLOSED_ORDER_IDS:
                _KNOWN_CLOSED_ORDER_IDS.add(oid)
                existing_trades.append(ct)
                _new_count += 1

        if _new_count > 0:
            existing["trades"] = existing_trades[-200:]  # keep last 200
            existing["updated_utc"] = utc_now()
            existing["total_captured"] = len(existing_trades)
            write_json(CLOSED_TRADES_PATH, existing)
            logger.info("P-OP54m: %d new closed trades captured (total: %d)", _new_count, len(existing_trades))

    logger.info(
        "Snapshot ingested: symbol=%s pair=%s price=%s",
        row.get("symbol"),
        row.get("pair"),
        row.get("price"),
    )
    return {
        "ok": True,
        "service": "pocketoption_bridge",
        "mode": "paper_only",
        "captured_utc": effective_payload["captured_utc"],
        "row_count": feed.get("row_count", 0),
        "last_row": row,
    }


# ── P-OP55a: Historical candle data endpoint ─────────────────────────────
# The browser extension intercepts loadHistoryPeriod/historyPeriod WS
# responses from PocketOption and forwards OHLC candles here.
# We persist them so the feature_engine candle buffer can seed instantly
# instead of accumulating from zero (which takes 15+ min of live ticks).
@app.post("/history-candles")
async def history_candles(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("candles"):
        return {"ok": False, "error": "no candles in payload"}

    symbol = payload.get("symbol", "unknown")
    candles = payload.get("candles", [])
    period = payload.get("period", 60)

    # Validate candle format: each must have t, o, c, h, l
    valid_candles = []
    for c in candles:
        if isinstance(c, dict) and all(k in c for k in ("t", "o", "c", "h", "l")):
            valid_candles.append({
                "t": int(c["t"]),
                "o": float(c["o"]),
                "c": float(c["c"]),
                "h": float(c["h"]),
                "l": float(c["l"]),
            })

    if not valid_candles:
        return {"ok": False, "error": "no valid candles after validation"}

    # Sort by timestamp ascending
    valid_candles.sort(key=lambda x: x["t"])

    history_data = {
        "symbol": symbol,
        "period": period,
        "candle_count": len(valid_candles),
        "candles": valid_candles,
        "received_utc": utc_now(),
        "source": "browser_bridge_history",
    }

    write_json(HISTORY_CANDLES_PATH, history_data)
    logger.info(
        "P-OP55a: Received %d historical candles for %s (period=%ds)",
        len(valid_candles), symbol, period,
    )

    return {
        "ok": True,
        "symbol": symbol,
        "candles_accepted": len(valid_candles),
        "period": period,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
