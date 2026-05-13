import base64, hashlib, json, re, time, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/stable_uplift_sweep_2026-04-21.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/stable_uplift_sweep_2026-04-21.txt")


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


def get_rt(rt, key):
    if isinstance(rt, dict):
        return rt.get(key)
    if isinstance(rt, list):
        for item in rt:
            if isinstance(item, dict) and str(item.get("name") or item.get("Name")) == key:
                return item.get("value") or item.get("Value")
    return None


def monthly_stats(bt):
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    pstats = perf.get("portfolioStatistics") or {}
    start_equity = parse_float(pstats.get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            d = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        by_month[f"{d.year:04d}-{d.month:02d}"] += float(pnl)

    if not by_month:
        return {"monthly_mean_pct": None, "monthly_median_pct": None, "monthly_count": 0}

    eq = float(start_equity)
    rets = []
    for m in sorted(by_month):
        pnl = by_month[m]
        rets.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl

    return {
        "monthly_mean_pct": round(statistics.mean(rets), 3),
        "monthly_median_pct": round(statistics.median(rets), 3),
        "monthly_count": len(rets),
    }


def upload_main(uid, tok):
    payload = {"projectId": PROJECT_ID, "name": "main.py", "content": MAIN_PATH.read_text(encoding="utf-8")}
    resp = api_post(uid, tok, "files/update", payload, timeout=180)
    if not resp.get("success", False):
        raise RuntimeError(f"files/update failed: {resp}")


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
                raise RuntimeError(f"compile failed: {st} | {r}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
    bid = ((bt.get("backtest") or {}).get("backtestId"))
    if not bid:
        return {"status": "CreateFailed", "error": str(bt)}
    for _ in range(420):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        if "Completed" in st:
            s = b.get("statistics") or {}
            rt = b.get("runtimeStatistics") or {}
            row = {
                "status": st,
                "backtest_id": bid,
                "np_pct": parse_float(s.get("Net Profit")),
                "dd_pct": parse_float(s.get("Drawdown")),
                "sharpe": parse_float(s.get("Sharpe Ratio")),
                "orders": parse_int(s.get("Total Orders")),
                "dbr": parse_int(get_rt(rt, "DailyLossBreaches")),
                "tbr": parse_int(get_rt(rt, "TrailingBreaches")),
                "pf100_trades_total": parse_int(get_rt(rt, "PF100TradesTotal")),
                "pf100_stress_trades": parse_int(get_rt(rt, "PF100StressTrades")),
                "error": b.get("error") or b.get("message"),
            }
            row.update(monthly_stats(b))
            return row
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": b.get("error") or b.get("message")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def stress_ok(r):
    return (r.get("np_pct") is not None and (r.get("np_pct") >= 0.0)
            and int(r.get("dbr") or 0) == 0 and int(r.get("tbr") or 0) == 0)


def main():
    uid, tok = load_creds()

    base = {
        "label": "PF100_STABLE_UPLIFT_BASE",
        "allow_shorts": 1,
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
        "max_trades_per_symbol_day": 2,
        "risk_per_trade": 0.0115,
        "max_contracts_per_trade": 5,
        "pf1_risk": 0.0085,
        "pf1_stop": 0.45,
        "pf1_tgt": 1.70,
        "pf1_rng": 0.0055,
        "pf1_buf": 0.0005,
        "pf1_gap_fb": 1,
        "pf1_gap_thr": 0.0030,
        "pf1_tpd": 1,
        "pf1_mom_on": 1,
        "pf1_mom": 0.0006,
        "pf1_no_shorts": 1,
        "pf1_maxc": 1,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_mom_entry_pct": 0.0025,
        "second_stop_atr_mult": 0.65,
        "second_target_atr_mult": 1.35,
        "second_risk_mult": 0.70,
        "second_max_hold_hours": 3,
        "second_use_trend_filter": 1,
        "pf1_w2win": 0,
        "pf1_pt_on": 0,
        "pf1_tr_on": 0,
        "pf1_q_on": 0,
    }

    candidates = [
        ("ST_U0_CTRL_R115_V1030", {}),
        ("ST_U1_R118_V1030", {"risk_per_trade": 0.0118}),
        ("ST_U2_R120_V1030", {"risk_per_trade": 0.0120}),
        ("ST_U3_R115_V1025", {"ext_vixy_ratio_threshold": 1.025}),
        ("ST_U4_R120_V1025", {"risk_per_trade": 0.0120, "ext_vixy_ratio_threshold": 1.025}),
        ("ST_U5_R118_SEC75", {"risk_per_trade": 0.0118, "second_risk_mult": 0.75, "second_target_atr_mult": 1.40}),
        ("ST_U6_R115_MOM20", {"second_mom_entry_pct": 0.0020, "second_risk_mult": 0.72}),
        ("ST_U7_R115_MAXC6", {"max_contracts_per_trade": 6}),
    ]

    scenarios = [
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("FULL_2022_2026Q1", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
    ]

    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg["label"] = label
        cfg.update(ov)

        # run stress first; only continue if robust
        p = dict(cfg)
        p.update(scenarios[0][1])
        set_params(uid, tok, p)
        r0 = run_backtest(uid, tok, cid, f"{label}_STRESS_{int(time.time())}")
        r0.update({"candidate": label, "scenario": scenarios[0][0], "overrides": ov})
        rows.append(r0)

        if stress_ok(r0):
            for sname, sdates in scenarios[1:]:
                p2 = dict(cfg)
                p2.update(sdates)
                set_params(uid, tok, p2)
                r = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
                r.update({"candidate": label, "scenario": sname, "overrides": ov})
                rows.append(r)

        OUT_JSON.write_text(json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "compile_id": cid,
            "rows": rows,
        }, indent=2), encoding="utf-8")

    lines = ["generated_at_utc=" + datetime.now(timezone.utc).isoformat(), f"compile_id={cid}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
            f"m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} trades={r.get('pf100_trades_total')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_JSON)


if __name__ == "__main__":
    main()
