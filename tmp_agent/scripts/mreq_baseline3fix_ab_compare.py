"""
Compare baseline PF100 vs CALDENSITY-fixed variant on identical parameter sets.
Outputs:
- pf100_caldensity_ab_compare.json
- pf100_caldensity_ab_compare.txt
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

SRC_BASELINE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_before_caldensity_merge_2026-04-14.py")
SRC_CAL = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")

OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_baseline3fix_ab_compare.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_baseline3fix_ab_compare.txt")


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


def create_backtest_retry(compile_id, name, wait_sec=30, max_wait_rounds=12):
    for n in range(max_wait_rounds):
        d = api_post(
            "backtests/create",
            {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
            timeout=90,
        )
        bt = d.get("backtest", {})
        bid = bt.get("backtestId", "")
        if d.get("success") and bid:
            return True, bid, d
        errs = " | ".join(d.get("errors", []) or [])
        if "spare nodes" in errs.lower() or "nodes available" in errs.lower():
            time.sleep(wait_sec)
            continue
        return False, "", d
    return False, "", {"errors": [f"no_spare_nodes_after_{max_wait_rounds}_retries"], "success": False}


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
    out.update(pass_metrics(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2))
    return out


def configs():
    common = {
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.02,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_entry_hour": 10,
        "second_entry_min": 35,
        "second_mom_entry_pct": 0.0018,
        "second_stop_atr_mult": 0.6,
        "second_target_atr_mult": 1.2,
        "second_max_hold_hours": 2,
        "second_risk_mult": 0.6,
        "s2_block_red": 1,
        "s2_red_buf": 0.003,
        "max_trades_per_symbol_day": 2,
        "risk_per_trade": 0.0125,
        "pf1_risk": 0.009,
        "max_contracts_per_trade": 8,
        "pf1_maxc": 3,
        "daily_loss_limit_pct": 0.04,
        "trailing_dd_limit_pct": 0.04,
        "trade_nq": 1,
        "trade_mym": 0,
    }
    a = dict(common)
    a["label"] = "CFG_A_MNQ"
    a["trade_m2k"] = 0
    b = dict(common)
    b["label"] = "CFG_B_MNQ_M2K"
    b["trade_m2k"] = 1
    return [a, b]


def windows():
    return [
        ("CH_2024", 2024, 1, 1, 2024, 12, 31),
        ("CH_2025", 2025, 1, 1, 2025, 12, 31),
        ("CH_2026_Q1", 2026, 1, 1, 2026, 3, 31),
        ("STRESS_2020", 2020, 1, 1, 2020, 12, 31),
    ]


def run_one(compile_id, model_label, cfg_label, params, w):
    win, sy, sm, sd, ey, em, ed = w
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"model": model_label, "cfg": cfg_label, "window": win, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, created = create_backtest_retry(compile_id, f"{model_label}_{cfg_label}_{win}_{int(time.time())}")
    if not ok:
        return {"model": model_label, "cfg": cfg_label, "window": win, "error": f"create_backtest_failed: {created}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {
            "model": model_label,
            "cfg": cfg_label,
            "window": win,
            "backtest_id": bt_id,
            "error": f"poll_failed: {bt}",
        }
    m = extract_metrics(bt)
    m.update({"model": model_label, "cfg": cfg_label, "window": win})
    return m


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 CALDENSITY A/B ===", ""]
    for r in payload.get("rows", []):
        lines.append(
            f"{r.get('model')} {r.get('cfg')} {r.get('window')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} pass={r.get('pass_achieved')} "
            f"cal_days={r.get('calendar_days_to_pass')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Summary by model/cfg")
    for r in payload.get("summary", []):
        lines.append(
            f"{r.get('model')} {r.get('cfg')} score={r.get('score')} "
            f"ch24={r.get('ch24_np')} ch25={r.get('ch25_np')} q1={r.get('q1_np')} stress={r.get('stress_np')} "
            f"tbr_stress={r.get('stress_tbr')} pass25_days={r.get('ch25_days')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def summarize(rows):
    by = defaultdict(dict)
    for r in rows:
        if r.get("error"):
            continue
        by[(r["model"], r["cfg"])][r["window"]] = r
    out = []
    for (model, cfg), g in by.items():
        ch24 = g.get("CH_2024", {})
        ch25 = g.get("CH_2025", {})
        q1 = g.get("CH_2026_Q1", {})
        st = g.get("STRESS_2020", {})
        score = 0.0
        score += float(ch25.get("net_profit_pct") or 0.0) * 3.0
        score += float(ch24.get("net_profit_pct") or 0.0) * 1.5
        score += float(q1.get("net_profit_pct") or 0.0) * 1.0
        score += float(st.get("net_profit_pct") or 0.0) * 2.0
        if int(st.get("trailing_breaches") or 0) == 0:
            score += 4.0
        else:
            score -= 6.0
        if ch25.get("calendar_days_to_pass") is not None:
            score += max(0.0, (220 - ch25["calendar_days_to_pass"]) / 20.0)
        out.append(
            {
                "model": model,
                "cfg": cfg,
                "score": round(score, 3),
                "ch24_np": ch24.get("net_profit_pct"),
                "ch25_np": ch25.get("net_profit_pct"),
                "q1_np": q1.get("net_profit_pct"),
                "stress_np": st.get("net_profit_pct"),
                "stress_tbr": st.get("trailing_breaches"),
                "ch25_days": ch25.get("calendar_days_to_pass"),
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def run_model(model_label, source_path, rows):
    up = upload_source(source_path)
    if not up.get("success"):
        rows.append({"model": model_label, "error": f"upload_failed: {up}"})
        return
    ok, compile_id, comp = compile_project()
    if not ok:
        rows.append({"model": model_label, "error": f"compile_failed: {comp}"})
        return

    for cfg in configs():
        cfg_label = cfg["label"]
        params = {k: v for k, v in cfg.items() if k != "label"}
        for w in windows():
            r = run_one(compile_id, model_label, cfg_label, params, w)
            rows.append(r)
            print(
                f"{model_label} {cfg_label} {r.get('window')} np={r.get('net_profit_pct')} "
                f"tbr={r.get('trailing_breaches')} pass={r.get('pass_achieved')} days={r.get('calendar_days_to_pass')}"
            )
            save({"rows": rows, "summary": summarize(rows)})
            time.sleep(2)


def main():
    rows = []
    save({"rows": rows, "summary": []})
    run_model("BEFORE_3FIX", SRC_BASELINE, rows)
    run_model("AFTER_3FIX", SRC_CAL, rows)
    save({"rows": rows, "summary": summarize(rows)})


if __name__ == "__main__":
    main()
