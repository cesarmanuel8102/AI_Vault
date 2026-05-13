import base64
import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase9_pf200_execfix.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase9_pf200_execfix_recheck_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase9_pf200_execfix_recheck_2026-04-22.txt")


def creds():
    data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(data.get("user_id") or data.get("userId") or "").strip()
    tok = str(data.get("api_token") or data.get("apiToken") or data.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Missing QC credentials in quantconnect_access.json")
    return uid, tok


def hdr(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Timestamp": str(ts),
        "Content-Type": "application/json",
    }


def post(uid, tok, endpoint, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=hdr(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
    if data.get("success", False):
        return data

    msg = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", msg)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return data


def pf(value):
    try:
        return float(str(value).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def pi(value):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def rt(runtime, key):
    if isinstance(runtime, dict):
        return runtime.get(key)
    if isinstance(runtime, list):
        for it in runtime:
            if isinstance(it, dict) and str(it.get("name") or it.get("Name")) == key:
                return it.get("value") or it.get("Value")
    return None


def perf_metrics(bt):
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    start_equity = pf((perf.get("portfolioStatistics") or {}).get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    by_day = defaultdict(float)
    gross_profit = 0.0
    gross_loss = 0.0
    max_consec_losses = 0
    cur_consec_losses = 0

    for t in trades:
        et = t.get("exitTime")
        pnl = t.get("profitLoss")
        if et is None or pnl is None:
            continue
        pnl = float(pnl)
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue

        by_month[f"{dt.year:04d}-{dt.month:02d}"] += pnl
        by_day[f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"] += pnl

        if pnl >= 0:
            gross_profit += pnl
            cur_consec_losses = 0
        else:
            gross_loss += abs(pnl)
            cur_consec_losses += 1
            if cur_consec_losses > max_consec_losses:
                max_consec_losses = cur_consec_losses

    monthly = []
    eq = float(start_equity)
    for key in sorted(by_month.keys()):
        pnl = by_month[key]
        monthly.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl

    total_profit = sum(by_day.values())
    best_day = max(by_day.values()) if by_day else 0.0
    best_day_share_pct = 999.0 if total_profit <= 0 else (best_day / total_profit) * 100.0
    profit_factor = None if gross_loss <= 0 else gross_profit / gross_loss

    return {
        "monthly_mean_pct": round(statistics.mean(monthly), 3) if monthly else None,
        "monthly_median_pct": round(statistics.median(monthly), 3) if monthly else None,
        "monthly_count": len(monthly),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "max_consec_losses": int(max_consec_losses),
        "best_day_share_pct": round(best_day_share_pct, 2),
    }


def upload_main(uid, tok):
    data = post(
        uid,
        tok,
        "files/update",
        {"projectId": PROJECT_ID, "name": "main.py", "content": MAIN_PATH.read_text(encoding="utf-8")},
        timeout=180,
    )
    if not data.get("success", False):
        raise RuntimeError(data)


def clear_params(uid, tok):
    data = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": []}, timeout=60)
    if not data.get("success", False):
        raise RuntimeError(data)


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    data = post(uid, tok, "projects/update", payload, timeout=60)
    if not data.get("success", False):
        raise RuntimeError(data)


def compile_project(uid, tok):
    data = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = data.get("compileId")
    if not cid:
        raise RuntimeError(data)
    for _ in range(180):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(rd)
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, compile_id, name):
    backtest_id = None
    create_err = None
    for _ in range(30):
        bc = post(
            uid,
            tok,
            "backtests/create",
            {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
            timeout=120,
        )
        backtest_id = ((bc.get("backtest") or {}).get("backtestId"))
        if backtest_id:
            break
        create_err = str(bc)
        if "no spare nodes available" in create_err.lower():
            time.sleep(60)
            continue
        return {"status": "CreateFailed", "error": create_err}
    if not backtest_id:
        return {"status": "CreateFailed", "error": create_err or "no backtest id"}

    for _ in range(420):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=120)
        bt = rd.get("backtest") or {}
        status = str(bt.get("status", ""))

        if "Completed" in status:
            stats = bt.get("statistics") or {}
            runtime = bt.get("runtimeStatistics") or {}
            row = {
                "status": status,
                "backtest_id": backtest_id,
                "np_pct": pf(stats.get("Net Profit")),
                "dd_pct": pf(stats.get("Drawdown")),
                "dbr": pi(rt(runtime, "DailyLossBreaches")),
                "tbr": pi(rt(runtime, "TrailingBreaches")),
                "orders": pi(stats.get("Total Orders")),
                "stress_days": pi(rt(runtime, "ExternalStressDays")),
            }
            row.update(perf_metrics(bt))
            return row

        if any(x in status for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": status, "backtest_id": backtest_id, "error": bt.get("error") or bt.get("message")}

        time.sleep(10)
    return {"status": "Timeout", "backtest_id": backtest_id}


def stress_ok(row):
    return (
        row.get("np_pct") is not None
        and row.get("np_pct") >= 0
        and int(row.get("dbr") or 0) == 0
        and int(row.get("tbr") or 0) == 0
    )


def main():
    uid, tok = creds()

    base = {
        "trade_mnq": 1,
        "trade_mes": 1,
        "allow_shorts": 1,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.04,
        "flatten_hour": 15,
        "flatten_min": 58,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_rv_threshold": 1.0,
        "ext_gap_abs_threshold": 1.0,
        "n_risk": 0.013,
        "or_risk": 0.010,
        "s_risk": 0.003,
        "max_contracts_per_trade": 12,
        "max_trades_per_symbol_day": 3,
        "or_minutes": 10,
        "or_breakout_buffer_pct": 0.0003,
        "or_target_atr_mult": 1.55,
        "or_stop_atr_mult": 0.75,
        "trailing_lock_mode": "EOD",
    }

    candidates = [
        ("P9_A0_DD35", {"trailing_dd_limit_pct": 0.035}),
        ("P9_A1_DD40", {"trailing_dd_limit_pct": 0.040}),
        ("P9_B0_DD35_R20", {"trailing_dd_limit_pct": 0.035, "n_risk": 0.014, "or_risk": 0.011}),
        ("P9_B1_DD40_R20", {"trailing_dd_limit_pct": 0.040, "n_risk": 0.014, "or_risk": 0.011}),
        (
            "P9_C0_DYN_DD40",
            {
                "trailing_dd_limit_pct": 0.040,
                "dynamic_risk_enabled": 1,
                "dynamic_risk_soft_dd_frac": 0.60,
                "dynamic_risk_hard_dd_frac": 0.80,
                "dynamic_risk_soft_mult": 0.78,
                "dynamic_risk_hard_mult": 0.58,
                "dynamic_risk_red_day_mult": 0.82,
            },
        ),
        (
            "P9_C1_DYN_DD40_R20",
            {
                "trailing_dd_limit_pct": 0.040,
                "n_risk": 0.014,
                "or_risk": 0.011,
                "dynamic_risk_enabled": 1,
                "dynamic_risk_soft_dd_frac": 0.60,
                "dynamic_risk_hard_dd_frac": 0.80,
                "dynamic_risk_soft_mult": 0.80,
                "dynamic_risk_hard_mult": 0.60,
                "dynamic_risk_red_day_mult": 0.85,
            },
        ),
    ]

    scenarios = [
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        (
            "OOS_2025_2026Q1",
            {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31},
        ),
        (
            "FULL_2022_2026Q1",
            {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31},
        ),
    ]

    upload_main(uid, tok)
    clear_params(uid, tok)
    compile_id = compile_project(uid, tok)

    rows = []
    for label, overrides in candidates:
        cfg = dict(base)
        cfg.update(overrides)

        # Gated pipeline: stress first, then oos/full only if stress survives
        stress_params = dict(cfg)
        stress_params.update(scenarios[0][1])
        set_params(uid, tok, stress_params)
        r0 = run_backtest(uid, tok, compile_id, f"{label}_STRESS_{int(time.time())}")
        r0.update({"candidate": label, "scenario": "STRESS_2020", "overrides": overrides})
        rows.append(r0)

        if stress_ok(r0):
            for sname, sdates in scenarios[1:]:
                params = dict(cfg)
                params.update(sdates)
                set_params(uid, tok, params)
                r = run_backtest(uid, tok, compile_id, f"{label}_{sname}_{int(time.time())}")
                r.update({"candidate": label, "scenario": sname, "overrides": overrides})
                rows.append(r)

        OUT_JSON.write_text(
            json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": compile_id, "rows": rows}, indent=2),
            encoding="utf-8",
        )

    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"compile_id={compile_id}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} "
            f"tbr={r.get('tbr')} m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} "
            f"pf={r.get('profit_factor')} max_l={r.get('max_consec_losses')} best_day%={r.get('best_day_share_pct')} "
            f"orders={r.get('orders')} stress_days={r.get('stress_days')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
