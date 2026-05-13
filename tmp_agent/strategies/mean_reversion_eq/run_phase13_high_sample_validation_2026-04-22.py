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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase13_high_sample_validation_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase13_high_sample_validation_2026-04-22.txt")


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Missing QC credentials")
    return uid, tok


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


def trade_metrics(bt):
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    start = pf((perf.get("portfolioStatistics") or {}).get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    by_day = defaultdict(float)
    gp, gl = 0.0, 0.0
    wins, losses = 0, 0
    max_l, cur_l = 0, 0

    for t in trades:
        et, pnl = t.get("exitTime"), t.get("profitLoss")
        if et is None or pnl is None:
            continue
        p = float(pnl)
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        by_month[f"{dt.year:04d}-{dt.month:02d}"] += p
        by_day[f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"] += p

        if p >= 0:
            gp += p
            wins += 1
            cur_l = 0
        else:
            gl += abs(p)
            losses += 1
            cur_l += 1
            max_l = max(max_l, cur_l)

    arr = []
    eq = float(start)
    for m in sorted(by_month.keys()):
        pnl = by_month[m]
        arr.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl

    total = sum(by_day.values())
    best = max(by_day.values()) if by_day else 0.0
    wr = 100.0 * wins / max(1, wins + losses)
    return {
        "closed_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wr, 2),
        "profit_factor_calc": round(gp / gl, 3) if gl > 0 else None,
        "max_consec_losses": int(max_l),
        "best_day_share_pct": round(999.0 if total <= 0 else (best / total) * 100.0, 2),
        "monthly_mean_pct": round(statistics.mean(arr), 3) if arr else None,
        "monthly_median_pct": round(statistics.median(arr), 3) if arr else None,
        "monthly_count": len(arr),
    }


def run_bt(uid, tok, cid, name):
    bid = None
    err = None
    for _ in range(40):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(45)
            continue
        return {"status": "CreateFailed", "error": err}
    if not bid:
        return {"status": "CreateFailed", "error": err or "no id"}

    for _ in range(480):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            s = bt.get("statistics") or {}
            rts = bt.get("runtimeStatistics") or {}
            row = {
                "status": st,
                "backtest_id": bid,
                "np_pct": pf(s.get("Net Profit")),
                "dd_pct": pf(s.get("Drawdown")),
                "dbr": pi(rt(rts, "DailyLossBreaches")),
                "tbr": pi(rt(rts, "TrailingBreaches")),
                "orders": pi(s.get("Total Orders")),
                "stress_days": pi(rt(rts, "ExternalStressDays")),
                "consistency_ratio_rt": pf(rt(rts, "ConsistencyRatioPct")),
            }
            row.update(trade_metrics(bt))
            return row
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": bt.get("error") or bt.get("message")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = creds()
    code = MAIN_PATH.read_text(encoding="utf-8")
    u = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not u.get("success", False):
        raise RuntimeError(u)

    clr = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": []}, timeout=60)
    if not clr.get("success", False):
        raise RuntimeError(clr)

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

    base = {
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
    }

    scenarios = [
        ("SEG_2018_2019", {"start_year": 2018, "start_month": 1, "start_day": 1, "end_year": 2019, "end_month": 12, "end_day": 31}),
        ("SEG_2020_STRESS", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("SEG_2021_2022", {"start_year": 2021, "start_month": 1, "start_day": 1, "end_year": 2022, "end_month": 12, "end_day": 31}),
        ("SEG_2023", {"start_year": 2023, "start_month": 1, "start_day": 1, "end_year": 2023, "end_month": 12, "end_day": 31}),
        ("SEG_2024", {"start_year": 2024, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("SEG_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("FULL_2018_2026Q1", {"start_year": 2018, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
    ]

    rows = []
    for sname, dates in scenarios:
        cfg = dict(base)
        cfg.update(dates)
        su = post(
            uid,
            tok,
            "projects/update",
            {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in cfg.items()]},
            timeout=60,
        )
        if not su.get("success", False):
            raise RuntimeError(su)
        rr = run_bt(uid, tok, cid, f"P13_SAMPLE_{sname}_{int(time.time())}")
        rr.update({"scenario": sname, "params": dates})
        rows.append(rr)
        OUT_JSON.write_text(
            json.dumps(
                {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": cid, "rows": rows},
                indent=2,
            ),
            encoding="utf-8",
        )

    non_overlap = [r for r in rows if str(r.get("scenario", "")).startswith("SEG_")]
    total_closed_non_overlap = sum(int(r.get("closed_trades") or 0) for r in non_overlap)
    total_closed_all = sum(int(r.get("closed_trades") or 0) for r in rows)
    all_clean = all(int(r.get("dbr") or 0) == 0 and int(r.get("tbr") or 0) == 0 for r in rows if r.get("np_pct") is not None)

    lines = [
        f"generated_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"compile_id={cid}",
        "",
    ]
    for r in rows:
        lines.append(
            f"{r.get('scenario')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
            f"closed_trades={r.get('closed_trades')} win_rate={r.get('win_rate_pct')} pf={r.get('profit_factor_calc')} "
            f"best_day%={r.get('best_day_share_pct')} orders={r.get('orders')} stress_days={r.get('stress_days')} "
            f"m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} id={r.get('backtest_id')}"
        )
    lines += [
        "",
        f"total_closed_trades_non_overlap={total_closed_non_overlap}",
        f"total_closed_trades_all_windows={total_closed_all}",
        f"all_windows_clean_breaches={all_clean}",
        "thresholds_reference: OOS>=200 closed trades, STRESS>=100 closed trades, total>=500 closed trades",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()

