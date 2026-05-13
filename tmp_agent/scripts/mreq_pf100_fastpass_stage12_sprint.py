"""
PF100 FASTPASS Stage 12 (sprint):
- Objective: minimum calendar days to +6% / +8% in CH_2025
- MNQ-only (trade_m2k=0)
- Phase A: CH_2025 sweep
- Phase B: CH_2024 + CH_2026_Q1 validation for top candidates
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage12_sprint.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage12_sprint.txt")


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


def days_to_target(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2):
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
        return {"achieved": False, "cal_days": None, "tr_days": 0}

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
                return {"achieved": True, "cal_days": (d - first).days + 1, "tr_days": td}
    return {"achieved": False, "cal_days": None, "tr_days": td}


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
    m6 = days_to_target(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2)
    m8 = days_to_target(bt, target_usd=4000.0, consistency_limit=0.50, min_days=2)
    out.update(
        {
            "pass6": m6["achieved"],
            "days6": m6["cal_days"],
            "trdays6": m6["tr_days"],
            "pass8": m8["achieved"],
            "days8": m8["cal_days"],
            "trdays8": m8["tr_days"],
        }
    )
    return out


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_entry_hour": 10,
        "second_entry_min": 35,
        "max_trades_per_symbol_day": 2,
        "max_contracts_per_trade": 8,
        "pf1_maxc": 3,
        "daily_loss_limit_pct": 0.040,
        "trailing_dd_limit_pct": 0.040,
    }


def candidates():
    b = base_cfg()
    rows = []
    i = 0
    for vixy in (1.015, 1.020, 1.025):
        for r, pf1 in ((0.0125, 0.009), (0.0150, 0.011), (0.0175, 0.013), (0.0200, 0.015)):
            for sr in (0.60, 0.80, 1.00):
                i += 1
                c = dict(b)
                c["label"] = f"S12_{i:02d}_V{int(round(vixy*1000))}_R{int(round(r*10000))}_SR{int(round(sr*100))}"
                c["ext_vixy_ratio_threshold"] = vixy
                c["risk_per_trade"] = r
                c["pf1_risk"] = pf1
                c["second_risk_mult"] = sr
                c["second_mom_entry_pct"] = 0.0018 if sr <= 0.80 else 0.0012
                c["second_stop_atr_mult"] = 0.60
                c["second_target_atr_mult"] = 1.20 if sr <= 0.80 else 1.35
                c["second_max_hold_hours"] = 2
                rows.append(c)
    return rows


def run_window(compile_id, params, candidate, window, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": candidate, "window": window, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest_retry(compile_id, f"{candidate}_{window}_{int(time.time())}")
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
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS STAGE12 SPRINT ===", ""]
    lines.append("Phase A (CH_2025)")
    for r in payload.get("phase_a", []):
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass6={r.get('pass6')} days6={r.get('days6')} pass8={r.get('pass8')} days8={r.get('days8')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Phase B (Top Validation)")
    for r in payload.get("phase_b", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass6={r.get('pass6')} days6={r.get('days6')} pass8={r.get('pass8')} days8={r.get('days8')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} ch25_days6={r.get('ch25_days6')} ch25_days8={r.get('ch25_days8')} "
            f"ch24_days6={r.get('ch24_days6')} q1_np={r.get('q1_np')}"
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

    cfg_map = {c["label"]: c for c in candidates()}

    for c in cfg_map.values():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        m = run_window(compile_id, cfg, label, "CH_2025", 2025, 1, 1, 2025, 12, 31)
        phase_a.append(m)
        save(payload)
        print(
            f"A {label} pass6={m.get('pass6')} days6={m.get('days6')} "
            f"pass8={m.get('pass8')} days8={m.get('days8')} np={m.get('net_profit_pct')} "
            f"dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')}"
        )
        time.sleep(2)

    survivors = []
    for r in phase_a:
        if (
            r.get("pass6")
            and r.get("daily_loss_breaches") == 0
            and r.get("trailing_breaches") == 0
            and (r.get("days6") or 9999) <= 90
        ):
            survivors.append(r)
    survivors.sort(
        key=lambda x: (
            x.get("days6") or 9999,
            x.get("days8") or 9999,
            -(x.get("net_profit_pct") or -999),
        )
    )
    survivors = survivors[:8]

    bmap = defaultdict(dict)
    for s in survivors:
        label = s["candidate"]
        cfg = {k: v for k, v in cfg_map[label].items() if k != "label"}
        for w, sy, sm, sd, ey, em, ed in (
            ("CH_2024", 2024, 1, 1, 2024, 12, 31),
            ("CH_2026_Q1", 2026, 1, 1, 2026, 3, 31),
        ):
            m = run_window(compile_id, cfg, label, w, sy, sm, sd, ey, em, ed)
            phase_b.append(m)
            bmap[label][w] = m
            save(payload)
            print(
                f"B {label} {w} pass6={m.get('pass6')} days6={m.get('days6')} "
                f"np={m.get('net_profit_pct')} dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')}"
            )
            time.sleep(2)

    ranked = []
    for s in survivors:
        label = s["candidate"]
        ch24 = bmap[label].get("CH_2024", {})
        q1 = bmap[label].get("CH_2026_Q1", {})
        if ch24.get("daily_loss_breaches") not in (0, None) or ch24.get("trailing_breaches") not in (0, None):
            continue
        score = 0.0
        score += 500 - float(s.get("days6") or 999)
        score += 200 - float(s.get("days8") or 999)
        score += float(s.get("net_profit_pct") or 0.0) * 5.0
        if ch24.get("pass6"):
            score += 20.0
        if q1.get("daily_loss_breaches") == 0 and q1.get("trailing_breaches") == 0:
            score += 10.0
        score += float(q1.get("net_profit_pct") or 0.0) * 2.0
        ranked.append(
            {
                "candidate": label,
                "score": round(score, 3),
                "ch25_days6": s.get("days6"),
                "ch25_days8": s.get("days8"),
                "ch24_days6": ch24.get("days6"),
                "q1_np": q1.get("net_profit_pct"),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    payload["ranked"] = ranked
    save(payload)


if __name__ == "__main__":
    main()
