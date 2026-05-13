import base64
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_fewdays_branch2_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_fewdays_branch2_2026-04-20.txt")


def load_creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Credenciales QC invalidas")
    return uid, tok


def headers(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    basic = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {basic}", "Timestamp": str(ts), "Content-Type": "application/json"}


def api_post(uid, tok, endpoint, payload, timeout=90):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
        if "errors" not in data:
            data["errors"] = [f"HTTP {r.status_code}"]
    if data.get("success", False):
        return data
    errs = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return data


def parse_float(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def parse_bool(x):
    return str(x).strip().lower() in ("1", "true", "yes")


def get_rt(rt, key):
    if isinstance(rt, dict):
        return rt.get(key)
    if isinstance(rt, list):
        for item in rt:
            if isinstance(item, dict) and str(item.get("name") or item.get("Name")) == key:
                return item.get("value") or item.get("Value")
    return None


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    resp = api_post(uid, tok, "projects/update", payload, timeout=60)
    if not resp.get("success", False):
        raise RuntimeError(f"projects/update failed: {resp}")


def compile_project(uid, tok):
    c = api_post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=90)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(180):
        r = api_post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile no exitoso: {st} | {r}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=90)
    bid = ((bt.get("backtest") or {}).get("backtestId"))
    if not bid:
        return {"status": "CreateFailed", "error": str(bt)}

    def read_once():
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=90)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        s = b.get("statistics") or {}
        rt = b.get("runtimeStatistics") or {}
        return {
            "status": st,
            "backtest_id": bid,
            "np_pct": parse_float(s.get("Net Profit")),
            "dd_pct": parse_float(s.get("Drawdown")),
            "sharpe": parse_float(s.get("Sharpe Ratio")),
            "orders": parse_int(s.get("Total Orders")),
            "dbr": parse_int(get_rt(rt, "DailyLossBreaches")),
            "tbr": parse_int(get_rt(rt, "TrailingBreaches")),
            "challenge_hit": parse_bool(get_rt(rt, "ChallengeTargetHit")),
            "challenge_days": parse_int(get_rt(rt, "ChallengeDaysToTarget")),
            "error": b.get("error") or b.get("message"),
        }

    for _ in range(320):
        r = read_once()
        st = r["status"]
        if "Completed" in st:
            # QC sometimes returns empty stats in first completed read; retry few times.
            if (r["np_pct"] is None or r["dd_pct"] is None or r["orders"] is None):
                for _k in range(6):
                    time.sleep(8)
                    r2 = read_once()
                    if r2["np_pct"] is not None and r2["dd_pct"] is not None and r2["orders"] is not None:
                        return r2
                return r
            return r
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return r
        time.sleep(12)

    return {"status": "Timeout", "backtest_id": bid}


def calc_score(crow):
    ch25 = crow.get("CH_2025", {})
    ch26 = crow.get("CH_2026_Q1", {})
    oos = crow.get("OOS_2025_2026Q1", {})
    stress = crow.get("STRESS_2020", {})

    d25 = int(ch25.get("challenge_days") or 999)
    d26 = int(ch26.get("challenge_days") or 999)

    # If stage2 not present, keep neutral placeholders.
    oos_np = float(oos.get("np_pct") or 0.0)
    oos_dd = float(oos.get("dd_pct") or 999.0) if oos else 999.0
    stress_np = float(stress.get("np_pct") or 0.0)
    stress_dd = float(stress.get("dd_pct") or 999.0) if stress else 999.0
    stress_tbr = int(stress.get("tbr") or 0)

    penalty = 0.0
    for x in (ch25, ch26):
        breaches = int(x.get("dbr") or 0) + int(x.get("tbr") or 0)
        penalty += 400000 * max(0, breaches)
        if not bool(x.get("challenge_hit")):
            penalty += 300000

    speed_term = (d25 * 500) + (d26 * 650)
    quality_term = -(oos_np * 16) + (oos_dd * 10) - (stress_np * 6) + (stress_dd * 7) + (stress_tbr * 80)
    return round(penalty + speed_term + quality_term, 3)


def main():
    uid, tok = load_creds()

    base = {
        "label": "PF100_FASTPASS_S4_BLEND_35_FREQ",
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "entry_hour": "9",
        "entry_min": "40",
        "second_entry_enabled": "1",
        "second_entry_hour": "9",
        "second_entry_min": "55",
        "risk_per_trade": "0.035",
        "pf1_risk": "0.024",
        "max_contracts_per_trade": "18",
        "pf1_maxc": "8",
        "max_open_positions": "2",
        "max_trades_per_symbol_day": "3",
        "pf1_tpd": "2",
        "daily_loss_limit_pct": "0.05",
        "daily_profit_lock_pct": "0.04",
        "trailing_dd_limit_pct": "0.05",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_vixy_ratio_threshold": "1.0",
        "ext_use_vix": "0",
        "ext_vix_threshold": "25",
        "ext_min_signals": "1",
        "gap_atr_mult": "0.15",
        "max_gap_entry_pct": "0.0065",
        "second_mom_entry_pct": "0.0006",
        "pf1_stop": "0.42",
        "pf1_tgt": "1.35",
        "pf1_mom": "0.0005",
        "pf1_rng": "0.01",
        "pf1_gap_thr": "0.004",
        "challenge_mode_enabled": "1",
        "challenge_lock_on_target": "1",
        "trade_nq": "1",
        "trade_m2k": "0",
        "start_year": "2026",
        "start_month": "1",
        "start_day": "1",
        "end_year": "2026",
        "end_month": "12",
        "end_day": "31",
    }

    restore_params = dict(base)

    candidates = [
        {"label": "B0_S4_CONTROL", "overrides": {}},
        {"label": "B1_R45_RELAX1", "overrides": {
            "risk_per_trade": "0.045", "pf1_risk": "0.032", "max_contracts_per_trade": "26", "pf1_maxc": "12",
            "gap_atr_mult": "0.12", "max_gap_entry_pct": "0.0080", "pf1_gap_thr": "0.0030", "second_mom_entry_pct": "0.0004",
            "second_entry_min": "47"
        }},
        {"label": "B2_R50_RELAX1", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "gap_atr_mult": "0.12", "max_gap_entry_pct": "0.0080", "pf1_gap_thr": "0.0030", "second_mom_entry_pct": "0.0004",
            "second_entry_min": "47", "daily_profit_lock_pct": "0.06"
        }},
        {"label": "B3_R50_RELAX2", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "gap_atr_mult": "0.10", "max_gap_entry_pct": "0.0100", "pf1_gap_thr": "0.0025", "pf1_rng": "0.0080",
            "pf1_mom": "0.0003", "second_mom_entry_pct": "0.0003", "second_entry_min": "45", "daily_profit_lock_pct": "0.07"
        }},
        {"label": "B4_R55_RELAX2", "overrides": {
            "risk_per_trade": "0.055", "pf1_risk": "0.040", "max_contracts_per_trade": "34", "pf1_maxc": "16",
            "gap_atr_mult": "0.10", "max_gap_entry_pct": "0.0100", "pf1_gap_thr": "0.0025", "pf1_rng": "0.0080",
            "pf1_mom": "0.0003", "second_mom_entry_pct": "0.0003", "second_entry_min": "45", "daily_profit_lock_pct": "0.08"
        }},
        {"label": "B5_R50_RELAX2_M2K", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.034", "max_contracts_per_trade": "28", "pf1_maxc": "12",
            "trade_m2k": "1", "max_open_positions": "3", "gap_atr_mult": "0.10", "max_gap_entry_pct": "0.0100",
            "pf1_gap_thr": "0.0025", "second_mom_entry_pct": "0.0003", "daily_profit_lock_pct": "0.07"
        }},
        {"label": "B6_R48_EARLY", "overrides": {
            "entry_min": "35", "second_entry_min": "45", "risk_per_trade": "0.048", "pf1_risk": "0.034",
            "max_contracts_per_trade": "28", "pf1_maxc": "13", "gap_atr_mult": "0.11", "pf1_gap_thr": "0.0028",
            "second_mom_entry_pct": "0.0003"
        }},
        {"label": "B7_R50_EXT103", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "ext_vixy_ratio_threshold": "1.03", "ext_min_signals": "2", "gap_atr_mult": "0.12", "pf1_gap_thr": "0.0030"
        }},
        {"label": "B8_R50_EXT104", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "ext_vixy_ratio_threshold": "1.04", "ext_min_signals": "2", "gap_atr_mult": "0.12", "pf1_gap_thr": "0.0030"
        }},
        {"label": "B9_R50_NO_VIXY", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "ext_use_vixy": "0", "ext_use_vix": "0", "gap_atr_mult": "0.11", "pf1_gap_thr": "0.0028"
        }},
        {"label": "B10_R45_RELAX3", "overrides": {
            "risk_per_trade": "0.045", "pf1_risk": "0.032", "max_contracts_per_trade": "26", "pf1_maxc": "12",
            "pf1_tgt": "1.50", "second_target_atr_mult": "1.25", "daily_profit_lock_pct": "0.08",
            "gap_atr_mult": "0.11", "pf1_gap_thr": "0.0028", "second_mom_entry_pct": "0.0003"
        }},
        {"label": "B11_R50_RELAX3", "overrides": {
            "risk_per_trade": "0.050", "pf1_risk": "0.036", "max_contracts_per_trade": "30", "pf1_maxc": "14",
            "pf1_tgt": "1.50", "second_target_atr_mult": "1.25", "daily_profit_lock_pct": "0.10",
            "gap_atr_mult": "0.11", "pf1_gap_thr": "0.0028", "second_mom_entry_pct": "0.0003", "second_entry_min": "45"
        }},
    ]

    stage1_windows = [
        {
            "name": "CH_2025",
            "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2025", "end_month": "12", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "1", "challenge_lock_on_target": "1"},
        },
        {
            "name": "CH_2026_Q1",
            "dates": {"start_year": "2026", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "1", "challenge_lock_on_target": "1"},
        },
    ]

    stage2_windows = [
        {
            "name": "OOS_2025_2026Q1",
            "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "0", "challenge_lock_on_target": "0"},
        },
        {
            "name": "STRESS_2020",
            "dates": {"start_year": "2020", "start_month": "1", "start_day": "1", "end_year": "2020", "end_month": "12", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "0", "challenge_lock_on_target": "0"},
        },
    ]

    results = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": PROJECT_ID,
        "base_label": base["label"],
        "candidates": [c["label"] for c in candidates],
        "stage1_windows": [w["name"] for w in stage1_windows],
        "stage2_windows": [w["name"] for w in stage2_windows],
        "results": [],
    }

    try:
        set_params(uid, tok, base)
        cid = compile_project(uid, tok)
        results["compile_id"] = cid

        by = {c["label"]: {} for c in candidates}

        # Stage 1: challenge speed
        for c in candidates:
            for w in stage1_windows:
                p = dict(base)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = c["label"]
                set_params(uid, tok, p)
                run_name = f"FPFD2_S1_{c['label']}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, cid, run_name)
                r.update({"candidate": c["label"], "window": w["name"], "stage": "S1"})
                results["results"].append(r)
                by[c["label"]][w["name"]] = r
                OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        # shortlist by strict few-days criteria
        shortlist = []
        for c in candidates:
            label = c["label"]
            ch25 = by[label].get("CH_2025", {})
            ch26 = by[label].get("CH_2026_Q1", {})
            ok = (
                bool(ch25.get("challenge_hit"))
                and bool(ch26.get("challenge_hit"))
                and int(ch25.get("challenge_days") or 999) <= 7
                and int(ch26.get("challenge_days") or 999) <= 7
                and int(ch25.get("dbr") or 0) == 0
                and int(ch25.get("tbr") or 0) == 0
                and int(ch26.get("dbr") or 0) == 0
                and int(ch26.get("tbr") or 0) == 0
            )
            if ok:
                shortlist.append(label)

        # if none strict, keep top 4 by speed and no breaches
        if not shortlist:
            def key_speed(label):
                ch25 = by[label].get("CH_2025", {})
                ch26 = by[label].get("CH_2026_Q1", {})
                breaches = int(ch25.get("dbr") or 0) + int(ch25.get("tbr") or 0) + int(ch26.get("dbr") or 0) + int(ch26.get("tbr") or 0)
                dsum = int(ch25.get("challenge_days") or 999) + int(ch26.get("challenge_days") or 999)
                hitpen = 0 if (bool(ch25.get("challenge_hit")) and bool(ch26.get("challenge_hit"))) else 1000
                return (breaches, hitpen, dsum)

            labels = [c["label"] for c in candidates]
            labels.sort(key=key_speed)
            shortlist = labels[:4]

        results["stage2_candidates"] = shortlist
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        # Stage 2: robustness check for shortlist only
        cand_map = {c["label"]: c for c in candidates}
        for label in shortlist:
            c = cand_map[label]
            for w in stage2_windows:
                p = dict(base)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = label
                set_params(uid, tok, p)
                run_name = f"FPFD2_S2_{label}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, cid, run_name)
                r.update({"candidate": label, "window": w["name"], "stage": "S2"})
                results["results"].append(r)
                by[label][w["name"]] = r
                OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        rank = []
        for label in [c["label"] for c in candidates]:
            row = by.get(label, {})
            score = calc_score(row)
            ch25 = row.get("CH_2025", {})
            ch26 = row.get("CH_2026_Q1", {})
            oos = row.get("OOS_2025_2026Q1", {})
            stress = row.get("STRESS_2020", {})
            rank.append(
                {
                    "candidate": label,
                    "score": score,
                    "stage2_ran": bool(oos) and bool(stress),
                    "ch25_hit": bool(ch25.get("challenge_hit")),
                    "ch25_days": int(ch25.get("challenge_days") or 999),
                    "ch25_dbr": int(ch25.get("dbr") or 0),
                    "ch25_tbr": int(ch25.get("tbr") or 0),
                    "ch26_hit": bool(ch26.get("challenge_hit")),
                    "ch26_days": int(ch26.get("challenge_days") or 999),
                    "ch26_dbr": int(ch26.get("dbr") or 0),
                    "ch26_tbr": int(ch26.get("tbr") or 0),
                    "oos_np": float(oos.get("np_pct") or 0.0) if oos else None,
                    "oos_dd": float(oos.get("dd_pct") or 0.0) if oos else None,
                    "stress_np": float(stress.get("np_pct") or 0.0) if stress else None,
                    "stress_dd": float(stress.get("dd_pct") or 0.0) if stress else None,
                    "stress_tbr": int(stress.get("tbr") or 0) if stress else None,
                    "few_days_pass": bool(ch25.get("challenge_hit"))
                    and bool(ch26.get("challenge_hit"))
                    and int(ch25.get("challenge_days") or 999) <= 7
                    and int(ch26.get("challenge_days") or 999) <= 7
                    and int(ch25.get("dbr") or 0) == 0
                    and int(ch25.get("tbr") or 0) == 0
                    and int(ch26.get("dbr") or 0) == 0
                    and int(ch26.get("tbr") or 0) == 0,
                }
            )

        rank.sort(key=lambda x: x["score"])
        results["ranking"] = rank
        results["few_days_shortlist"] = [x for x in rank if x["few_days_pass"]]

    finally:
        set_params(uid, tok, restore_params)

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"generated_at_utc={results.get('generated_at_utc')}",
        f"project_id={PROJECT_ID}",
        f"compile_id={results.get('compile_id','')}",
        f"base_label={base['label']}",
        f"stage2_candidates={results.get('stage2_candidates',[])}",
        "",
        "=== RESULTS ===",
    ]
    for r in results.get("results", []):
        lines.append(
            f"{r.get('stage')} {r.get('candidate')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} orders={r.get('orders')} id={r.get('backtest_id')} err={r.get('error')}"
        )

    lines.append("")
    lines.append("=== RANKING ===")
    for x in results.get("ranking", []):
        lines.append(
            f"{x['candidate']} score={x['score']} S2={x['stage2_ran']} FEW={x['few_days_pass']} CH25(hit={x['ch25_hit']} d={x['ch25_days']} b={x['ch25_dbr']}/{x['ch25_tbr']}) CH26(hit={x['ch26_hit']} d={x['ch26_days']} b={x['ch26_dbr']}/{x['ch26_tbr']}) OOS(np={x['oos_np']} dd={x['oos_dd']}) STRESS(np={x['stress_np']} dd={x['stress_dd']} tbr={x['stress_tbr']})"
        )

    lines.append("")
    lines.append("=== FEW_DAYS_SHORTLIST ===")
    for x in results.get("few_days_shortlist", []):
        lines.append(
            f"{x['candidate']} CH25={x['ch25_days']}d CH26={x['ch26_days']}d OOS={x['oos_np']} STRESS={x['stress_np']}"
        )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out_json": str(OUT_JSON),
                "out_txt": str(OUT_TXT),
                "stage2_candidates": results.get("stage2_candidates", []),
                "top": (results.get("ranking") or [None])[0],
                "few_days_count": len(results.get("few_days_shortlist") or []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
