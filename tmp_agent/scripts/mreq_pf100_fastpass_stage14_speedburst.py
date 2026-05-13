"""
PF100 FASTPASS Stage 14 (speed burst)
- Uses challenge target lock in main.py
- Objective: minimize days from start to +6%
- Aggressive search around PF100 with constrained prop risk fences
"""

import json
import time
from base64 import b64encode
from datetime import datetime, date
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage14_speedburst.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage14_speedburst.txt")


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


def parse_bool_flag(s):
    return str(s).strip().lower() in ("1", "true", "yes")


def parse_date(s):
    try:
        parts = str(s).split("-")
        if len(parts) != 3:
            return None
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, m, d)
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


def extract_metrics(bt, sy=2025, sm=1, sd=1):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    perf = bt.get("totalPerformance", {}) or {}
    closed = perf.get("closedTrades", []) or []

    first_trade_day = None
    for tr in closed:
        et = tr.get("exitTime")
        if not et:
            continue
        t = parse_date(str(et)[:10])
        if t is None:
            continue
        if first_trade_day is None or t < first_trade_day:
            first_trade_day = t

    hit = parse_bool_flag(rt.get("ChallengeTargetHit"))
    hit_date = parse_date(rt.get("ChallengeHitDate"))
    start_day = date(int(sy), int(sm), int(sd))

    cal_days_from_start = None
    cal_days_from_first_trade = None
    if hit and hit_date is not None:
        cal_days_from_start = (hit_date - start_day).days + 1
        if first_trade_day is not None:
            cal_days_from_first_trade = (hit_date - first_trade_day).days + 1

    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "challenge_hit": hit,
        "challenge_days_trading": parse_int(rt.get("ChallengeDaysToTarget")),
        "challenge_hit_date": rt.get("ChallengeHitDate"),
        "days_from_start": cal_days_from_start,
        "days_from_first_trade": cal_days_from_first_trade,
    }


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "trade_nq": 1,
        "trade_mym": 0,
        "allow_shorts": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_entry_hour": 10,
        "second_entry_min": 10,
        "second_max_hold_hours": 2,
        "trailing_lock_mode": "EOD",
        "challenge_mode_enabled": 1,
        "challenge_lock_on_target": 1,
        "challenge_target_pct": 0.06,
        "challenge_min_trading_days": 0,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 3,
        "pf1_tpd": 1,
        "pf1_w2win": 0,
    }


def candidates():
    b = base_cfg()
    rows = []
    i = 0
    for m2k in (0, 1):
        for vixy in (1.005, 1.010, 1.015):
            for r, pf1, maxc, pf1max, dloss, tdd in (
                (0.020, 0.014, 10, 4, 0.040, 0.040),
                (0.025, 0.017, 12, 5, 0.045, 0.045),
                (0.030, 0.020, 15, 6, 0.050, 0.050),
            ):
                i += 1
                c = dict(b)
                c["label"] = f"S14_{i:02d}_M2K{m2k}_V{int(round(vixy*1000))}_R{int(r*10000)}"
                c["trade_m2k"] = m2k
                c["ext_vixy_ratio_threshold"] = vixy
                c["risk_per_trade"] = r
                c["pf1_risk"] = pf1
                c["max_contracts_per_trade"] = maxc
                c["pf1_maxc"] = pf1max
                c["daily_loss_limit_pct"] = dloss
                c["trailing_dd_limit_pct"] = tdd
                c["second_risk_mult"] = 1.20
                c["second_mom_entry_pct"] = 0.0008
                c["second_stop_atr_mult"] = 0.55
                c["second_target_atr_mult"] = 1.20
                c["pf1_stop"] = 0.42
                c["pf1_tgt"] = 1.35
                c["pf1_mom"] = 0.0005
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
    m = extract_metrics(bt, sy, sm, sd)
    m.update({"candidate": candidate, "window": window})
    return m


def score_row(r):
    if not r.get("challenge_hit"):
        return 10_000_000
    if (r.get("daily_loss_breaches") or 0) > 0 or (r.get("trailing_breaches") or 0) > 0:
        return 5_000_000 + (r.get("days_from_start") or 9999)
    s = (r.get("days_from_start") or 9999) * 1000.0
    s += (r.get("drawdown_pct") or 99.0) * 20.0
    return round(s, 3)


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS STAGE14 SPEED BURST ===", ""]
    for r in payload.get("results", []):
        lines.append(
            f"{r.get('candidate')} hit={r.get('challenge_hit')} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} tr_d={r.get('challenge_days_trading')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')}"
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

    cfgs = candidates()
    for c in cfgs:
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        r = run_window(compile_id, cfg, label, "CH_2025", 2025, 1, 1, 2025, 12, 31)
        payload["results"].append(r)
        save(payload)
        print(
            f"{label} hit={r.get('challenge_hit')} start_d={r.get('days_from_start')} first_d={r.get('days_from_first_trade')} "
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
