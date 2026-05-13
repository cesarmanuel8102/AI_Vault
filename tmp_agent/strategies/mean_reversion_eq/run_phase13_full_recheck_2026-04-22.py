import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase13_full_recheck_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase13_full_recheck_2026-04-22.txt")


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()


def hdr(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": str(ts), "Content-Type": "application/json"}


def post(uid, tok, ep, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts), json=payload, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        d = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        d.setdefault("success", False)
    if d.get("success", False):
        return d
    m = re.search(r"Server Time:\s*(\d+)", " ".join(d.get("errors") or []))
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return d


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def pi(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def rt(runtime, key):
    if isinstance(runtime, dict):
        return runtime.get(key)
    if isinstance(runtime, list):
        for it in runtime:
            if isinstance(it, dict) and str(it.get("name") or it.get("Name")) == key:
                return it.get("value") or it.get("Value")
    return None


def main():
    uid, tok = creds()
    code = MAIN_PATH.read_text(encoding="utf-8")
    u = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not u.get("success", False):
        raise RuntimeError(u)

    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(c)
    for _ in range(180):
        cr = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = cr.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(cr)
            break
        time.sleep(2)

    params = {
        "trade_mnq": 1,
        "trade_mes": 1,
        "allow_shorts": 1,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.04,
        "flatten_hour": 15,
        "flatten_min": 58,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_rv_threshold": 1.0,
        "ext_gap_abs_threshold": 1.0,
        "n_risk": 0.013,
        "or_risk": 0.010,
        "s_risk": 0.003,
        "max_contracts_per_trade": 12,
        "max_trades_per_symbol_day": 3,
        "or_minutes": 10,
        "or_breakout_buffer_pct": 0.0003,
        "or_target_atr_mult": 1.55,
        "or_stop_atr_mult": 0.75,
        "trailing_lock_mode": "EOD",
        "trailing_dd_limit_pct": 0.035,
        "guard_enabled": 1,
        "guard_block_entry_cushion_pct": 0.0045,
        "guard_soft_cushion_pct": 0.0080,
        "guard_hard_cushion_pct": 0.0055,
        "guard_soft_mult": 0.82,
        "guard_hard_mult": 0.65,
        "guard_day_lock_enabled": 1,
        "guard_red_pnl_lock_pct": -0.0015,
        "consistency_guard_enabled": 0,
        "start_year": 2018,
        "start_month": 1,
        "start_day": 1,
        "end_year": 2026,
        "end_month": 3,
        "end_day": 31,
    }
    su = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}, timeout=60)
    if not su.get("success", False):
        raise RuntimeError(su)

    bid = None
    for _ in range(40):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": f"P13_FULL_RECHECK_{int(time.time())}"}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45)
            continue
        raise RuntimeError(bc)
    if not bid:
        raise RuntimeError("no backtest id")

    bt = {}
    for _ in range(480):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st or any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            break
        time.sleep(10)

    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    s = bt.get("statistics") or {}
    rts = bt.get("runtimeStatistics") or {}
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "compile_id": cid,
        "backtest_id": bid,
        "status": bt.get("status"),
        "error": bt.get("error"),
        "stacktrace": bt.get("stacktrace"),
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "orders": pi(s.get("Total Orders")),
        "closed_trades": len(trades),
        "dbr": pi(rt(rts, "DailyLossBreaches")),
        "tbr": pi(rt(rts, "TrailingBreaches")),
        "stress_days": pi(rt(rts, "ExternalStressDays")),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    OUT_TXT.write_text("\n".join(f"{k}={v}" for k, v in out.items()) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()

