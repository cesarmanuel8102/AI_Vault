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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/mff_compliance_ab_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/mff_compliance_ab_2026-04-20.txt")


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

    for _ in range(360):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=90)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        if "Completed" in st:
            s = b.get("statistics") or {}
            rt = b.get("runtimeStatistics") or {}
            rec = {
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
                "consistency_pct": parse_float(get_rt(rt, "ConsistencyPct")),
                "best_day_usd": parse_float(get_rt(rt, "BestDayUSD")),
                "mff_news_blocks": parse_int(get_rt(rt, "MFFNewsBlocks")),
                "mff_price_limit_blocks": parse_int(get_rt(rt, "MFFPriceLimitBlocks")),
                "mff_consistency_blocks": parse_int(get_rt(rt, "MFFConsistencyBlocks")),
            }
            return rec
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(10)

    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = load_creds()

    base_restore = {
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
        "max_trades_per_symbol_day": "3",
        "pf1_tpd": "2",
        "daily_loss_limit_pct": "0.05",
        "daily_profit_lock_pct": "0.04",
        "trailing_dd_limit_pct": "0.05",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_vixy_ratio_threshold": "1.0",
        "ext_use_vix": "0",
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
        "mff_compliance_enabled": "0",
        "mff_consistency_enforced": "0",
        "mff_news_guard_enabled": "0",
        "mff_price_limit_guard_enabled": "0",
    }

    profiles = [
        {
            "label": "BASE_S4",
            "overrides": {
                "mff_compliance_enabled": "0",
                "mff_consistency_enforced": "0",
                "mff_news_guard_enabled": "0",
                "mff_price_limit_guard_enabled": "0",
                "challenge_min_trading_days": "0",
                "challenge_lock_on_target": "1",
            },
        },
        {
            "label": "S4_MFF_COMPLIANCE",
            "overrides": {
                "mff_compliance_enabled": "1",
                "mff_consistency_enforced": "1",
                "mff_consistency_limit_pct": "50",
                "mff_news_guard_enabled": "1",
                "mff_news_flatten_enabled": "0",
                "mff_news_block_minutes": "2",
                "mff_news_times_hhmm": "08:30,10:00,14:00",
                "mff_price_limit_guard_enabled": "1",
                "mff_price_limit_pct": "0.05",
                "challenge_min_trading_days": "2",
                "challenge_lock_on_target": "1",
            },
        },
    ]

    windows = [
        {
            "name": "CH_2025",
            "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2025", "end_month": "12", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "1"},
        },
        {
            "name": "CH_2026_Q1",
            "dates": {"start_year": "2026", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "1"},
        },
        {
            "name": "OOS_2025_2026Q1",
            "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "0"},
        },
        {
            "name": "STRESS_2020",
            "dates": {"start_year": "2020", "start_month": "1", "start_day": "1", "end_year": "2020", "end_month": "12", "end_day": "31"},
            "overrides": {"challenge_mode_enabled": "0"},
        },
    ]

    results = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": PROJECT_ID,
        "profiles": [p["label"] for p in profiles],
        "windows": [w["name"] for w in windows],
        "results": [],
    }

    try:
        set_params(uid, tok, base_restore)
        cid = compile_project(uid, tok)
        results["compile_id"] = cid

        for profile in profiles:
            for w in windows:
                p = dict(base_restore)
                p.update(profile["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = profile["label"]
                set_params(uid, tok, p)
                run_name = f"MFF_AB_{profile['label']}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, cid, run_name)
                r.update({"profile": profile["label"], "window": w["name"]})
                results["results"].append(r)
                OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    finally:
        set_params(uid, tok, base_restore)

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
            f"{r.get('profile')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} cons={r.get('consistency_pct')} bestDay={r.get('best_day_usd')} mffBlocks(news={r.get('mff_news_blocks')},price={r.get('mff_price_limit_blocks')},cons={r.get('mff_consistency_blocks')}) id={r.get('backtest_id')}"
        )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT), "results": len(results.get('results', []))}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
