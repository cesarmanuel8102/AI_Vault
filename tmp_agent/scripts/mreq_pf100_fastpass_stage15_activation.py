"""
PF100 FASTPASS Stage15 Activation
- Uses current main.py (PF100) with challenge lock
- Focus: reduce days_from_start by early activation
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage15_activation.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage15_activation.txt")


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
        p = str(s).split("-")
        return date(int(p[0]), int(p[1]), int(p[2])) if len(p) == 3 else None
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
        bid = (d.get("backtest") or {}).get("backtestId", "")
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
    hit = parse_bool_flag(rt.get("ChallengeTargetHit"))
    hit_date = parse_date(rt.get("ChallengeHitDate"))
    start = date(int(sy), int(sm), int(sd))
    days_start = None
    if hit and hit_date is not None:
        days_start = (hit_date - start).days + 1

    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "challenge_hit": hit,
        "challenge_days": parse_int(rt.get("ChallengeDaysToTarget")),
        "challenge_hit_date": rt.get("ChallengeHitDate"),
        "days_from_start": days_start,
    }


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "allow_shorts": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_entry_hour": 9,
        "second_entry_min": 55,
        "second_max_hold_hours": 2,
        "trailing_lock_mode": "EOD",
        "challenge_mode_enabled": 1,
        "challenge_lock_on_target": 1,
        "challenge_target_pct": 0.06,
        "challenge_min_trading_days": 0,
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 2,
        "pf1_w2win": 0,
        "pf1_tpd": 1,
        "pf1_stop": 0.42,
        "pf1_tgt": 1.35,
        "pf1_mom": 0.0005,
        "second_mom_entry_pct": 0.0008,
        "second_stop_atr_mult": 0.55,
        "second_target_atr_mult": 1.20,
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
    for use_vixy in (0, 1):
        for vixy in (1.000, 1.005, 1.010):
            for max_atr in (0.013, 0.020, 0.030):
                for max_gap in (0.0065, 0.0120, 0.0200):
                    for gap_mult in (0.22, 0.15):
                        for risk, pf1, maxc, pf1c, dloss, tdd in (
                            (0.020, 0.014, 10, 4, 0.040, 0.040),
                            (0.030, 0.020, 15, 6, 0.050, 0.050),
                        ):
                            i += 1
                            c = dict(b)
                            c["label"] = f"S15_{i:03d}_V{use_vixy}_A{int(max_atr*1000)}_G{int(max_gap*10000)}_M{int(gap_mult*100)}_R{int(risk*10000)}"
                            c["ext_use_vix"] = 0
                            c["ext_use_vixy"] = use_vixy
                            c["ext_vixy_sma_period"] = 5
                            c["ext_vixy_ratio_threshold"] = vixy
                            c["max_atr_pct"] = max_atr
                            c["max_gap_entry_pct"] = max_gap
                            c["gap_atr_mult"] = gap_mult
                            c["risk_per_trade"] = risk
                            c["pf1_risk"] = pf1
                            c["max_contracts_per_trade"] = maxc
                            c["pf1_maxc"] = pf1c
                            c["daily_loss_limit_pct"] = dloss
                            c["trailing_dd_limit_pct"] = tdd
                            rows.append(c)
    # deterministic shortlist: 24 diverse points
    pick = []
    for idx in [0,5,11,17,23,31,39,47,55,63,71,79,87,95,103,111,119,127,135,143,151,159,167,175]:
        if idx < len(rows):
            pick.append(rows[idx])
    return pick


def run_window(compile_id, params, candidate, window, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": candidate, "window": window, "error": f"set_parameters_failed: {upd}"}
    ok, bid, create = create_backtest_retry(compile_id, f"{candidate}_{window}_{int(time.time())}")
    if not ok or not bid:
        return {"candidate": candidate, "window": window, "error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bid)
    if not ok:
        return {"candidate": candidate, "window": window, "backtest_id": bid, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt, sy, sm, sd)
    m.update({"candidate": candidate, "window": window})
    return m


def score_row(r):
    if not r.get("challenge_hit"):
        return 10_000_000
    if (r.get("daily_loss_breaches") or 0) > 0 or (r.get("trailing_breaches") or 0) > 0:
        return 5_000_000 + (r.get("days_from_start") or 9999)
    return round((r.get("days_from_start") or 9999) * 1000 + (r.get("drawdown_pct") or 99.0) * 20.0, 3)


def save(payload):
    payload["updated_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 FASTPASS STAGE15 ACTIVATION ===", ""]
    lines.append("Phase A CH_2025")
    for r in payload.get("phase_a", []):
        lines.append(
            f"{r.get('candidate')} hit={r.get('challenge_hit')} start_d={r.get('days_from_start')} tr_d={r.get('challenge_days')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Phase B validation")
    for r in payload.get("phase_b", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} hit={r.get('challenge_hit')} start_d={r.get('days_from_start')} tr_d={r.get('challenge_days')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("Ranked")
    for r in payload.get("ranked", []):
        lines.append(
            f"{r.get('candidate')} score={r.get('score')} ch25_d={r.get('ch25_d')} ch24_d={r.get('ch24_d')} q1_np={r.get('q1_np')}"
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
    cfg_map = {c['label']: c for c in candidates()}

    for c in cfg_map.values():
        label = c['label']
        cfg = {k: v for k, v in c.items() if k != 'label'}
        r = run_window(compile_id, cfg, label, 'CH_2025', 2025, 1, 1, 2025, 12, 31)
        payload['phase_a'].append(r)
        save(payload)
        print(f"A {label} hit={r.get('challenge_hit')} start_d={r.get('days_from_start')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')}")
        time.sleep(2)

    survivors = [r for r in payload['phase_a'] if r.get('challenge_hit') and (r.get('daily_loss_breaches') or 0)==0 and (r.get('trailing_breaches') or 0)==0]
    survivors.sort(key=lambda x: ((x.get('days_from_start') or 9999), (x.get('drawdown_pct') or 99.0), -(x.get('net_profit_pct') or -999)))
    survivors = survivors[:6]

    for s in survivors:
        label = s['candidate']
        cfg = {k: v for k, v in cfg_map[label].items() if k != 'label'}
        r24 = run_window(compile_id, cfg, label, 'CH_2024', 2024, 1, 1, 2024, 12, 31)
        payload['phase_b'].append(r24)
        save(payload)
        print(f"B {label} CH_2024 hit={r24.get('challenge_hit')} start_d={r24.get('days_from_start')} np={r24.get('net_profit_pct')} dbr={r24.get('daily_loss_breaches')} tbr={r24.get('trailing_breaches')}")
        time.sleep(2)

        rq1 = run_window(compile_id, cfg, label, 'CH_2026_Q1', 2026, 1, 1, 2026, 3, 31)
        payload['phase_b'].append(rq1)
        save(payload)
        print(f"B {label} CH_2026_Q1 hit={rq1.get('challenge_hit')} start_d={rq1.get('days_from_start')} np={rq1.get('net_profit_pct')} dbr={rq1.get('daily_loss_breaches')} tbr={rq1.get('trailing_breaches')}")
        time.sleep(2)

    by = {}
    for r in payload['phase_a']:
        by.setdefault(r['candidate'], {})['CH_2025'] = r
    for r in payload['phase_b']:
        by.setdefault(r['candidate'], {})[r['window']] = r

    ranked = []
    for c, d in by.items():
        ch25 = d.get('CH_2025')
        if not ch25:
            continue
        ranked.append({
            'candidate': c,
            'score': score_row(ch25),
            'ch25_d': ch25.get('days_from_start'),
            'ch24_d': (d.get('CH_2024') or {}).get('days_from_start'),
            'q1_np': (d.get('CH_2026_Q1') or {}).get('net_profit_pct'),
        })
    ranked.sort(key=lambda x: x['score'])
    payload['ranked'] = ranked[:20]
    save(payload)


if __name__ == '__main__':
    main()
