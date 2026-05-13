"""
Pass-Fast Stage 1 (MFFU-like rules)
- Uploads pass_fast_main.py as project main.py
- Runs challenge window backtests to estimate speed-to-pass
- Validates top candidates on OOS + STRESS
"""

import json
import statistics
import time
from base64 import b64encode
from collections import defaultdict
from datetime import datetime, date
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pass_fast_main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_stage1_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_stage1_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=8, backoff=3):
    last = None
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(min(backoff * (2**i), 45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} err={last}")


def parse_pct(s):
    try:
        return float(str(s).replace("%", "").replace(" ", "").replace(",", ""))
    except Exception:
        return None


def parse_num(s):
    try:
        return float(str(s).replace("$", "").replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(s):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


def upload_source(path):
    code = path.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)


def compile_project():
    c = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId", "")
    if not cid:
        return False, "", c
    for _ in range(120):
        r = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return st == "BuildSuccess", cid, r
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    return api_post("projects/update", payload, timeout=60)


def create_backtest(compile_id, name):
    d = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
        timeout=90,
    )
    bt = d.get("backtest", {})
    return bool(d.get("success")), bt.get("backtestId", ""), d


def poll_backtest(backtest_id, timeout_sec=2400):
    elapsed = 0
    while elapsed < timeout_sec:
        d = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
        bt = d.get("backtest", {})
        st = str(bt.get("status", ""))
        if "Completed" in st:
            time.sleep(2)
            d2 = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
            return True, d2.get("backtest", bt)
        if "Error" in st or "Runtime" in st:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def monthly_stats(bt):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    pstats = perf.get("portfolioStatistics", {}) or {}
    start_equity = parse_num(pstats.get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        key = f"{dt.year:04d}-{dt.month:02d}"
        by_month[key] += float(pnl)

    if not by_month:
        return {"monthly_mean_pct": None, "monthly_median_pct": None, "monthly_count": 0}

    eq = float(start_equity)
    rets = []
    for m in sorted(by_month.keys()):
        pnl = by_month[m]
        rets.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl
    return {
        "monthly_mean_pct": round(statistics.mean(rets), 3),
        "monthly_median_pct": round(statistics.median(rets), 3),
        "monthly_count": len(rets),
    }


def pass_metrics(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    by_day = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        key = date(dt.year, dt.month, dt.day)
        by_day[key] += float(pnl)

    if not by_day:
        return {
            "pass_achieved": False,
            "pass_date": None,
            "calendar_days_to_pass": None,
            "trading_days_to_pass": 0,
            "best_day_usd_at_pass": 0.0,
            "consistency_pct_at_pass": None,
        }

    days = sorted(by_day.keys())
    first_day = days[0]
    cum = 0.0
    best = 0.0
    trade_days = 0
    for d in days:
        day_pnl = by_day[d]
        if abs(day_pnl) > 1e-9:
            trade_days += 1
        cum += day_pnl
        if day_pnl > best:
            best = day_pnl
        if cum >= target_usd and trade_days >= min_days:
            consistency = (best / cum) if cum > 0 else None
            if consistency is not None and consistency <= consistency_limit:
                return {
                    "pass_achieved": True,
                    "pass_date": d.isoformat(),
                    "calendar_days_to_pass": (d - first_day).days + 1,
                    "trading_days_to_pass": trade_days,
                    "best_day_usd_at_pass": round(best, 2),
                    "consistency_pct_at_pass": round(consistency * 100.0, 2),
                }

    consistency_final = (best / cum) if cum > 0 else None
    return {
        "pass_achieved": False,
        "pass_date": None,
        "calendar_days_to_pass": None,
        "trading_days_to_pass": trade_days,
        "best_day_usd_at_pass": round(best, 2),
        "consistency_pct_at_pass": round(consistency_final * 100.0, 2) if consistency_final is not None else None,
    }


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    perf = bt.get("totalPerformance", {}) or {}
    closed = perf.get("closedTrades", []) or []
    m = {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "consistency_locks": parse_int(rt.get("ConsistencyLocks")),
        "price_guard_skips": parse_int(rt.get("PriceGuardSkips")),
        "best_day_usd": parse_num(rt.get("BestDayUSD")),
        "closed_trades": len(closed),
    }
    m.update(monthly_stats(bt))
    return m


def base_cfg():
    return {
        "allow_shorts": 1,
        "trade_mnq": 1,
        "trade_mes": 1,
        "trade_m2k": 0,
        "entry_start_hour": 9,
        "entry_start_min": 36,
        "entry_end_hour": 11,
        "entry_end_min": 30,
        "flatten_hour": 15,
        "flatten_min": 58,
        "daily_loss_limit_pct": 0.018,
        "trailing_dd_limit_pct": 0.035,
        "daily_profit_lock_usd": 1200,
        "consistency_day_profit_cap_usd": 1200,
        "evaluation_profit_target_usd": 3000,
        "consistency_pct_limit": 0.50,
        "max_contracts_per_trade": 5,
        "max_open_positions": 2,
        "max_trades_per_symbol_day": 1,
        "use_or_filter": 0,
        "min_gap_pct": 0.0,
        "max_gap_pct": 0.03,
    }


def candidates():
    b = base_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    add(
        "PFSTAGE1_A_BAL",
        risk_per_trade=0.0120,
        stop_atr_mult=0.90,
        target_atr_mult=1.90,
        trail_after_r_mult=1.0,
        trail_atr_mult=0.80,
        min_intraday_mom_pct=0.0008,
        require_trend_alignment=1,
        require_gap_alignment=0,
    )
    add(
        "PFSTAGE1_B_AGGR",
        risk_per_trade=0.0140,
        stop_atr_mult=0.85,
        target_atr_mult=2.10,
        trail_after_r_mult=1.0,
        trail_atr_mult=0.75,
        min_intraday_mom_pct=0.0006,
        require_trend_alignment=0,
        require_gap_alignment=0,
    )
    add(
        "PFSTAGE1_C_FREQ",
        risk_per_trade=0.0130,
        stop_atr_mult=0.85,
        target_atr_mult=1.80,
        trail_after_r_mult=0.8,
        trail_atr_mult=0.80,
        min_intraday_mom_pct=0.0005,
        max_trades_per_symbol_day=2,
        require_trend_alignment=0,
        require_gap_alignment=0,
    )
    add(
        "PFSTAGE1_D_M2K",
        risk_per_trade=0.0125,
        stop_atr_mult=0.90,
        target_atr_mult=1.90,
        trail_after_r_mult=1.0,
        trail_atr_mult=0.80,
        min_intraday_mom_pct=0.0007,
        trade_m2k=1,
        require_trend_alignment=0,
        require_gap_alignment=0,
    )
    add(
        "PFSTAGE1_E_SAFE",
        risk_per_trade=0.0110,
        stop_atr_mult=0.95,
        target_atr_mult=1.70,
        trail_after_r_mult=1.1,
        trail_atr_mult=0.85,
        min_intraday_mom_pct=0.0010,
        require_trend_alignment=1,
        require_gap_alignment=0,
    )
    add(
        "PFSTAGE1_F_ULTRA",
        risk_per_trade=0.0150,
        stop_atr_mult=0.80,
        target_atr_mult=2.20,
        trail_after_r_mult=0.9,
        trail_atr_mult=0.75,
        min_intraday_mom_pct=0.0004,
        max_trades_per_symbol_day=2,
        require_trend_alignment=0,
        require_gap_alignment=0,
    )
    return rows


def run_scenario(compile_id, label, params, scenario_name, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})

    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": label, "scenario": scenario_name, "error": f"set_parameters_failed: {upd}"}

    ok, bt_id, create = create_backtest(compile_id, f"{label}_{scenario_name}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "scenario": scenario_name, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "scenario": scenario_name, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = extract_metrics(bt)
    if scenario_name == "CHALLENGE_2025":
        m.update(pass_metrics(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2))
    m["candidate"] = label
    m["scenario"] = scenario_name
    return m


def stress_ok(m):
    if m.get("error"):
        return False
    npv = m.get("net_profit_pct")
    dbr = m.get("daily_loss_breaches") or 0
    tbr = m.get("trailing_breaches") or 0
    if npv is None:
        return False
    return dbr == 0 and tbr == 0 and npv > -2.0


def challenge_ok(m):
    if m.get("error"):
        return False
    dbr = m.get("daily_loss_breaches") or 0
    tbr = m.get("trailing_breaches") or 0
    return bool(m.get("pass_achieved")) and dbr == 0 and tbr == 0


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PASSFAST STAGE1 ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass={r.get('pass_achieved')} pass_date={r.get('pass_date')} "
            f"cal_days={r.get('calendar_days_to_pass')} tr_days={r.get('trading_days_to_pass')} "
            f"cons_at_pass={r.get('consistency_pct_at_pass')} best_day={r.get('best_day_usd_at_pass')} "
            f"closed={r.get('closed_trades')} m_mean={r.get('monthly_mean_pct')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
        raise RuntimeError(f"upload_failed: {up}")

    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    rows = []
    eligible = []
    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}

        # Stage 1 priority: challenge pass speed
        ch = run_scenario(compile_id, label, cfg, "CHALLENGE_2025", 2025, 1, 1, 2025, 12, 31)
        rows.append(ch)
        save(rows)
        print(
            f"{label} CH pass={ch.get('pass_achieved')} cal_days={ch.get('calendar_days_to_pass')} "
            f"cons={ch.get('consistency_pct_at_pass')} np={ch.get('net_profit_pct')} dbr={ch.get('daily_loss_breaches')} tbr={ch.get('trailing_breaches')}"
        )
        time.sleep(4)
        if challenge_ok(ch):
            eligible.append((label, cfg, ch))

    # shortlist by fastest pass then lowest dd
    eligible.sort(key=lambda x: (x[2].get("calendar_days_to_pass") or 999999, x[2].get("drawdown_pct") or 999))
    shortlist = eligible[:3]

    for label, cfg, _ in shortlist:
        stress = run_scenario(compile_id, label, cfg, "STRESS_2020", 2020, 1, 1, 2020, 12, 31)
        rows.append(stress)
        save(rows)
        print(
            f"{label} STRESS np={stress.get('net_profit_pct')} dd={stress.get('drawdown_pct')} "
            f"dbr={stress.get('daily_loss_breaches')} tbr={stress.get('trailing_breaches')}"
        )
        time.sleep(4)

        if not stress_ok(stress):
            continue

        oos = run_scenario(compile_id, label, cfg, "OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31)
        rows.append(oos)
        save(rows)
        print(
            f"{label} OOS np={oos.get('net_profit_pct')} dd={oos.get('drawdown_pct')} "
            f"m_mean={oos.get('monthly_mean_pct')}"
        )
        time.sleep(4)

        full = run_scenario(compile_id, label, cfg, "FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31)
        rows.append(full)
        save(rows)
        print(
            f"{label} FULL np={full.get('net_profit_pct')} dd={full.get('drawdown_pct')} "
            f"m_mean={full.get('monthly_mean_pct')}"
        )
        time.sleep(4)


if __name__ == "__main__":
    main()
