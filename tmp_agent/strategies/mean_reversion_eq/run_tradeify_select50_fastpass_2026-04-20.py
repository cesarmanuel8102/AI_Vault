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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/tradeify_select50_fastpass_2026-04-20.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/tradeify_select50_fastpass_2026-04-20.txt")


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
    payload = {"projectId": PROJECT_ID, "name": remote_name, "content": path.read_text(encoding="utf-8")}
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


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
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


def pass_select_gate(row):
    c1 = row.get("CH_2025", {})
    c2 = row.get("CH_2026_Q1", {})
    def ok(c):
        return (
            bool(c.get("challenge_hit"))
            and int(c.get("challenge_days") or 999) <= 20
            and int(c.get("tbr") or 0) == 0
            and (c.get("consistency_pct") is not None and float(c.get("consistency_pct")) <= 40.0)
        )
    return ok(c1) and ok(c2)


def score(row):
    c1 = row.get("CH_2025", {})
    c2 = row.get("CH_2026_Q1", {})
    o = row.get("OOS_2025_2026Q1", {})
    s = row.get("STRESS_2020", {})
    pen = 0
    for c in (c1, c2):
        if not c.get("challenge_hit"):
            pen += 250000
        pen += 100000 * int(c.get("tbr") or 0)
        cons = c.get("consistency_pct")
        if cons is None:
            pen += 50000
        elif float(cons) > 40.0:
            pen += 70000
    days = int(c1.get("challenge_days") or 999) + int(c2.get("challenge_days") or 999)
    return pen + days * 600 - float(o.get("np_pct") or 0.0) * 8 - float(s.get("np_pct") or 0.0) * 4


def main():
    uid, tok = load_creds()

    common = {
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "initial_cash": "50000",
        "challenge_mode_enabled": "1",
        "challenge_lock_on_target": "1",
        "challenge_target_pct": "0.06",
        "challenge_min_trading_days": "3",
        "entry_hour": "9",
        "entry_min": "40",
        "second_entry_enabled": "1",
        "second_entry_hour": "9",
        "second_entry_min": "50",
        "trade_nq": "1",
        "trade_m2k": "0",
        "trade_mym": "0",
        # Select constraints
        "daily_loss_limit_pct": "1.0",   # no DLL in evaluation
        "trailing_dd_limit_pct": "0.04", # $2,000
        "trailing_lock_mode": "EOD",
        "max_contracts_per_trade": "20", # max 40 micro total with max_open_positions=1
        "pf1_maxc": "20",
        "max_open_positions": "1",
        "max_trades_per_symbol_day": "3",
        "pf1_tpd": "2",
        "daily_profit_lock_pct": "0.07",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_vixy_ratio_threshold": "1.0",
        "ext_use_vix": "0",
        "ext_min_signals": "1",
    }

    candidates = [
        {"label": "TS50_FD1_R40", "overrides": {"risk_per_trade": "0.040", "pf1_risk": "0.028", "gap_atr_mult": "0.15", "pf1_gap_thr": "0.004", "max_gap_entry_pct": "0.0065", "second_mom_entry_pct": "0.0006"}},
        {"label": "TS50_FD2_R45", "overrides": {"risk_per_trade": "0.045", "pf1_risk": "0.032", "gap_atr_mult": "0.15", "pf1_gap_thr": "0.004", "max_gap_entry_pct": "0.0065", "second_mom_entry_pct": "0.0006"}},
        {"label": "TS50_FD4_R42F4", "overrides": {"risk_per_trade": "0.042", "pf1_risk": "0.030", "gap_atr_mult": "0.15", "pf1_gap_thr": "0.004", "max_gap_entry_pct": "0.0065", "max_trades_per_symbol_day": "4", "pf1_tpd": "3", "second_mom_entry_pct": "0.0005"}},
        {"label": "TS50_FD6_EARLY", "overrides": {"risk_per_trade": "0.042", "pf1_risk": "0.030", "gap_atr_mult": "0.15", "pf1_gap_thr": "0.004", "max_gap_entry_pct": "0.0065", "max_trades_per_symbol_day": "4", "pf1_tpd": "3", "second_entry_min": "47", "second_mom_entry_pct": "0.0004"}},
        {"label": "TS50_FD2_R45_RELAX", "overrides": {"risk_per_trade": "0.045", "pf1_risk": "0.032", "gap_atr_mult": "0.12", "pf1_gap_thr": "0.0030", "max_gap_entry_pct": "0.0080", "second_entry_min": "47", "second_mom_entry_pct": "0.0004"}},
        {"label": "TS50_FD1_R40_RELAX", "overrides": {"risk_per_trade": "0.040", "pf1_risk": "0.028", "gap_atr_mult": "0.12", "pf1_gap_thr": "0.0032", "max_gap_entry_pct": "0.0080", "second_entry_min": "50", "second_mom_entry_pct": "0.0005"}},
    ]

    stage1 = [
        {"name": "CH_2025", "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2025", "end_month": "12", "end_day": "31"}, "overrides": {"challenge_mode_enabled": "1", "challenge_lock_on_target": "1"}},
        {"name": "CH_2026_Q1", "dates": {"start_year": "2026", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"}, "overrides": {"challenge_mode_enabled": "1", "challenge_lock_on_target": "1"}},
    ]
    stage2 = [
        {"name": "OOS_2025_2026Q1", "dates": {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"}, "overrides": {"challenge_mode_enabled": "0", "challenge_lock_on_target": "0"}},
        {"name": "STRESS_2020", "dates": {"start_year": "2020", "start_month": "1", "start_day": "1", "end_year": "2020", "end_month": "12", "end_day": "31"}, "overrides": {"challenge_mode_enabled": "0", "challenge_lock_on_target": "0"}},
    ]

    out = {"generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "project_id": PROJECT_ID, "candidates": [c["label"] for c in candidates], "results": []}
    by = {c["label"]: {} for c in candidates}

    try:
        upload_file(uid, tok, MAIN_PATH, "main.py")
        upload_file(uid, tok, HELPERS_PATH, "pf100_helpers.py")
        set_params(uid, tok, common)
        cid = compile_project(uid, tok)
        out["compile_id"] = cid

        for c in candidates:
            for w in stage1:
                p = dict(common)
                p.update(c["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = c["label"]
                set_params(uid, tok, p)
                r = run_backtest(uid, tok, cid, f"TS50_S1_{c['label']}_{w['name']}_{int(time.time())}")
                r.update({"candidate": c["label"], "window": w["name"], "stage": "S1"})
                out["results"].append(r)
                by[c["label"]][w["name"]] = r
                OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        shortlist = [c["label"] for c in candidates if pass_select_gate(by[c["label"]])]
        if not shortlist:
            pre = []
            for c in candidates:
                lb = c["label"]
                c1 = by[lb].get("CH_2025", {})
                c2 = by[lb].get("CH_2026_Q1", {})
                k = (
                    int(not bool(c1.get("challenge_hit"))) + int(not bool(c2.get("challenge_hit"))),
                    int(c1.get("tbr") or 0) + int(c2.get("tbr") or 0),
                    int(c1.get("challenge_days") or 999) + int(c2.get("challenge_days") or 999),
                )
                pre.append((k, lb))
            pre.sort(key=lambda x: x[0])
            shortlist = [x[1] for x in pre[:3]]

        out["stage2_candidates"] = shortlist
        OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        cmap = {c["label"]: c for c in candidates}
        for lb in shortlist:
            for w in stage2:
                p = dict(common)
                p.update(cmap[lb]["overrides"])
                p.update(w["overrides"])
                p.update(w["dates"])
                p["label"] = lb
                set_params(uid, tok, p)
                r = run_backtest(uid, tok, cid, f"TS50_S2_{lb}_{w['name']}_{int(time.time())}")
                r.update({"candidate": lb, "window": w["name"], "stage": "S2"})
                out["results"].append(r)
                by[lb][w["name"]] = r
                OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        ranking = []
        for c in candidates:
            lb = c["label"]
            row = by[lb]
            ranking.append(
                {
                    "candidate": lb,
                    "score": score(row),
                    "passes_select_gate": pass_select_gate(row),
                    "CH_2025": row.get("CH_2025"),
                    "CH_2026_Q1": row.get("CH_2026_Q1"),
                    "OOS_2025_2026Q1": row.get("OOS_2025_2026Q1"),
                    "STRESS_2020": row.get("STRESS_2020"),
                }
            )
        ranking.sort(key=lambda x: x["score"])
        out["ranking"] = ranking
        out["recommended_candidate"] = ranking[0]["candidate"] if ranking else None
        out["recommended_should_pass"] = bool(ranking and ranking[0].get("passes_select_gate"))

        if out["recommended_candidate"]:
            rec = next(c for c in candidates if c["label"] == out["recommended_candidate"])
            p = dict(common)
            p.update(rec["overrides"])
            p["label"] = rec["label"]
            set_params(uid, tok, p)

    finally:
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
            f"{r.get('stage')} {r.get('candidate')} {r.get('window')} status={r.get('status')} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} cons={r.get('consistency_pct')} orders={r.get('orders')} id={r.get('backtest_id')} err={r.get('error')}"
        )
    lines.append("")
    lines.append("=== RANKING ===")
    for x in out.get("ranking", []):
        c1 = x.get("CH_2025") or {}
        c2 = x.get("CH_2026_Q1") or {}
        o = x.get("OOS_2025_2026Q1") or {}
        s = x.get("STRESS_2020") or {}
        lines.append(
            f"{x['candidate']} score={x['score']:.3f} passGate={x['passes_select_gate']} CH25(hit={c1.get('challenge_hit')} d={c1.get('challenge_days')} cons={c1.get('consistency_pct')} tbr={c1.get('tbr')}) CH26(hit={c2.get('challenge_hit')} d={c2.get('challenge_days')} cons={c2.get('consistency_pct')} tbr={c2.get('tbr')}) OOS(np={o.get('np_pct')} dd={o.get('dd_pct')} tbr={o.get('tbr')}) STRESS(np={s.get('np_pct')} dd={s.get('dd_pct')} tbr={s.get('tbr')})"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

