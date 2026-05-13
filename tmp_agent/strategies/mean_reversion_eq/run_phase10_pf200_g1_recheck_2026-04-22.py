import base64
import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase10_pf200_guardrail.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase10_pf200_g1_recheck_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase10_pf200_g1_recheck_2026-04-22.txt")


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
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
    if data.get("success", False):
        return data
    m = re.search(r"Server Time:\s*(\d+)", " ".join(data.get("errors") or []))
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return data


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


def perf_metrics(bt):
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    start = pf((perf.get("portfolioStatistics") or {}).get("startEquity")) or 50000.0
    by_month = defaultdict(float)
    by_day = defaultdict(float)
    gp, gl = 0.0, 0.0
    mcl, cur = 0, 0
    for t in trades:
        et = t.get("exitTime")
        pnl = t.get("profitLoss")
        if et is None or pnl is None:
            continue
        pnl = float(pnl)
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        by_month[f"{dt.year:04d}-{dt.month:02d}"] += pnl
        by_day[f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"] += pnl
        if pnl >= 0:
            gp += pnl
            cur = 0
        else:
            gl += abs(pnl)
            cur += 1
            mcl = max(mcl, cur)
    arr, eq = [], float(start)
    for k in sorted(by_month.keys()):
        pnl = by_month[k]
        arr.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl
    total = sum(by_day.values())
    best = max(by_day.values()) if by_day else 0.0
    return {
        "monthly_mean_pct": round(statistics.mean(arr), 3) if arr else None,
        "monthly_median_pct": round(statistics.median(arr), 3) if arr else None,
        "monthly_count": len(arr),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "max_consec_losses": int(mcl),
        "best_day_share_pct": round(999.0 if total <= 0 else (best / total) * 100.0, 2),
    }


def run_backtest(uid, tok, compile_id, name):
    bid = None
    err = None
    for _ in range(30):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(60)
            continue
        return {"status": "CreateFailed", "error": err}
    if not bid:
        return {"status": "CreateFailed", "error": err or "no id"}

    for _ in range(420):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            s = bt.get("statistics") or {}
            rt_stats = bt.get("runtimeStatistics") or {}
            row = {
                "status": st,
                "backtest_id": bid,
                "np_pct": pf(s.get("Net Profit")),
                "dd_pct": pf(s.get("Drawdown")),
                "dbr": pi(rt(rt_stats, "DailyLossBreaches")),
                "tbr": pi(rt(rt_stats, "TrailingBreaches")),
                "orders": pi(s.get("Total Orders")),
                "stress_days": pi(rt(rt_stats, "ExternalStressDays")),
            }
            row.update(perf_metrics(bt))
            return row
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": bt.get("error") or bt.get("message")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = creds()
    code = MAIN_PATH.read_text(encoding="utf-8")
    d = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not d.get("success", False):
        raise RuntimeError(d)
    d = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": []}, timeout=60)
    if not d.get("success", False):
        raise RuntimeError(d)
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
    }
    scenarios = [
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("FULL_2022_2026Q1", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
    ]

    rows = []
    for sc, dates in scenarios:
        p = dict(params)
        p.update(dates)
        d = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in p.items()]}, timeout=60)
        if not d.get("success", False):
            raise RuntimeError(d)
        r = run_backtest(uid, tok, cid, f"P10_G1_RECHECK_{sc}_{int(time.time())}")
        r.update({"candidate": "P10_G1_RECHECK", "scenario": sc})
        rows.append(r)
        OUT_JSON.write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": cid, "rows": rows}, indent=2), encoding="utf-8")

    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"compile_id={cid}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} "
            f"tbr={r.get('tbr')} m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} "
            f"pf={r.get('profit_factor')} max_l={r.get('max_consec_losses')} best_day%={r.get('best_day_share_pct')} "
            f"orders={r.get('orders')} stress_days={r.get('stress_days')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
