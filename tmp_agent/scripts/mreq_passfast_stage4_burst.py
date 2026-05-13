"""
PassFast Stage4 Burst
- Uploads pass_fast_main.py to QC main.py
- Aggressive search for days to +6% (3000 USD) on CH_2025
"""

import json
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_stage4_burst_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_stage4_burst_results.txt")


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


def parse_int(s):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


def upload_source(path):
    code = path.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=90)


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
    return api_post("projects/update", payload, timeout=90)


def create_backtest_retry(compile_id, name, wait_sec=20, max_retries=20):
    for _ in range(max_retries):
        d = api_post("backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=90)
        bt = d.get("backtest", {})
        bid = bt.get("backtestId", "")
        if d.get("success") and bid:
            return True, bid, d
        errors = " | ".join(d.get("errors", []) or [])
        lower = errors.lower()
        if "spare nodes" in lower or "too many backtest requests" in lower or "slow down" in lower:
            time.sleep(wait_sec)
            continue
        return False, "", d
    return False, "", {"errors": ["create_backtest_retry_exhausted"], "success": False}


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
        if "Error" in st or "Runtime" in st or "Cancelled" in st:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def date_from_iso(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def days_to_target(bt, target_usd=3000.0, start_day=date(2025,1,1)):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    by_day = defaultdict(float)
    for tr in trades:
        d = date_from_iso(tr.get("exitTime"))
        pnl = tr.get("profitLoss")
        if d is None or pnl is None:
            continue
        by_day[d] += float(pnl)

    if not by_day:
        return None, None

    cum = 0.0
    first_trade = min(by_day.keys())
    for d in sorted(by_day.keys()):
        cum += by_day[d]
        if cum >= target_usd:
            return (d - start_day).days + 1, (d - first_trade).days + 1
    return None, None


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    d_start, d_first = days_to_target(bt, target_usd=3000.0)
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "days_from_start": d_start,
        "days_from_first_trade": d_first,
    }


def base_cfg():
    return {
        "trade_mnq": 1,
        "trade_mes": 1,
        "trade_m2k": 0,
        "allow_shorts": 1,
        "use_vixy_gate": 0,
        "or_minutes": 5,
        "use_or_filter": 0,
        "min_intraday_mom_pct": 0.0006,
        "require_trend_alignment": 0,
        "require_gap_alignment": 0,
        "min_gap_pct": 0.0005,
        "max_gap_pct": 0.03,
        "min_atr_pct": 0.0025,
        "max_atr_pct": 0.04,
        "max_open_positions": 2,
        "max_trades_per_symbol_day": 2,
        "entry_start_hour": 9,
        "entry_start_min": 36,
        "entry_end_hour": 12,
        "entry_end_min": 0,
        "flatten_hour": 15,
        "flatten_min": 58,
        "evaluation_profit_target_usd": 3000,
        "consistency_pct_limit": 0.80,
        "consistency_day_profit_cap_usd": 5000,
        "daily_profit_lock_usd": 5000,
        "start_year": 2025,
        "start_month": 1,
        "start_day": 1,
        "end_year": 2025,
        "end_month": 12,
        "end_day": 31,
    }


def candidates():
    b = base_cfg()
    rows = []
    i = 0
    for r in (0.015, 0.020, 0.025, 0.030):
        for stop, tgt in ((0.60, 1.20), (0.70, 1.40), (0.80, 1.60)):
            for dloss, tdd in ((0.025, 0.035), (0.030, 0.040), (0.035, 0.045)):
                i += 1
                c = dict(b)
                c["label"] = f"PFB4_{i:02d}_R{int(r*10000)}_S{int(stop*100)}_T{int(tgt*100)}_D{int(dloss*1000)}"
                c["risk_per_trade"] = r
                c["stop_atr_mult"] = stop
                c["target_atr_mult"] = tgt
                c["trail_after_r_mult"] = 0.8
                c["trail_atr_mult"] = 0.75
                c["max_contracts_per_trade"] = 8 if r <= 0.02 else 10
                c["daily_loss_limit_pct"] = dloss
                c["trailing_dd_limit_pct"] = tdd
                rows.append(c)
    return rows[:18]


def run_bt(compile_id, cfg, label):
    upd = set_parameters(cfg)
    if not upd.get("success"):
        return {"candidate": label, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest_retry(compile_id, f"{label}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt)
    m["candidate"] = label
    return m


def score_row(r):
    d = r.get("days_from_start")
    if d is None:
        return 10_000_000
    breaches = (r.get("daily_loss_breaches") or 0) + (r.get("trailing_breaches") or 0)
    if breaches > 0:
        return 5_000_000 + d
    return round(d * 1000 + (r.get("drawdown_pct") or 99.0) * 20, 3)


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PASSFAST STAGE4 BURST ===", ""]
    for r in payload.get("results", []):
        lines.append(
            f"{r.get('candidate')} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    payload = {"results": [], "ranked": []}
    save(payload)

    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        r = run_bt(compile_id, cfg, label)
        payload["results"].append(r)
        save(payload)
        print(
            f"{label} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')}"
        )
        time.sleep(2)

    ranked = []
    for r in payload["results"]:
        rr = dict(r)
        rr["score"] = score_row(r)
        ranked.append(rr)
    ranked.sort(key=lambda x: x["score"])
    payload["ranked"] = ranked[:20]
    save(payload)


if __name__ == "__main__":
    main()
