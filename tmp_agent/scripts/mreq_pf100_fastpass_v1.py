"""
PF100_FASTPASS_V1 micro-grid.
Uploads main_fastpass_v1.py as main.py to QC and evaluates pass speed on 2025.
"""

import json
import time
from base64 import b64encode
from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_v1_main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_v1_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_v1_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    tok = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {tok}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=8):
    last = None
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(min(3 * (2**i), 45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} err={last}")


def parse_pct(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return None


def upload_source(path):
    code = path.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)


def compile_project():
    resp = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = resp.get("compileId", "")
    if not cid:
        return False, "", resp
    for _ in range(120):
        rd = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        state = rd.get("state", "")
        if state in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return state == "BuildSuccess", cid, rd
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    return api_post("projects/update", payload, timeout=60)


def create_backtest(compile_id, name):
    d = api_post("backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=90)
    bt = d.get("backtest", {})
    return bool(d.get("success")), bt.get("backtestId", ""), d


def poll_backtest(backtest_id, timeout_sec=2700):
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


def build_daily_pnl(bt):
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
        by_day[date(dt.year, dt.month, dt.day)] += float(pnl)
    return dict(sorted(by_day.items(), key=lambda x: x[0]))


def days_to_target(by_day, target_usd, consistency_limit=0.50, min_trade_days=2):
    if not by_day:
        return {
            "pass": False,
            "pass_date": None,
            "calendar_days": None,
            "trading_days": 0,
            "consistency_pct": None,
        }
    first_day = next(iter(by_day.keys()))
    cum = 0.0
    best_day = 0.0
    trade_days = 0
    for d, pnl in by_day.items():
        if abs(pnl) > 1e-9:
            trade_days += 1
        cum += pnl
        if pnl > best_day:
            best_day = pnl
        if cum >= target_usd and trade_days >= min_trade_days:
            cons = best_day / cum if cum > 0 else None
            if cons is not None and cons <= consistency_limit:
                return {
                    "pass": True,
                    "pass_date": d.isoformat(),
                    "calendar_days": (d - first_day).days + 1,
                    "trading_days": trade_days,
                    "consistency_pct": round(cons * 100.0, 2),
                }
    cons = best_day / cum if cum > 0 else None
    return {
        "pass": False,
        "pass_date": None,
        "calendar_days": None,
        "trading_days": trade_days,
        "consistency_pct": round(cons * 100.0, 2) if cons is not None else None,
    }


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    by_day = build_daily_pnl(bt)
    r4 = days_to_target(by_day, 2000.0)
    r6 = days_to_target(by_day, 3000.0)
    r8 = days_to_target(by_day, 4000.0)
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "consistency_pct": parse_pct(rt.get("ConsistencyPct")),
        "days_to_4pct": r4,
        "days_to_6pct": r6,
        "days_to_8pct": r8,
    }


def base_cfg():
    return {
        "allow_shorts": 1,
        "trade_mnq": 1,
        "trade_mes": 1,
        "trade_m2k": 0,
        "entry_start_hour": 9,
        "entry_start_min": 40,
        "entry_end_hour": 11,
        "entry_end_min": 30,
        "risk_per_trade": 0.0045,
        "max_contracts_per_trade": 2,
        "max_open_positions": 1,
        "max_trades_per_symbol_day": 2,
        "min_gap_pct": 0.0,
        "require_gap_alignment": 0,
        "min_intraday_mom_pct": 0.0004,
        "daily_loss_limit_pct": 0.0070,
        "trailing_dd_limit_pct": 0.0300,
        "daily_profit_lock_usd": 600,
        "pf1_w2win": 1,
        "pf1_pt_on": 1,
        "pf1_ptf": 0.50,
        "pf1_t1r": 1.00,
        "challenge_target_pct": 0.06,
    }


def candidates():
    b = base_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    add("FPV1_SEED")
    add(
        "FPV1_OR_LONGONLY",
        allow_shorts=0,
        use_or_filter=1,
        breakout_buffer_pct=0.0002,
        risk_per_trade=0.0100,
        stop_atr_mult=0.50,
        target_atr_mult=1.60,
        max_contracts_per_trade=3,
        max_trades_per_symbol_day=3,
        pf1_w2win=0,
        fastpass_risk_build=0.0100,
        fastpass_risk_cruise=0.0080,
        fastpass_risk_protect=0.0050,
    )
    add(
        "FPV1_MOM_LONGONLY",
        allow_shorts=0,
        use_or_filter=0,
        min_intraday_mom_pct=0.0006,
        risk_per_trade=0.0100,
        stop_atr_mult=0.45,
        target_atr_mult=1.45,
        max_contracts_per_trade=3,
        max_trades_per_symbol_day=3,
        pf1_w2win=0,
        fastpass_risk_build=0.0100,
        fastpass_risk_cruise=0.0080,
        fastpass_risk_protect=0.0050,
    )
    add(
        "FPV1_AGGR_MIX",
        allow_shorts=1,
        use_or_filter=1,
        breakout_buffer_pct=0.0003,
        risk_per_trade=0.0120,
        stop_atr_mult=0.45,
        target_atr_mult=1.70,
        max_contracts_per_trade=4,
        max_trades_per_symbol_day=3,
        pf1_w2win=0,
        fastpass_risk_build=0.0120,
        fastpass_risk_cruise=0.0090,
        fastpass_risk_protect=0.0060,
        fastpass_contracts_build=4,
        fastpass_contracts_cruise=3,
    )
    add(
        "FPV1_DEF_OR",
        allow_shorts=0,
        use_or_filter=1,
        breakout_buffer_pct=0.0004,
        risk_per_trade=0.0080,
        stop_atr_mult=0.55,
        target_atr_mult=1.35,
        max_contracts_per_trade=2,
        max_trades_per_symbol_day=2,
        pf1_w2win=1,
    )
    return rows


def run_challenge(compile_id, label, params):
    p = dict(params)
    p.update({"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2025, "end_month": 12, "end_day": 31})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": label, "error": f"set_parameters_failed: {upd}"}

    ok, bt_id, create = create_backtest(compile_id, f"{label}_CH2025_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = extract_metrics(bt)
    m["candidate"] = label
    return m


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS V1 ==="]
    for r in rows:
        d6 = r.get("days_to_6pct", {})
        d8 = r.get("days_to_8pct", {})
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"6%pass={d6.get('pass') if isinstance(d6, dict) else None} "
            f"6%days={d6.get('calendar_days') if isinstance(d6, dict) else None} "
            f"8%pass={d8.get('pass') if isinstance(d8, dict) else None} "
            f"8%days={d8.get('calendar_days') if isinstance(d8, dict) else None} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
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
    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        m = run_challenge(compile_id, label, cfg)
        rows.append(m)
        save(rows)
        d6 = m.get("days_to_6pct", {}) if isinstance(m, dict) else {}
        print(
            f"{label} np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} "
            f"tbr={m.get('trailing_breaches')} pass6={d6.get('pass')} "
            f"days6={d6.get('calendar_days')} id={m.get('backtest_id')}"
        )
        time.sleep(4)


if __name__ == "__main__":
    main()
