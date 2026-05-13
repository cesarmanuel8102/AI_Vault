import argparse
import base64
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


BASE_URL = "https://www.quantconnect.com/api/v2"
FILLED_STATUS_TEXT = {"filled", "partiallyfilled"}
FILLED_STATUS_INT = {2, 3}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def load_qc_credentials(path: Optional[str]) -> Dict[str, str]:
    default_path = r"C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json"
    p = Path(path or os.environ.get("QC_SECRETS", default_path))
    data = json.loads(p.read_text(encoding="utf-8"))

    user_id = str(data.get("user_id") or data.get("userId") or "").strip()
    api_token = str(data.get("api_token") or data.get("apiToken") or data.get("token") or "").strip()
    if not user_id or not api_token:
        raise RuntimeError(f"Invalid QuantConnect credentials in {p}")
    return {"user_id": user_id, "api_token": api_token}


def auth_headers(creds: Dict[str, str], timestamp_override: Optional[int] = None) -> Dict[str, str]:
    ts_int = int(timestamp_override) if timestamp_override is not None else int(datetime.utcnow().timestamp())
    ts = str(ts_int)
    hashed = hashlib.sha256(f"{creds['api_token']}:{ts}".encode("utf-8")).hexdigest()
    basic = base64.b64encode(f"{creds['user_id']}:{hashed}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {basic}",
        "Timestamp": ts,
        "Content-Type": "application/json",
    }


def post_qc(
    endpoint: str,
    payload: Dict[str, Any],
    creds: Dict[str, str],
    timestamp_override: Optional[int] = None,
) -> Dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/{endpoint}",
        headers=auth_headers(creds, timestamp_override=timestamp_override),
        json=payload,
        timeout=45,
    )
    r.raise_for_status()
    return r.json()


def fetch_live_orders(
    creds: Dict[str, str],
    project_id: int,
    deploy_id: str,
    start: int,
    end: int,
) -> List[Dict[str, Any]]:
    forced_ts: Optional[int] = None
    attempts = [
        ("live/read/orders", {"projectId": project_id, "deployId": deploy_id, "start": start, "end": end}),
        ("live/read/orders", {"projectId": project_id, "start": start, "end": end}),
        ("live/orders/read", {"projectId": project_id, "deployId": deploy_id, "start": start, "end": end}),
        ("live/orders/read", {"projectId": project_id, "start": start, "end": end}),
    ]
    last_error = None
    for endpoint, payload in attempts:
        if not deploy_id and "deployId" in payload:
            continue
        try:
            data = post_qc(endpoint, payload, creds, timestamp_override=forced_ts)
            if not data.get("success", False):
                errs = data.get("errors") or []
                # Handle machine clock drift: retry with QC server timestamp.
                txt = " ".join(str(e) for e in errs) if isinstance(errs, list) else str(errs)
                m = re.search(r"Server Time:\s*(\d+)", txt)
                if m:
                    forced_ts = int(m.group(1)) - 1
                    data = post_qc(endpoint, payload, creds, timestamp_override=forced_ts)
                    if data.get("success", False):
                        orders = data.get("orders", [])
                        if isinstance(orders, list):
                            return orders
                last_error = RuntimeError(str(data.get("errors") or data))
                continue
            orders = data.get("orders", [])
            if isinstance(orders, list):
                return orders
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError(f"Unable to fetch live orders: {last_error}")
    return []


def extract_symbol(order: Dict[str, Any]) -> str:
    events = order.get("events") or order.get("Events") or []
    if isinstance(events, list) and events:
        ev0 = events[0] if isinstance(events[0], dict) else {}
        for k in ("symbolPermtick", "symbolValue", "symbol"):
            ev_sym = str(ev0.get(k, "")).strip().upper()
            if ev_sym:
                # "SYMBOL PERM|..." -> keep first root-ish token
                if "|" in ev_sym:
                    ev_sym = ev_sym.split("|", 1)[0].strip()
                if " " in ev_sym:
                    ev_sym = ev_sym.split(" ", 1)[0].strip()
                return ev_sym

    s = order.get("symbol") or order.get("Symbol") or ""
    if isinstance(s, dict):
        sv = s.get("value") or s.get("Value") or ""
    else:
        sv = str(s)
    sv = sv.strip().upper()
    if not sv:
        return "MNQ"
    # Normalize to root symbol used by execution core.
    for root in ("MNQ", "MES", "M2K", "MYM", "ES", "NQ", "RTY", "YM"):
        if root in sv:
            return root
    return sv.split(" ")[0]


def parse_timestamp_et(order: Dict[str, Any]) -> Optional[str]:
    candidates = [
        order.get("time"),
        order.get("Time"),
        order.get("createdTime"),
        order.get("CreatedTime"),
        order.get("lastFillTime"),
        order.get("LastFillTime"),
    ]
    for raw in candidates:
        if not raw:
            continue
        txt = str(raw).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(txt)
            # keep local date-time string expected by phase0 runner
            return dt.astimezone().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    # Fallback to event timestamp (usually Unix epoch seconds)
    events = order.get("events") or order.get("Events") or []
    if isinstance(events, list):
        for ev in events:
            if not isinstance(ev, dict):
                continue
            raw_ev = ev.get("time") or ev.get("Time")
            if isinstance(raw_ev, (int, float)):
                try:
                    dt = datetime.fromtimestamp(float(raw_ev))
                    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass
            if isinstance(raw_ev, str):
                txt = raw_ev.replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(txt)
                    return dt.astimezone().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass
    return None


def is_filled(order: Dict[str, Any]) -> bool:
    status = order.get("status")
    if status is None:
        status = order.get("Status")
    if isinstance(status, str):
        return status.lower().replace(" ", "") in FILLED_STATUS_TEXT
    if isinstance(status, (int, float)):
        if int(status) in FILLED_STATUS_INT:
            return True
    events = order.get("events") or order.get("Events") or []
    if isinstance(events, list):
        for ev in events:
            if not isinstance(ev, dict):
                continue
            st = str(ev.get("status", "") or ev.get("Status", "")).lower().replace(" ", "")
            if st in FILLED_STATUS_TEXT:
                return True
    return False


def infer_side_qty(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    qty = order.get("quantity")
    if qty is None:
        qty = order.get("Quantity")
    q = _safe_int(qty, 0)
    if q == 0:
        direction = str(order.get("direction") or order.get("Direction") or "").upper()
        if direction in {"BUY", "LONG"}:
            q = 1
        elif direction in {"SELL", "SHORT"}:
            q = -1
        else:
            events = order.get("events") or order.get("Events") or []
            if isinstance(events, list):
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    ed = str(ev.get("direction", "") or ev.get("Direction", "")).upper()
                    fq = _safe_float(ev.get("fillQuantity") or ev.get("quantity"), 0.0)
                    if fq <= 0:
                        continue
                    if ed in {"BUY", "LONG"}:
                        q = int(round(fq))
                        break
                    if ed in {"SELL", "SHORT"}:
                        q = -int(round(fq))
                        break
            if q == 0:
                return None
    side = "BUY" if q > 0 else "SELL"
    return {"side": side, "qty": abs(q)}


def build_signal_from_order(
    order: Dict[str, Any],
    trade_date_et: Optional[str],
    stop_points: Dict[str, float],
    target_points: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    if not is_filled(order):
        return None

    ts = parse_timestamp_et(order)
    if not ts:
        return None
    if trade_date_et and not ts.startswith(trade_date_et):
        return None

    side_qty = infer_side_qty(order)
    if not side_qty:
        return None

    symbol = extract_symbol(order)
    fill_price = _safe_float(
        order.get("price")
        or order.get("fillPrice")
        or order.get("FillPrice")
        or order.get("limitPrice")
        or order.get("LimitPrice"),
        0.0,
    )
    if fill_price <= 0:
        events = order.get("events") or order.get("Events") or []
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                fp = _safe_float(ev.get("fillPrice") or ev.get("FillPrice"), 0.0)
                if fp > 0:
                    fill_price = fp
                    break

    stop = _safe_float(order.get("stopPrice") or order.get("StopPrice"), 0.0)
    target = _safe_float(order.get("targetPrice") or order.get("TargetPrice"), 0.0)

    sp = stop_points.get(symbol, 50.0)
    tp = target_points.get(symbol, 100.0)

    if fill_price > 0 and (stop <= 0 or target <= 0):
        if side_qty["side"] == "BUY":
            stop = fill_price - sp
            target = fill_price + tp
        else:
            stop = fill_price + sp
            target = fill_price - tp

    oid = order.get("id") or order.get("Id") or order.get("orderId") or "?"
    return {
        "timestamp_et": ts,
        "strategy_id": "PF100_QC_BRIDGE",
        "symbol": symbol,
        "side": side_qty["side"],
        "qty": side_qty["qty"],
        "stop_price": round(stop, 4),
        "target_price": round(target, 4),
        "note": f"from_qc_order:{oid}",
    }


def dedupe_signals(signals: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for s in sorted(signals, key=lambda x: x["timestamp_et"]):
        key = (s["timestamp_et"], s["symbol"], s["side"], s["qty"], s["note"])
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def load_bridge_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser(description="Build phase0 paper signals from QuantConnect live orders")
    p.add_argument("--config", default="config/qc_signal_bridge.sample.json")
    p.add_argument("--qc-secrets", default=None, help="Path to quantconnect_access.json")
    p.add_argument("--output", default="", help="Output signals JSON path")
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    cfg = load_bridge_config((base / args.config).resolve())
    creds = load_qc_credentials(args.qc_secrets)

    project_id = int(cfg["project_id"])
    deploy_id = str(cfg.get("deploy_id", "") or "")
    trade_date_raw = str(cfg.get("trade_date_et", "") or "")
    start = int(cfg.get("start", 0))
    end = int(cfg.get("end", 500))
    stop_points = {str(k).upper(): float(v) for k, v in (cfg.get("default_stop_points") or {}).items()}
    target_points = {str(k).upper(): float(v) for k, v in (cfg.get("default_target_points") or {}).items()}
    allowed_symbols = {str(x).upper() for x in (cfg.get("allowed_symbols") or [])}

    trade_date_et: Optional[str]
    if trade_date_raw.lower() in {"latest", "auto", ""}:
        trade_date_et = None
    else:
        trade_date_et = trade_date_raw

    orders = fetch_live_orders(
        creds=creds,
        project_id=project_id,
        deploy_id=deploy_id,
        start=start,
        end=end,
    )

    raw: List[Dict[str, Any]] = []
    for o in orders:
        s = build_signal_from_order(o, trade_date_et, stop_points, target_points)
        if s:
            if allowed_symbols and str(s.get("symbol", "")).upper() not in allowed_symbols:
                continue
            raw.append(s)

    if trade_date_et is None and raw:
        latest_date = max(s["timestamp_et"][:10] for s in raw)
        raw = [s for s in raw if s["timestamp_et"].startswith(latest_date)]
        trade_date_et = latest_date

    signals = dedupe_signals(raw)

    if args.output:
        out = (base / args.output).resolve()
    else:
        date_suffix = trade_date_et or "unknown"
        out = (base / "config" / f"paper_day_signals.qc_{date_suffix}.json").resolve()

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals, indent=2), encoding="utf-8")

    summary = {
        "project_id": project_id,
        "deploy_id": deploy_id,
        "trade_date_et": trade_date_et or "",
        "orders_fetched": len(orders),
        "signals_built": len(signals),
        "output": str(out),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
