"""
PF100 fast-pass Stage 11:
- Keep base risk profile fixed (safe challenge profile)
- Tune second-entry extraction only
  * second_mom_entry_pct
  * second_risk_mult
  * second_target_atr_mult
- Phase A: CH_2025 filter
- Phase B: CH_2024 confirm for top CH_2025 survivors
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
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage11_second_entry_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage11_second_entry_results.txt")


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
    d = api_post("backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=90)
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
        by_day[date(dt.year, dt.month, dt.day)] += float(pnl)

    if not by_day:
        return {"pass_achieved": False, "calendar_days_to_pass": None, "trading_days_to_pass": 0}

    days = sorted(by_day.keys())
    first = days[0]
    cum = 0.0
    best = 0.0
    td = 0
    for d in days:
        pnl = by_day[d]
        if abs(pnl) > 1e-9:
            td += 1
        cum += pnl
        if pnl > best:
            best = pnl
        if cum >= target_usd and td >= min_days:
            c = best / cum if cum > 0 else None
            if c is not None and c <= consistency_limit:
                return {
                    "pass_achieved": True,
                    "calendar_days_to_pass": (d - first).days + 1,
                    "trading_days_to_pass": td,
                }
    return {"pass_achieved": False, "calendar_days_to_pass": None, "trading_days_to_pass": td}


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    out = {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
    }
    out.update(pass_metrics(bt))
    return out


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "trade_nq": 1,
        "trade_m2k": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.020,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_stop_atr_mult": 0.65,
        "second_max_hold_hours": 3,
        "max_trades_per_symbol_day": 2,
        "max_contracts_per_trade": 8,
        "pf1_maxc": 3,
        "risk_per_trade": 0.0125,
        "pf1_risk": 0.0090,
        "daily_loss_limit_pct": 0.040,
        "trailing_dd_limit_pct": 0.040,
    }


def candidates():
    b = base_cfg()
    out = []
    idx = 0
    for mom in (0.0018, 0.0022, 0.0025):
        for rm in (0.72, 0.80, 0.88, 0.95):
            for tgt in (1.20, 1.30):
                idx += 1
                c = dict(b)
                c["label"] = f"S11_{idx:02d}_M{int(mom*10000)}_R{int(rm*100)}_T{int(tgt*100)}"
                c["second_mom_entry_pct"] = mom
                c["second_risk_mult"] = rm
                c["second_target_atr_mult"] = tgt
                out.append(c)
    return out


def run_window(compile_id, params, candidate, window, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": candidate, "window": window, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest(compile_id, f"{candidate}_{window}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": candidate, "window": window, "error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": candidate, "window": window, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt)
    m.update({"candidate": candidate, "window": window})
    return m


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS STAGE11 SECOND ENTRY ===", ""]
    lines.append("Phase A (CH_2025)")
    for r in payload.get("phase_a", []):
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass={r.get('pass_achieved')} cal_days={r.get('calendar_days_to_pass')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Phase B (CH_2024 top)")
    for r in payload.get("phase_b", []):
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass={r.get('pass_achieved')} cal_days={r.get('calendar_days_to_pass')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} ch2025_days={r.get('ch2025_days')} ch2024_days={r.get('ch2024_days')} "
            f"np25={r.get('ch2025_np')} np24={r.get('ch2024_np')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    phase_a = []
    phase_b = []
    payload = {"phase_a": phase_a, "phase_b": phase_b, "ranked": []}
    save(payload)

    cfg_by_label = {c["label"]: c for c in candidates()}
    for c in cfg_by_label.values():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        m = run_window(compile_id, cfg, label, "CH_2025", 2025, 1, 1, 2025, 12, 31)
        phase_a.append(m)
        save(payload)
        print(
            f"A {label} pass={m.get('pass_achieved')} cal_days={m.get('calendar_days_to_pass')} "
            f"np={m.get('net_profit_pct')} dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')}"
        )
        time.sleep(2)

    survivors = []
    for r in phase_a:
        if (
            r.get("pass_achieved")
            and r.get("daily_loss_breaches") == 0
            and r.get("trailing_breaches") == 0
            and (r.get("calendar_days_to_pass") or 9999) <= 170
        ):
            survivors.append(r)
    survivors.sort(key=lambda x: ((x.get("calendar_days_to_pass") or 9999), -(x.get("net_profit_pct") or -999)))
    survivors = survivors[:6]

    bmap = {}
    for s in survivors:
        label = s["candidate"]
        cfg = {k: v for k, v in cfg_by_label[label].items() if k != "label"}
        m = run_window(compile_id, cfg, label, "CH_2024", 2024, 1, 1, 2024, 12, 31)
        phase_b.append(m)
        bmap[label] = m
        save(payload)
        print(
            f"B {label} pass={m.get('pass_achieved')} cal_days={m.get('calendar_days_to_pass')} "
            f"np={m.get('net_profit_pct')} dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')}"
        )
        time.sleep(2)

    ranked = []
    for s in survivors:
        label = s["candidate"]
        r24 = bmap.get(label, {})
        if not (
            r24.get("pass_achieved")
            and r24.get("daily_loss_breaches") == 0
            and r24.get("trailing_breaches") == 0
        ):
            continue
        d25 = s.get("calendar_days_to_pass") or 9999
        d24 = r24.get("calendar_days_to_pass") or 9999
        np25 = s.get("net_profit_pct") or 0.0
        np24 = r24.get("net_profit_pct") or 0.0
        score = (900 - d25 - d24) + (np25 + np24) * 5.0
        ranked.append(
            {
                "candidate": label,
                "ch2025_days": d25,
                "ch2024_days": d24,
                "ch2025_np": np25,
                "ch2024_np": np24,
                "score": round(score, 3),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    payload["ranked"] = ranked
    save(payload)


if __name__ == "__main__":
    main()
