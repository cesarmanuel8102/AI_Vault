import base64
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 30507388
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/main_v7_regime_confidence.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v7_regime_phase1_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v7_regime_phase1_2026-04-22.txt")


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Missing QC credentials")
    return uid, tok


def hdr(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": str(ts), "Content-Type": "application/json"}


def post(uid, tok, ep, payload, timeout=120):
    last = None
    for i in range(6):
        ts = int(time.time())
        try:
            r = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts), json=payload, timeout=timeout)
            try:
                d = r.json()
            except Exception:
                d = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
            if r.status_code >= 400:
                d.setdefault("success", False)
            if d.get("success", False):
                return d
            m = re.search(r"Server Time:\s*(\d+)", " ".join(d.get("errors") or []))
            if m:
                ts2 = int(m.group(1)) - 1
                r2 = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
                try:
                    d2 = r2.json()
                except Exception:
                    d2 = {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
                if d2.get("success", False):
                    return d2
                d = d2
            last = d
        except Exception as e:
            last = {"success": False, "errors": [str(e)]}
        time.sleep(min(3 * (i + 1), 20))
    return last or {"success": False, "errors": ["request failed"]}


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    r = post(uid, tok, "projects/update", payload, timeout=90)
    if not r.get("success", False):
        raise RuntimeError(f"projects/update failed: {r}")


def upload_main(uid, tok):
    code = MAIN_PATH.read_text(encoding="utf-8")
    r = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not r.get("success", False):
        raise RuntimeError(f"files/update failed: {r}")


def compile_project(uid, tok):
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(240):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, compile_id, name):
    bid = None
    for _ in range(40):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45)
            continue
        raise RuntimeError(f"backtests/create failed: {bc}")
    if not bid:
        raise RuntimeError("backtest id missing")

    bt = {}
    for _ in range(600):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            break
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            raise RuntimeError(f"Backtest ended in {st}: {bt.get('error') or bt.get('message')}")
        time.sleep(10)
    rd2 = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
    return rd2.get("backtest") or bt


def summarize(bt):
    s = bt.get("statistics") or {}
    cagr = pf(s.get("Compounding Annual Return"))
    monthly = None
    if cagr is not None:
        monthly = (math.pow(1.0 + cagr / 100.0, 1.0 / 12.0) - 1.0) * 100.0
    return {
        "status": bt.get("status"),
        "backtest_id": bt.get("backtestId"),
        "np_pct": pf(s.get("Net Profit")),
        "cagr_pct": cagr,
        "monthly_equiv_pct": monthly,
        "dd_pct": pf(s.get("Drawdown")),
        "sharpe": pf(s.get("Sharpe Ratio")),
        "sortino": pf(s.get("Sortino Ratio")),
        "win_rate_pct": pf(s.get("Win Rate")),
    }


def main():
    uid, tok = creds()
    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = {
        "initial_cash": 10000,
        "lookback_fast": 63,
        "lookback_slow": 252,
        "atr_period": 20,
        "sma_filter_period": 200,
        "vixy_sma_period": 20,
        "w_fast": 0.4,
        "w_slow": 0.6,
        "vol_penalty": 0.65,
        "min_core_signal": 0.0,
        "min_turbo_signal": 0.015,
        "core_gross_low": 0.9,
        "core_gross_mid": 1.35,
        "core_gross_high": 1.75,
        "turbo_gross_mid": 0.45,
        "turbo_gross_high": 1.2,
        "bear_gross_mid": 0.35,
        "bear_gross_high": 0.75,
        "max_total_gross": 2.85,
        "max_single_weight": 0.85,
        "max_core_active": 4,
        "max_turbo_active_mid": 1,
        "max_turbo_active_high": 2,
        "rebalance_buffer": 0.02,
        "conf_bull_high": 0.72,
        "conf_bull_mid": 0.56,
        "conf_bear_high": 0.68,
        "conf_bear_mid": 0.54,
        "conf_stress": 0.70,
        "vixy_ratio_stress": 1.12,
        "vixy_ratio_riskoff": 1.05,
        "circuit_dd_pct": 0.42,
        "cooldown_days": 20,
    }

    candidates = [
        ("V7_REF", {}),
        (
            "V7_MORE_TRADES",
            {
                "conf_bull_mid": 0.50,
                "conf_bear_mid": 0.50,
                "rebalance_buffer": 0.015,
                "core_gross_mid": 1.45,
                "turbo_gross_mid": 0.60,
            },
        ),
        (
            "V7_AGGR_BULL",
            {
                "conf_bull_high": 0.66,
                "core_gross_high": 2.05,
                "turbo_gross_high": 1.55,
                "max_total_gross": 3.20,
                "max_single_weight": 1.0,
                "circuit_dd_pct": 0.50,
            },
        ),
        (
            "V7_BALANCED_PLUS",
            {
                "conf_bull_high": 0.69,
                "conf_bull_mid": 0.53,
                "core_gross_high": 1.85,
                "turbo_gross_high": 1.20,
                "bear_gross_high": 0.85,
                "vixy_ratio_riskoff": 1.04,
            },
        ),
        (
            "V7_FAST_MOM",
            {
                "lookback_fast": 21,
                "lookback_slow": 126,
                "w_fast": 0.65,
                "w_slow": 0.35,
                "conf_bull_high": 0.67,
                "conf_bull_mid": 0.50,
                "core_gross_high": 1.95,
                "turbo_gross_high": 1.35,
            },
        ),
    ]

    scenarios = [
        ("FULL_2018_2026Q1", {"start_year": 2018, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("OOS_2023_2026Q1", {"start_year": 2023, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("RECENT_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("BEAR_2022", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2022, "end_month": 12, "end_day": 31}),
    ]

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        for sname, dates in scenarios:
            p = dict(cfg)
            p.update(dates)
            set_params(uid, tok, p)
            bt = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            sm = summarize(bt)
            sm.update({"candidate": label, "scenario": sname})
            rows.append(sm)
            OUT_JSON.write_text(
                json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "project_id": PROJECT_ID, "rows": rows}, indent=2),
                encoding="utf-8",
            )

    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"project_id={PROJECT_ID}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} cagr={r.get('cagr_pct')} "
            f"m_eq={r.get('monthly_equiv_pct')} dd={r.get('dd_pct')} sharpe={r.get('sharpe')} "
            f"sortino={r.get('sortino')} wr={r.get('win_rate_pct')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"project_id": PROJECT_ID, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2))


if __name__ == "__main__":
    main()

