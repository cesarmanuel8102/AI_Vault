"""
Dashboard por Plataforma - AI_VAULT
Adaptador legacy reanclado a fuentes canónicas de Brain V9.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

TMP_AGENT_PATH = Path(r"C:\AI_VAULT\tmp_agent")
if str(TMP_AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT_PATH))

from brain_v9.config import IBKR_PROBE_ARTIFACT, PO_BRIDGE_LATEST_ARTIFACT
from brain_v9.core.state_io import read_json
from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str, timeout: int = 8) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _po_live_context() -> Dict[str, Any]:
    payload = read_json(PO_BRIDGE_LATEST_ARTIFACT, {})
    current = payload.get("current") if isinstance(payload, dict) else {}
    ws = payload.get("ws") if isinstance(payload, dict) else {}
    return {
        "current_symbol": current.get("symbol") or ws.get("visible_symbol"),
        "current_price": current.get("price"),
        "payout_pct": current.get("payout_pct"),
        "data_points": ws.get("event_count", 0),
    }


def _ibkr_live_context() -> Dict[str, Any]:
    payload = read_json(IBKR_PROBE_ARTIFACT, {})
    return {
        "port": payload.get("port", 4002),
        "port_open": bool(payload.get("connected")),
        "managed_accounts": payload.get("managed_accounts"),
        "market_data_ready": bool(payload.get("connected")),
    }


def _canonical_sample_accumulator() -> Dict[str, Any]:
    runtime = _fetch_json("http://127.0.0.1:8090/brain/autonomy/sample-accumulator", timeout=8)
    if runtime.get("ok") and isinstance(runtime.get("data"), dict):
        payload = runtime["data"].get("status", {})
        per_platform = payload.get("per_platform", {})
        return {
            "running": bool(payload.get("running")),
            "session_trades": int(payload.get("session_trades_count", 0) or 0),
            "last_trade": payload.get("last_trade_time"),
            "mode": payload.get("mode", "APRENDIZAJE MULTI-PLATAFORMA"),
            "cooldown": payload.get("cooldown_minutes", "1 min"),
            "check_interval": payload.get("check_interval_minutes", "mixed"),
            "aprendizaje": "SI - Estado canónico por plataforma",
            "per_platform": per_platform,
        }

    status = read_json(TMP_AGENT_PATH / "state" / "platform_accumulators" / "pocket_option_accumulator.json", {})
    return {
        "running": False,
        "session_trades": int(status.get("session_trades", 0) or 0),
        "last_trade": status.get("last_trade_time"),
        "mode": "APRENDIZAJE MULTI-PLATAFORMA",
        "cooldown": "1 min",
        "check_interval": "mixed",
        "aprendizaje": "SI - Fallback a artifacts canónicos",
        "per_platform": {},
    }


def build_platform_dashboard() -> Dict[str, Any]:
    """Construye el dashboard legacy usando solo fuentes canónicas."""
    api = get_platform_dashboard_api()
    summary = api.get_all_platforms_summary()

    po_summary = summary.get("platforms", {}).get("pocket_option", {})
    ibkr_summary = summary.get("platforms", {}).get("ibkr", {})
    po_signals = api.get_platform_signals_analysis("pocket_option")
    ibkr_signals = api.get_platform_signals_analysis("ibkr")
    po_trades = api.get_platform_trade_history("pocket_option", limit=10)
    ibkr_trades = api.get_platform_trade_history("ibkr", limit=10)

    po_live = _po_live_context()
    ibkr_live = _ibkr_live_context()
    accumulator = _canonical_sample_accumulator()

    return {
        "generated_utc": _utc_now(),
        "mode": "APRENDIZAJE CON SENALES",
        "platforms": {
            "pocket_option": {
                "name": "PocketOption",
                "type": "Opciones Binarias OTC",
                "venue": "pocket_option",
                "status": po_summary.get("status"),
                "connected": po_summary.get("status") == "active",
                "timeframe": "1m",
                "current_symbol": po_live.get("current_symbol"),
                "current_price": po_live.get("current_price"),
                "payout_pct": po_live.get("payout_pct"),
                "data_points": po_live.get("data_points", 0),
                "signals": {
                    "total": po_signals.get("total_signals", 0),
                    "valid": po_signals.get("valid_signals", 0),
                    "items": [],
                },
                "strategies": po_summary.get("metrics", {}).get("total_trades", 0),
                "recent_trades": len(po_trades),
                "updated": po_summary.get("timestamp"),
            },
            "ibkr": {
                "name": "Interactive Brokers",
                "type": "Stocks/ETFs/Options",
                "venue": "ibkr",
                "status": ibkr_summary.get("status"),
                "connected": ibkr_summary.get("status") == "active",
                "timeframe": "5m",
                "port": ibkr_live.get("port", 4002),
                "port_open": ibkr_live.get("port_open"),
                "order_api_ready": False,
                "managed_accounts": ibkr_live.get("managed_accounts"),
                "market_data_ready": ibkr_live.get("market_data_ready"),
                "signals": {
                    "total": ibkr_signals.get("total_signals", 0),
                    "valid": ibkr_signals.get("valid_signals", 0),
                    "items": [],
                },
                "strategies": ibkr_summary.get("metrics", {}).get("total_trades", 0),
                "recent_orders": len(ibkr_trades),
                "updated": ibkr_summary.get("timestamp"),
            },
        },
        "sample_accumulator": accumulator,
        "summary": {
            "total_platforms": 2,
            "platforms_connected": sum(
                1 for item in [po_summary, ibkr_summary] if item.get("status") == "active"
            ),
            "total_signals": po_signals.get("total_signals", 0) + ibkr_signals.get("total_signals", 0),
            "valid_signals": po_signals.get("valid_signals", 0) + ibkr_signals.get("valid_signals", 0),
            "total_strategies": 2,
            "session_trades": accumulator["session_trades"],
            "aprendizaje_activo": accumulator["aprendizaje"],
        },
    }


def get_platforms_summary() -> Dict[str, Any]:
    return build_platform_dashboard()


if __name__ == "__main__":
    print(json.dumps(build_platform_dashboard(), indent=2))
