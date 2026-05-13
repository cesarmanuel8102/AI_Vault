"""
PF100 fast-pass Stage 9:
- Micro-search around VIXY threshold/risk
- Phase A: CH_2025 + STRESS_2020 filter
- Phase B: full 4-window validation for top survivors
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
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_passspeed_stage9_crossfilter_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_passspeed_stage9_crossfilter_results.txt")


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
        return {"pass_achieved": False, "pass_date": None, "calendar_days_to_pass": None, "trading_days_to_pass": 0}

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
                    "pass_date": d.isoformat(),
                    "calendar_days_to_pass": (d - first).days + 1,
                    "trading_days_to_pass": td,
                }

    return {"pass_achieved": False, "pass_date": None, "calendar_days_to_pass": None, "trading_days_to_pass": td}


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
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_mom_entry_pct": 0.0025,
        "second_stop_atr_mult": 0.65,
        "second_target_atr_mult": 1.35,
        "second_risk_mult": 0.72,
        "second_max_hold_hours": 3,
        "max_trades_per_symbol_day": 2,
        "max_contracts_per_trade": 8,
        "pf1_maxc": 3,
        "pf1_risk": 0.0090,
        "daily_loss_limit_pct": 0.040,
        "trailing_dd_limit_pct": 0.040,
    }


def candidates():
    b = base_cfg()
    rows = []
    for vixy in (1.024, 1.026, 1.028, 1.030, 1.032):
        for r in (0.0110, 0.0115, 0.0120, 0.0125):
            c = dict(b)
            c["label"] = f"S9_V{int(round(vixy * 1000))}_R{int(round(r * 10000))}"
            c["ext_vixy_ratio_threshold"] = vixy
            c["risk_per_trade"] = r
            rows.append(c)
    return rows


def run_window(compile_id, params, label, win_label, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": label, "window": win_label, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest(compile_id, f"{label}_{win_label}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "window": win_label, "error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "window": win_label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt)
    m.update({"candidate": label, "window": win_label})
    return m


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 PASSSPEED STAGE9 CROSSFILTER ==="]
    lines.append("")
    lines.append("Phase A (CH_2025 + STRESS_2020)")
    for r in payload.get("phase_a", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} pass={r.get('pass_achieved')} "
            f"cal_days={r.get('calendar_days_to_pass')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Survivors")
    for s in payload.get("survivors", []):
        lines.append(
            f"{s.get('label')} ch2025_pass={s.get('ch2025_pass')} ch2025_days={s.get('ch2025_days')} "
            f"stress_np={s.get('stress_np')} stress_tbr={s.get('stress_tbr')} score={s.get('score')}"
        )
    lines.append("")
    lines.append("Phase B (full validate top)")
    for r in payload.get("phase_b", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} pass={r.get('pass_achieved')} "
            f"cal_days={r.get('calendar_days_to_pass')} err={r.get('error')} id={r.get('backtest_id')}"
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
    grouped = defaultdict(dict)
    payload = {"phase_a": phase_a, "survivors": [], "phase_b": []}
    save(payload)

    wins = [("CH_2025", 2025, 1, 1, 2025, 12, 31), ("STRESS_2020", 2020, 1, 1, 2020, 12, 31)]

    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        for wl, sy, sm, sd, ey, em, ed in wins:
            m = run_window(compile_id, cfg, label, wl, sy, sm, sd, ey, em, ed)
            phase_a.append(m)
            grouped[label][wl] = m
            save(payload)
            print(
                f"A {label} {wl} np={m.get('net_profit_pct')} tbr={m.get('trailing_breaches')} "
                f"pass={m.get('pass_achieved')} cal_days={m.get('calendar_days_to_pass')}"
            )
            time.sleep(2)

    survivors = []
    for label, g in grouped.items():
        ch = g.get("CH_2025", {})
        st = g.get("STRESS_2020", {})
        ch_pass = bool(ch.get("pass_achieved"))
        ch_days = ch.get("calendar_days_to_pass") if ch_pass else 9999
        st_np = st.get("net_profit_pct")
        st_tbr = st.get("trailing_breaches")
        st_dbr = st.get("daily_loss_breaches")
        if (
            ch_pass
            and ch_days is not None
            and ch_days <= 220
            and st_tbr == 0
            and st_dbr == 0
            and st_np is not None
            and st_np >= -0.5
        ):
            score = (200 - ch_days) + (st_np * 20.0)
            survivors.append(
                {
                    "label": label,
                    "params": next(x for x in candidates() if x["label"] == label),
                    "ch2025_pass": ch_pass,
                    "ch2025_days": ch_days,
                    "stress_np": st_np,
                    "stress_tbr": st_tbr,
                    "score": round(score, 3),
                }
            )

    survivors.sort(key=lambda x: x["score"], reverse=True)
    payload["survivors"] = survivors[:5]
    save(payload)

    phase_b = payload["phase_b"]
    full_windows = [
        ("CH_2024", 2024, 1, 1, 2024, 12, 31),
        ("CH_2025", 2025, 1, 1, 2025, 12, 31),
        ("CH_2026_Q1", 2026, 1, 1, 2026, 3, 31),
        ("STRESS_2020", 2020, 1, 1, 2020, 12, 31),
    ]

    for s in payload["survivors"][:3]:
        label = s["label"]
        cfg = {k: v for k, v in s["params"].items() if k != "label"}
        for wl, sy, sm, sd, ey, em, ed in full_windows:
            m = run_window(compile_id, cfg, label, wl, sy, sm, sd, ey, em, ed)
            phase_b.append(m)
            save(payload)
            print(
                f"B {label} {wl} np={m.get('net_profit_pct')} tbr={m.get('trailing_breaches')} "
                f"pass={m.get('pass_achieved')} cal_days={m.get('calendar_days_to_pass')}"
            )
            time.sleep(2)

    save(payload)


if __name__ == "__main__":
    main()
