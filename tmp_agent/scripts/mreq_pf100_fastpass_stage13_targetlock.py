"""
PF100 FASTPASS Stage 13 (target-lock):
- Adds challenge-mode lock-on-target logic from main.py
- Objective: minimize trading days to +6% target on CH_2025
- Evaluates both MNQ-only and MNQ+M2K variants
- Validates top survivors on CH_2024 and CH_2026_Q1
"""

import json
import time
from base64 import b64encode
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage13_targetlock.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage13_targetlock.txt")


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
    v = str(s).strip().lower()
    return v in ("1", "true", "yes")


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


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "challenge_hit": parse_bool_flag(rt.get("ChallengeTargetHit")),
        "challenge_days": parse_int(rt.get("ChallengeDaysToTarget")),
        "challenge_hit_date": rt.get("ChallengeHitDate"),
        "challenge_trading_days": parse_int(rt.get("ChallengeTradingDays")),
    }


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "allow_shorts": 1,
        "trade_nq": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_entry_hour": 10,
        "second_entry_min": 20,
        "trailing_lock_mode": "EOD",
        "challenge_mode_enabled": 1,
        "challenge_lock_on_target": 1,
        "challenge_target_pct": 0.06,
        "challenge_min_trading_days": 0,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "max_open_positions": 2,
        "max_trades_per_symbol_day": 2,
        "pf1_tpd": 1,
        "pf1_pt_on": 1,
        "pf1_ptf": 0.50,
        "pf1_t1r": 1.00,
        "pf1_w2win": 0,
        "second_max_hold_hours": 2,
        "flatten_hour": 15,
        "flatten_min": 58
    }


def candidates():
    b = base_cfg()
    rows = []
    i = 0

    seeds = [
        dict(vixy=1.010, r=0.0135, pf1=0.0105, sr=0.90, dloss=0.035, tdd=0.035, m2k=0, mom=0.0010, maxc=8, pf1max=3),
        dict(vixy=1.015, r=0.0150, pf1=0.0115, sr=1.00, dloss=0.040, tdd=0.040, m2k=0, mom=0.0010, maxc=8, pf1max=3),
        dict(vixy=1.015, r=0.0175, pf1=0.0130, sr=1.00, dloss=0.040, tdd=0.040, m2k=0, mom=0.0008, maxc=10, pf1max=4),
        dict(vixy=1.010, r=0.0135, pf1=0.0105, sr=0.90, dloss=0.035, tdd=0.035, m2k=1, mom=0.0010, maxc=6, pf1max=2),
        dict(vixy=1.015, r=0.0150, pf1=0.0115, sr=1.00, dloss=0.040, tdd=0.040, m2k=1, mom=0.0010, maxc=6, pf1max=2),
        dict(vixy=1.015, r=0.0175, pf1=0.0130, sr=1.00, dloss=0.045, tdd=0.045, m2k=1, mom=0.0008, maxc=8, pf1max=3),
    ]

    # generate with slight target/stop variants
    for s in seeds:
        for sec_tgt in (1.15, 1.30):
            for sec_stop in (0.55, 0.65):
                i += 1
                c = dict(b)
                c["label"] = f"S13_{i:02d}_M2K{s['m2k']}_R{int(round(s['r']*10000))}_SR{int(round(s['sr']*100))}_V{int(round(s['vixy']*1000))}_T{int(round(sec_tgt*100))}_S{int(round(sec_stop*100))}"
                c["trade_m2k"] = s["m2k"]
                c["ext_vixy_ratio_threshold"] = s["vixy"]
                c["risk_per_trade"] = s["r"]
                c["pf1_risk"] = s["pf1"]
                c["second_risk_mult"] = s["sr"]
                c["daily_loss_limit_pct"] = s["dloss"]
                c["trailing_dd_limit_pct"] = s["tdd"]
                c["second_mom_entry_pct"] = s["mom"]
                c["second_target_atr_mult"] = sec_tgt
                c["second_stop_atr_mult"] = sec_stop
                c["max_contracts_per_trade"] = s["maxc"]
                c["pf1_maxc"] = s["pf1max"]
                c["pf1_mom"] = 0.0006
                c["pf1_tgt"] = 1.40
                c["pf1_stop"] = 0.45
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


def score_row(ch25, ch24=None, q1=None):
    if not ch25.get("challenge_hit"):
        return 10_000_000
    if (ch25.get("daily_loss_breaches") or 0) > 0 or (ch25.get("trailing_breaches") or 0) > 0:
        return 5_000_000 + (ch25.get("challenge_days") or 9999)

    s = (ch25.get("challenge_days") or 9999) * 1000.0
    s += (ch25.get("drawdown_pct") or 99.0) * 20.0
    s += max(0.0, 8.0 - (ch25.get("net_profit_pct") or 0.0)) * 10.0

    if ch24 is not None:
        if not ch24.get("challenge_hit"):
            s += 800.0
        s += (ch24.get("challenge_days") or 9999) * 0.8
        s += ((ch24.get("daily_loss_breaches") or 0) + (ch24.get("trailing_breaches") or 0)) * 500.0

    if q1 is not None:
        s += max(0.0, 2.0 - (q1.get("net_profit_pct") or 0.0)) * 50.0
        s += ((q1.get("daily_loss_breaches") or 0) + (q1.get("trailing_breaches") or 0)) * 500.0

    return round(s, 3)


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS STAGE13 TARGET-LOCK ===", ""]
    lines.append("Phase A (CH_2025)")
    for r in payload.get("phase_a", []):
        lines.append(
            f"{r.get('candidate')} hit={r.get('challenge_hit')} d={r.get('challenge_days')} date={r.get('challenge_hit_date')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )

    lines.append("")
    lines.append("Phase B (Top Validation)")
    for r in payload.get("phase_b", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} hit={r.get('challenge_hit')} d={r.get('challenge_days')} date={r.get('challenge_hit_date')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )

    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} ch25_hit={r.get('ch25_hit')} ch25_days={r.get('ch25_days')} "
            f"ch24_hit={r.get('ch24_hit')} ch24_days={r.get('ch24_days')} q1_np={r.get('q1_np')}"
        )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
        raise RuntimeError(f"upload_failed: {up}")

    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    payload = {"phase_a": [], "phase_b": [], "ranked": []}
    save(payload)

    cfg_map = {c["label"]: c for c in candidates()}

    for c in cfg_map.values():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        m = run_window(compile_id, cfg, label, "CH_2025", 2025, 1, 1, 2025, 12, 31)
        payload["phase_a"].append(m)
        save(payload)
        print(
            f"A {label} hit={m.get('challenge_hit')} d={m.get('challenge_days')} "
            f"np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} "
            f"dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')}"
        )
        time.sleep(2)

    survivors = []
    for r in payload["phase_a"]:
        if (
            r.get("challenge_hit")
            and (r.get("daily_loss_breaches") or 0) == 0
            and (r.get("trailing_breaches") or 0) == 0
            and (r.get("challenge_days") or 9999) <= 90
        ):
            survivors.append(r)

    survivors.sort(
        key=lambda x: (
            x.get("challenge_days") or 9999,
            x.get("drawdown_pct") or 99.0,
            -(x.get("net_profit_pct") or -999),
        )
    )
    survivors = survivors[:8]

    for r in survivors:
        label = r["candidate"]
        cfg = {k: v for k, v in cfg_map[label].items() if k != "label"}
        m24 = run_window(compile_id, cfg, label, "CH_2024", 2024, 1, 1, 2024, 12, 31)
        payload["phase_b"].append(m24)
        save(payload)
        print(
            f"B {label} CH_2024 hit={m24.get('challenge_hit')} d={m24.get('challenge_days')} "
            f"np={m24.get('net_profit_pct')} dbr={m24.get('daily_loss_breaches')} tbr={m24.get('trailing_breaches')}"
        )
        time.sleep(2)

        mq1 = run_window(compile_id, cfg, label, "CH_2026_Q1", 2026, 1, 1, 2026, 3, 31)
        payload["phase_b"].append(mq1)
        save(payload)
        print(
            f"B {label} CH_2026_Q1 hit={mq1.get('challenge_hit')} d={mq1.get('challenge_days')} "
            f"np={mq1.get('net_profit_pct')} dbr={mq1.get('daily_loss_breaches')} tbr={mq1.get('trailing_breaches')}"
        )
        time.sleep(2)

    by_candidate = {}
    for r in payload["phase_a"]:
        by_candidate.setdefault(r["candidate"], {})["CH_2025"] = r
    for r in payload["phase_b"]:
        by_candidate.setdefault(r["candidate"], {})[r["window"]] = r

    ranked = []
    for c, d in by_candidate.items():
        ch25 = d.get("CH_2025")
        if not ch25:
            continue
        ch24 = d.get("CH_2024")
        q1 = d.get("CH_2026_Q1")
        ranked.append(
            {
                "candidate": c,
                "score": score_row(ch25, ch24, q1),
                "ch25_hit": ch25.get("challenge_hit"),
                "ch25_days": ch25.get("challenge_days"),
                "ch25_np": ch25.get("net_profit_pct"),
                "ch25_dd": ch25.get("drawdown_pct"),
                "ch24_hit": ch24.get("challenge_hit") if ch24 else None,
                "ch24_days": ch24.get("challenge_days") if ch24 else None,
                "q1_np": q1.get("net_profit_pct") if q1 else None,
            }
        )

    ranked.sort(key=lambda x: x["score"])
    payload["ranked"] = ranked[:20]
    save(payload)


if __name__ == "__main__":
    main()
