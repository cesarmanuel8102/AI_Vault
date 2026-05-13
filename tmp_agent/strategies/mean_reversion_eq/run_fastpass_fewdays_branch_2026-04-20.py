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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_fewdays_branch_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_fewdays_branch_2026-04-20.txt")


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

    for _ in range(320):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=90)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        if "Completed" in st:
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
            }
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(12)

    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = load_creds()

    # Baseline S4 currently in live.
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
        "start_year": "2026",
        "start_month": "1",
        "start_day": "1",
        "end_year": "2026",
        "end_month": "12",
        "end_day": "31",
    }

    restore_params = dict(base)

    candidates = [
        {"label": "FD0_S4_CONTROL", "overrides": {}},
        {
            "label": "FD1_R40",
            "overrides": {"risk_per_trade": "0.040", "pf1_risk": "0.028", "max_contracts_per_trade": "22", "pf1_maxc": "10"},
        },
        {
            "label": "FD2_R45",
            "overrides": {"risk_per_trade": "0.045", "pf1_risk": "0.032", "max_contracts_per_trade": "26", "pf1_maxc": "12"},
        },
        {
            "label": "FD3_R40_FREQ4",
            "overrides": {
                "risk_per_trade": "0.040",
                "pf1_risk": "0.028",
                "max_contracts_per_trade": "22",
                "pf1_maxc": "10",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
                "second_mom_entry_pct": "0.0005",
            },
        },
        {
            "label": "FD4_R42_FREQ4",
            "overrides": {
                "risk_per_trade": "0.042",
                "pf1_risk": "0.030",
                "max_contracts_per_trade": "24",
                "pf1_maxc": "11",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
                "second_mom_entry_pct": "0.0005",
            },
        },
        {
            "label": "FD5_EARLY2_R40",
            "overrides": {
                "risk_per_trade": "0.040",
                "pf1_risk": "0.028",
                "max_contracts_per_trade": "22",
                "pf1_maxc": "10",
                "second_entry_hour": "9",
                "second_entry_min": "47",
                "second_mom_entry_pct": "0.0004",
            },
        },
        {
            "label": "FD6_EARLY2_R42_FREQ4",
            "overrides": {
                "risk_per_trade": "0.042",
                "pf1_risk": "0.030",
                "max_contracts_per_trade": "24",
                "pf1_maxc": "11",
                "second_entry_hour": "9",
                "second_entry_min": "47",
                "second_mom_entry_pct": "0.0004",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
            },
        },
        {
            "label": "FD7_R40_NO_W2WIN",
            "overrides": {
                "risk_per_trade": "0.040",
                "pf1_risk": "0.028",
                "max_contracts_per_trade": "22",
                "pf1_maxc": "10",
                "pf1_w2win": "0",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
            },
        },
        {
            "label": "FD8_R42_OPENLOCK6",
            "overrides": {
                "risk_per_trade": "0.042",
                "pf1_risk": "0.030",
                "max_contracts_per_trade": "24",
                "pf1_maxc": "11",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
                "daily_profit_lock_pct": "0.06",
            },
        },
        {
            "label": "FD9_R45_OPENLOCK7",
            "overrides": {
                "risk_per_trade": "0.045",
                "pf1_risk": "0.032",
                "max_contracts_per_trade": "26",
                "pf1_maxc": "12",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
                "daily_profit_lock_pct": "0.07",
                "second_mom_entry_pct": "0.0004",
            },
        },
        {
            "label": "FD10_R48_OPENLOCK8",
            "overrides": {
                "risk_per_trade": "0.048",
                "pf1_risk": "0.034",
                "max_contracts_per_trade": "28",
                "pf1_maxc": "13",
                "max_trades_per_symbol_day": "4",
                "pf1_tpd": "3",
                "daily_profit_lock_pct": "0.08",
                "second_mom_entry_pct": "0.0004",
            },
        },
    ]

    windows = [
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
        "windows": [w["name"] for w in windows],
        "results": [],
    }

    try:
        set_params(uid, tok, base)
        cid = compile_project(uid, tok)
        results["compile_id"] = cid

        for c in candidates:
            for w in windows:
                p = dict(base)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = c["label"]
                set_params(uid, tok, p)
                run_name = f"FPFD_{c['label']}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, cid, run_name)
                r.update({"candidate": c["label"], "window": w["name"]})
                results["results"].append(r)
                OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        by = {}
        for r in results["results"]:
            by.setdefault(r["candidate"], {})[r["window"]] = r

        rank = []
        for label, m in by.items():
            ch25 = m.get("CH_2025", {})
            ch26 = m.get("CH_2026_Q1", {})
            oos = m.get("OOS_2025_2026Q1", {})
            stress = m.get("STRESS_2020", {})

            d25 = int(ch25.get("challenge_days") or 999)
            d26 = int(ch26.get("challenge_days") or 999)
            oos_np = float(oos.get("np_pct") or -999)
            oos_dd = float(oos.get("dd_pct") or 999)
            stress_np = float(stress.get("np_pct") or -999)
            stress_dd = float(stress.get("dd_pct") or 999)
            stress_tbr = int(stress.get("tbr") or 0)

            penalty = 0.0
            for x in (ch25, ch26):
                breaches = int(x.get("dbr") or 0) + int(x.get("tbr") or 0)
                penalty += 350000 * max(0, breaches)
                if not bool(x.get("challenge_hit")):
                    penalty += 250000

            # Prefer "few days" first, then preserve quality.
            speed_term = (d25 * 300) + (d26 * 350)
            quality_term = -(oos_np * 18) + (oos_dd * 16) - (stress_np * 8) + (stress_dd * 12) + (stress_tbr * 60)
            score = penalty + speed_term + quality_term

            rank.append(
                {
                    "candidate": label,
                    "score": round(score, 3),
                    "ch25_hit": bool(ch25.get("challenge_hit")),
                    "ch25_days": d25,
                    "ch25_dbr": int(ch25.get("dbr") or 0),
                    "ch25_tbr": int(ch25.get("tbr") or 0),
                    "ch26_hit": bool(ch26.get("challenge_hit")),
                    "ch26_days": d26,
                    "ch26_dbr": int(ch26.get("dbr") or 0),
                    "ch26_tbr": int(ch26.get("tbr") or 0),
                    "oos_np": oos_np,
                    "oos_dd": oos_dd,
                    "stress_np": stress_np,
                    "stress_dd": stress_dd,
                    "stress_tbr": stress_tbr,
                    "few_days_pass": bool(ch25.get("challenge_hit"))
                    and bool(ch26.get("challenge_hit"))
                    and (d25 <= 7)
                    and (d26 <= 7)
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
        "",
        "=== RESULTS ===",
    ]
    for r in results.get("results", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} orders={r.get('orders')} id={r.get('backtest_id')} err={r.get('error')}"
        )

    lines.append("")
    lines.append("=== RANKING ===")
    for x in results.get("ranking", []):
        lines.append(
            f"{x['candidate']} score={x['score']} FEW={x['few_days_pass']} CH25(hit={x['ch25_hit']} d={x['ch25_days']} b={x['ch25_dbr']}/{x['ch25_tbr']}) CH26(hit={x['ch26_hit']} d={x['ch26_days']} b={x['ch26_dbr']}/{x['ch26_tbr']}) OOS(np={x['oos_np']} dd={x['oos_dd']}) STRESS(np={x['stress_np']} dd={x['stress_dd']} tbr={x['stress_tbr']})"
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
                "top": (results.get("ranking") or [None])[0],
                "few_days_count": len(results.get("few_days_shortlist") or []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
