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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
HELPERS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_helpers.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/tradeify_growth50_candidates_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/tradeify_growth50_candidates_2026-04-20.txt")


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
    return {
        "Authorization": f"Basic {basic}",
        "Timestamp": str(ts),
        "Content-Type": "application/json",
    }


def api_post(uid, tok, endpoint, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
        data.setdefault("errors", [f"HTTP {r.status_code}"])
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


def upload_file(uid, tok, path, remote_name):
    payload = {
        "projectId": PROJECT_ID,
        "name": remote_name,
        "content": path.read_text(encoding="utf-8"),
    }
    resp = api_post(uid, tok, "files/update", payload, timeout=180)
    if not resp.get("success", False):
        raise RuntimeError(f"files/update {remote_name} failed: {resp}")


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    resp = api_post(uid, tok, "projects/update", payload, timeout=60)
    if not resp.get("success", False):
        raise RuntimeError(f"projects/update failed: {resp}")


def compile_project(uid, tok):
    c = api_post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
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


def run_backtest(uid, tok, compile_id, backtest_name):
    bt = api_post(
        uid,
        tok,
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": backtest_name},
        timeout=120,
    )
    bid = ((bt.get("backtest") or {}).get("backtestId"))
    if not bid:
        return {"status": "CreateFailed", "error": str(bt)}
    for _ in range(360):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
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
                "consistency_pct": parse_float(get_rt(rt, "ConsistencyPct")),
                "error": b.get("error") or b.get("message"),
            }
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def score(row):
    c1 = row.get("CH_2025", {})
    c2 = row.get("CH_2026_Q1", {})
    oos = row.get("OOS_2025_2026Q1", {})
    st = row.get("STRESS_2020", {})
    hit_pen = 0
    for x in (c1, c2):
        if not x.get("challenge_hit"):
            hit_pen += 300000
        hit_pen += 100000 * (int(x.get("dbr") or 0) + int(x.get("tbr") or 0))
    days = int(c1.get("challenge_days") or 999) + int(c2.get("challenge_days") or 999)
    oos_np = float(oos.get("np_pct") or 0.0)
    st_np = float(st.get("np_pct") or 0.0)
    st_tbr = int(st.get("tbr") or 0)
    return hit_pen + (days * 500) - (oos_np * 8) - (st_np * 4) + (st_tbr * 50)


def passes_growth_gate(row):
    c1 = row.get("CH_2025", {})
    c2 = row.get("CH_2026_Q1", {})
    return (
        bool(c1.get("challenge_hit"))
        and bool(c2.get("challenge_hit"))
        and int(c1.get("dbr") or 0) == 0
        and int(c1.get("tbr") or 0) == 0
        and int(c2.get("dbr") or 0) == 0
        and int(c2.get("tbr") or 0) == 0
        and int(c1.get("challenge_days") or 999) <= 15
        and int(c2.get("challenge_days") or 999) <= 15
    )


def main():
    uid, tok = load_creds()

    common = {
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "initial_cash": "50000",
        "challenge_mode_enabled": "1",
        "challenge_lock_on_target": "1",
        "challenge_target_pct": "0.06",
        "challenge_min_trading_days": "1",
        "entry_hour": "9",
        "entry_min": "40",
        "second_entry_enabled": "1",
        "second_entry_hour": "9",
        "trade_nq": "1",
        "trade_m2k": "0",
        "trade_mym": "0",
        # Tradeify Growth 50K constraints
        "daily_loss_limit_pct": "0.025",
        "trailing_dd_limit_pct": "0.04",
        "trailing_lock_mode": "EOD",
        "max_contracts_per_trade": "20",
        "pf1_maxc": "20",
        "max_open_positions": "2",
        "max_trades_per_symbol_day": "3",
        "pf1_tpd": "2",
        "daily_profit_lock_pct": "0.04",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_vixy_ratio_threshold": "1.0",
        "ext_use_vix": "0",
        "ext_min_signals": "1",
    }

    candidates = [
        {
            "label": "TF_G50_SAFE_S4",
            "overrides": {
                "risk_per_trade": "0.035",
                "pf1_risk": "0.024",
                "gap_atr_mult": "0.15",
                "max_gap_entry_pct": "0.0065",
                "pf1_gap_thr": "0.004",
                "second_entry_min": "55",
                "second_mom_entry_pct": "0.0006",
            },
        },
        {
            "label": "TF_G50_MID_B1",
            "overrides": {
                "risk_per_trade": "0.038",
                "pf1_risk": "0.026",
                "gap_atr_mult": "0.12",
                "max_gap_entry_pct": "0.0080",
                "pf1_gap_thr": "0.0032",
                "second_entry_min": "50",
                "second_mom_entry_pct": "0.0005",
            },
        },
        {
            "label": "TF_G50_FAST_B1",
            "overrides": {
                "risk_per_trade": "0.045",
                "pf1_risk": "0.032",
                "gap_atr_mult": "0.12",
                "max_gap_entry_pct": "0.0080",
                "pf1_gap_thr": "0.0030",
                "second_entry_min": "47",
                "second_mom_entry_pct": "0.0004",
            },
        },
        {
            "label": "TF_G50_SAFE_LOW",
            "overrides": {
                "risk_per_trade": "0.028",
                "pf1_risk": "0.019",
                "gap_atr_mult": "0.16",
                "max_gap_entry_pct": "0.0060",
                "pf1_gap_thr": "0.0045",
                "second_entry_min": "58",
                "second_mom_entry_pct": "0.0007",
            },
        },
    ]

    stage1 = [
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

    stage2 = [
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

    out = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": PROJECT_ID,
        "candidates": [c["label"] for c in candidates],
        "results": [],
    }

    by = {c["label"]: {} for c in candidates}

    try:
        upload_file(uid, tok, MAIN_PATH, "main.py")
        upload_file(uid, tok, HELPERS_PATH, "pf100_helpers.py")
        set_params(uid, tok, common)
        compile_id = compile_project(uid, tok)
        out["compile_id"] = compile_id

        for c in candidates:
            for w in stage1:
                p = dict(common)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = c["label"]
                set_params(uid, tok, p)
                run_name = f"TFG50_S1_{c['label']}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, compile_id, run_name)
                r.update({"candidate": c["label"], "window": w["name"], "stage": "S1"})
                out["results"].append(r)
                by[c["label"]][w["name"]] = r
                OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        shortlist = []
        for c in candidates:
            label = c["label"]
            if passes_growth_gate(by[label]):
                shortlist.append(label)

        if not shortlist:
            ranked_s1 = []
            for c in candidates:
                label = c["label"]
                r1 = by[label].get("CH_2025", {})
                r2 = by[label].get("CH_2026_Q1", {})
                breaches = int(r1.get("dbr") or 0) + int(r1.get("tbr") or 0) + int(r2.get("dbr") or 0) + int(r2.get("tbr") or 0)
                hits = int(bool(r1.get("challenge_hit"))) + int(bool(r2.get("challenge_hit")))
                days = int(r1.get("challenge_days") or 999) + int(r2.get("challenge_days") or 999)
                ranked_s1.append((breaches, -hits, days, label))
            ranked_s1.sort()
            shortlist = [x[3] for x in ranked_s1[:2]]

        out["stage2_candidates"] = shortlist
        OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        cmap = {c["label"]: c for c in candidates}
        for label in shortlist:
            c = cmap[label]
            for w in stage2:
                p = dict(common)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = label
                set_params(uid, tok, p)
                run_name = f"TFG50_S2_{label}_{w['name']}_{int(time.time())}"
                r = run_backtest(uid, tok, compile_id, run_name)
                r.update({"candidate": label, "window": w["name"], "stage": "S2"})
                out["results"].append(r)
                by[label][w["name"]] = r
                OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        ranking = []
        for c in candidates:
            label = c["label"]
            row = by[label]
            ranking.append(
                {
                    "candidate": label,
                    "score": score(row),
                    "passes_growth_gate": passes_growth_gate(row),
                    "CH_2025": row.get("CH_2025"),
                    "CH_2026_Q1": row.get("CH_2026_Q1"),
                    "OOS_2025_2026Q1": row.get("OOS_2025_2026Q1"),
                    "STRESS_2020": row.get("STRESS_2020"),
                }
            )
        ranking.sort(key=lambda x: x["score"])
        out["ranking"] = ranking
        out["recommended_candidate"] = ranking[0]["candidate"] if ranking else None
        out["recommended_should_pass"] = bool(ranking and ranking[0].get("passes_growth_gate"))

        # leave project configured with recommended candidate
        if out["recommended_candidate"]:
            rec = next(c for c in candidates if c["label"] == out["recommended_candidate"])
            p = dict(common)
            p.update(rec["overrides"])
            p["label"] = rec["label"]
            set_params(uid, tok, p)

    finally:
        OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"generated_at_utc={out.get('generated_at_utc')}",
        f"project_id={PROJECT_ID}",
        f"compile_id={out.get('compile_id','')}",
        f"stage2_candidates={out.get('stage2_candidates',[])}",
        f"recommended_candidate={out.get('recommended_candidate')}",
        f"recommended_should_pass={out.get('recommended_should_pass')}",
        "",
        "=== RESULTS ===",
    ]
    for r in out.get("results", []):
        lines.append(
            f"{r.get('stage')} {r.get('candidate')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} sharpe={r.get('sharpe')} orders={r.get('orders')} id={r.get('backtest_id')} err={r.get('error')}"
        )
    lines.append("")
    lines.append("=== RANKING ===")
    for x in out.get("ranking", []):
        c1 = x.get("CH_2025") or {}
        c2 = x.get("CH_2026_Q1") or {}
        o = x.get("OOS_2025_2026Q1") or {}
        s = x.get("STRESS_2020") or {}
        lines.append(
            f"{x['candidate']} score={x['score']:.3f} passGate={x['passes_growth_gate']} CH25(hit={c1.get('challenge_hit')} d={c1.get('challenge_days')} b={c1.get('dbr')}/{c1.get('tbr')}) CH26(hit={c2.get('challenge_hit')} d={c2.get('challenge_days')} b={c2.get('dbr')}/{c2.get('tbr')}) OOS(np={o.get('np_pct')} dd={o.get('dd_pct')} tbr={o.get('tbr')}) STRESS(np={s.get('np_pct')} dd={s.get('dd_pct')} tbr={s.get('tbr')})"
        )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

