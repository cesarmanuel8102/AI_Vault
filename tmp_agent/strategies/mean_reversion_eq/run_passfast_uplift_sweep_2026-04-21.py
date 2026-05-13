import base64, hashlib, json, re, time, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_uplift_sweep_2026-04-21.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/passfast_uplift_sweep_2026-04-21.txt")


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
                "challenge_hit": parse_bool(get_rt(rt, "ChallengeTargetHit")),
                "challenge_days": parse_int(get_rt(rt, "ChallengeDaysToTarget")),
                "consistency_pct": parse_float(get_rt(rt, "ChallengeConsistencyPct")),
                "pf100_trades_total": parse_int(get_rt(rt, "PF100TradesTotal")),
                "error": b.get("error") or b.get("message"),
            }
            row.update(monthly_stats(b))
            return row
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": b.get("error") or b.get("message")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = load_creds()

    base = {
        "label": "PF100_FASTPASS_UPLIFT_BASE",
        "regime_mode": "PF100",
        "profile_mode": "FAST_PASS",
        "allow_shorts": 1,
        "trade_nq": 1,
        "trade_m2k": 0,
        "entry_hour": 9,
        "entry_min": 40,
        "second_entry_enabled": 1,
        "second_entry_hour": 9,
        "second_entry_min": 47,
        "second_entry_breakout_enabled": 1,
        "second_use_trend_filter": 1,
        "risk_per_trade": 0.045,
        "pf1_risk": 0.032,
        "max_contracts_per_trade": 26,
        "pf1_maxc": 12,
        "max_open_positions": 2,
        "max_trades_per_symbol_day": 3,
        "pf1_tpd": 2,
        "daily_loss_limit_pct": 0.05,
        "daily_profit_lock_pct": 0.04,
        "trailing_dd_limit_pct": 0.05,
        "trailing_lock_mode": "INTRADAY",
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.00,
        "ext_min_signals": 1,
        "gap_atr_mult": 0.12,
        "max_gap_entry_pct": 0.0080,
        "second_mom_entry_pct": 0.0004,
        "pf1_stop": 0.42,
        "pf1_tgt": 1.35,
        "pf1_mom": 0.0005,
        "pf1_rng": 0.010,
        "pf1_gap_thr": 0.0030,
        "challenge_mode_enabled": 1,
        "challenge_lock_on_target": 1,
    }

    candidates = [
        ("PF_U0_B1_BASE", {}),
        ("PF_U1_B1_TRAIL45", {"trailing_dd_limit_pct": 0.045, "daily_loss_limit_pct": 0.045}),
        ("PF_U2_B1_TRAIL40", {"trailing_dd_limit_pct": 0.04, "daily_loss_limit_pct": 0.04, "risk_per_trade": 0.043, "pf1_risk": 0.030}),
        ("PF_U3_B1_R44_LOCK05", {"risk_per_trade": 0.044, "pf1_risk": 0.031, "daily_profit_lock_pct": 0.05}),
        ("PF_U4_B1_R43_V103_S2", {"risk_per_trade": 0.043, "pf1_risk": 0.030, "ext_vixy_ratio_threshold": 1.03, "ext_min_signals": 2}),
        ("PF_U5_B1_EOD_TRAIL", {"trailing_lock_mode": "EOD", "trailing_dd_limit_pct": 0.05}),
        ("PF_U6_MID_BAL", {"risk_per_trade": 0.040, "pf1_risk": 0.028, "max_contracts_per_trade": 22, "pf1_maxc": 10, "gap_atr_mult": 0.13}),
        ("PF_U7_B0_CTRL", {
            "risk_per_trade": 0.035, "pf1_risk": 0.024, "max_contracts_per_trade": 18, "pf1_maxc": 8,
            "gap_atr_mult": 0.15, "max_gap_entry_pct": 0.0065, "second_entry_min": 55, "second_mom_entry_pct": 0.0006
        }),
    ]

    windows = [
        ("CH_2025", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2025, "end_month": 12, "end_day": 31, "challenge_mode_enabled": 1, "challenge_lock_on_target": 1}),
        ("CH_2026_Q1", {"start_year": 2026, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31, "challenge_mode_enabled": 1, "challenge_lock_on_target": 1}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31, "challenge_mode_enabled": 0, "challenge_lock_on_target": 0}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31, "challenge_mode_enabled": 0, "challenge_lock_on_target": 0}),
    ]

    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg["label"] = label
        cfg.update(ov)

        for wname, wov in windows:
            p = dict(cfg)
            p.update(wov)
            set_params(uid, tok, p)
            r = run_backtest(uid, tok, cid, f"{label}_{wname}_{int(time.time())}")
            r.update({"candidate": label, "window": wname, "overrides": ov})
            rows.append(r)

            OUT_JSON.write_text(json.dumps({
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "compile_id": cid,
                "rows": rows,
            }, indent=2), encoding="utf-8")

    lines = ["generated_at_utc=" + datetime.now(timezone.utc).isoformat(), f"compile_id={cid}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['window']} hit={r.get('challenge_hit')} days={r.get('challenge_days')} np={r.get('np_pct')} dd={r.get('dd_pct')} "
            f"dbr={r.get('dbr')} tbr={r.get('tbr')} cons={r.get('consistency_pct')} m_mean={r.get('monthly_mean_pct')} trades={r.get('pf100_trades_total')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_JSON)


if __name__ == "__main__":
    main()
