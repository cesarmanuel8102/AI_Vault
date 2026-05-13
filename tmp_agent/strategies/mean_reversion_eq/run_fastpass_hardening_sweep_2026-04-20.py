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
CODE_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_hardening_sweep_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/fastpass_hardening_sweep_2026-04-20.txt")


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
    r.raise_for_status()
    data = r.json()
    if data.get("success", False):
        return data
    errs = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
        r2.raise_for_status()
        return r2.json()
    return data


def upload_code(uid, tok):
    code = CODE_PATH.read_text(encoding="utf-8")
    resp = api_post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=120)
    if not resp.get("success", False):
        raise RuntimeError(f"files/update failed: {resp}")


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
                "cost_blocks": parse_int(get_rt(rt, "CostGuardBlocks")),
                "expo_blocks": parse_int(get_rt(rt, "ExpoGuardBlocks")),
            }
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(12)

    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = load_creds()

    base = {
        "label": "S4_BLEND_35_FREQ",
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
        "daily_loss_limit_pct": "0.05",
        "trailing_dd_limit_pct": "0.05",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_vixy_ratio_threshold": "1.0",
        "ext_use_vix": "0",
        "ext_min_signals": "1",
        "gap_atr_mult": "0.15",
        "max_gap_entry_pct": "0.0065",
        "second_mom_entry_pct": "0.0006",
        "pf1_stop": "0.42",
        "pf1_tgt": "1.35",
        "pf1_mom": "0.0005",
        "pf1_rng": "0.01",
        "pf1_gap_thr": "0.004",
        "pf1_tpd": "2",
        "max_trades_per_symbol_day": "3",
        "challenge_mode_enabled": "1",
        "challenge_lock_on_target": "1",
        "live_safety_enabled": "1",
        "live_order_error_lock_enabled": "1",
        "live_max_order_errors_per_day": "3",
        "max_price_staleness_minutes": "5",
        "trailing_dd_buffer_pct": "0.0",
        "trade_cost_guard_enabled": "0",
        "roundtrip_fee_per_contract_usd": "1.40",
        "min_reward_to_fee_mult": "3.0",
        "net_exposure_guard_enabled": "0",
        "net_exp_max_same_dir": "1",
        "start_year": "2026",
        "start_month": "1",
        "start_day": "1",
        "end_year": "2026",
        "end_month": "12",
        "end_day": "31",
    }

    stable_restore = dict(base)
    stable_restore["label"] = "S4_BLEND_35_FREQ"

    candidates = [
        {"label": "C0_CONTROL", "overrides": {}},
        {"label": "C1_BUFFER_30BP", "overrides": {"trailing_dd_buffer_pct": "0.003"}},
        {
            "label": "C2_BUFFER_COST",
            "overrides": {
                "trailing_dd_buffer_pct": "0.003",
                "trade_cost_guard_enabled": "1",
                "roundtrip_fee_per_contract_usd": "1.40",
                "min_reward_to_fee_mult": "3.0",
            },
        },
        {
            "label": "C3_BUFFER_EXPO",
            "overrides": {
                "trailing_dd_buffer_pct": "0.003",
                "net_exposure_guard_enabled": "1",
                "net_exp_max_same_dir": "1",
            },
        },
        {
            "label": "C4_ALL_GUARDS",
            "overrides": {
                "trailing_dd_buffer_pct": "0.003",
                "trade_cost_guard_enabled": "1",
                "roundtrip_fee_per_contract_usd": "1.40",
                "min_reward_to_fee_mult": "3.0",
                "net_exposure_guard_enabled": "1",
                "net_exp_max_same_dir": "1",
            },
        },
        {
            "label": "C5_ALL_GUARDS_R36",
            "overrides": {
                "risk_per_trade": "0.036",
                "pf1_risk": "0.025",
                "trailing_dd_buffer_pct": "0.003",
                "trade_cost_guard_enabled": "1",
                "roundtrip_fee_per_contract_usd": "1.40",
                "min_reward_to_fee_mult": "3.0",
                "net_exposure_guard_enabled": "1",
                "net_exp_max_same_dir": "1",
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
        "candidates": [c["label"] for c in candidates],
        "windows": [w["name"] for w in windows],
        "results": [],
    }

    try:
        upload_code(uid, tok)
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
                run_name = f"FPHS_{c['label']}_{w['name']}_{int(time.time())}"
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

            penalty = 0.0
            for x in (ch25, ch26):
                penalty += 200000 * max(0, int(x.get("dbr") or 0) + int(x.get("tbr") or 0))
                if not bool(x.get("challenge_hit")):
                    penalty += 150000

            d25 = int(ch25.get("challenge_days") or 999)
            d26 = int(ch26.get("challenge_days") or 999)
            oos_np = float(oos.get("np_pct") or -999)
            oos_dd = float(oos.get("dd_pct") or 999)
            stress_np = float(stress.get("np_pct") or -999)
            stress_dd = float(stress.get("dd_pct") or 999)
            avg_blocks = (
                float(ch25.get("cost_blocks") or 0)
                + float(ch26.get("cost_blocks") or 0)
                + float(ch25.get("expo_blocks") or 0)
                + float(ch26.get("expo_blocks") or 0)
            )

            score = penalty + (d25 * 220) + (d26 * 260) - (oos_np * 25) + (oos_dd * 14) - (stress_np * 8) + (stress_dd * 10) + (avg_blocks * 0.25)
            rank.append(
                {
                    "candidate": label,
                    "score": round(score, 3),
                    "ch25_hit": bool(ch25.get("challenge_hit")),
                    "ch25_days": d25,
                    "ch25_dbr": ch25.get("dbr"),
                    "ch25_tbr": ch25.get("tbr"),
                    "ch26_hit": bool(ch26.get("challenge_hit")),
                    "ch26_days": d26,
                    "ch26_dbr": ch26.get("dbr"),
                    "ch26_tbr": ch26.get("tbr"),
                    "oos_np": oos_np,
                    "oos_dd": oos_dd,
                    "stress_np": stress_np,
                    "stress_dd": stress_dd,
                    "ch_cost_blocks": int(ch25.get("cost_blocks") or 0) + int(ch26.get("cost_blocks") or 0),
                    "ch_expo_blocks": int(ch25.get("expo_blocks") or 0) + int(ch26.get("expo_blocks") or 0),
                }
            )

        rank.sort(key=lambda x: x["score"])
        results["ranking"] = rank

    finally:
        set_params(uid, tok, stable_restore)

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"generated_at_utc={results.get('generated_at_utc')}",
        f"project_id={PROJECT_ID}",
        f"compile_id={results.get('compile_id','')}",
        "",
        "=== RESULTS ===",
    ]
    for r in results.get("results", []):
        lines.append(
            f"{r.get('candidate')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} sharpe={r.get('sharpe')} dbr={r.get('dbr')} tbr={r.get('tbr')} costb={r.get('cost_blocks')} expob={r.get('expo_blocks')} orders={r.get('orders')} id={r.get('backtest_id')} err={r.get('error')}"
        )

    lines.append("")
    lines.append("=== RANKING ===")
    for x in results.get("ranking", []):
        lines.append(
            f"{x['candidate']} score={x['score']} CH25(hit={x['ch25_hit']} d={x['ch25_days']} b={x['ch25_dbr']}/{x['ch25_tbr']}) CH26(hit={x['ch26_hit']} d={x['ch26_days']} b={x['ch26_dbr']}/{x['ch26_tbr']}) OOS(np={x['oos_np']} dd={x['oos_dd']}) STRESS(np={x['stress_np']} dd={x['stress_dd']}) blocks(cost={x['ch_cost_blocks']} expo={x['ch_expo_blocks']})"
        )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out_json": str(OUT_JSON),
                "out_txt": str(OUT_TXT),
                "ranking_top": (results.get("ranking") or [None])[0],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
