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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/main_v12_gate_only.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v12_phase2_risk_realism_2026-04-24.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v12_phase2_risk_realism_2026-04-24.txt")


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
    for i in range(8):
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
        time.sleep(min(4 * (i + 1), 30))
    return last or {"success": False, "errors": ["request failed"]}


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    r = post(uid, tok, "projects/update", payload, timeout=120)
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
    for _ in range(260):
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
    for _ in range(50):
        bc = post(
            uid,
            tok,
            "backtests/create",
            {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
            timeout=120,
        )
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
    for _ in range(700):
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
        "psr_pct": pf(s.get("Probabilistic Sharpe Ratio")),
    }


def load_rows():
    if not OUT_JSON.exists():
        return []
    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8")).get("rows", [])
    except Exception:
        return []


def save_rows(rows):
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "project_id": PROJECT_ID,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"project_id={PROJECT_ID}", ""]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} cagr={r.get('cagr_pct')} m_eq={r.get('monthly_equiv_pct')} "
            f"dd={r.get('dd_pct')} sharpe={r.get('sharpe')} sortino={r.get('sortino')} wr={r.get('win_rate_pct')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    uid, tok = creds()
    rows = load_rows()
    done = {(r.get("candidate"), r.get("scenario")) for r in rows}

    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = {
        "initial_cash": 10000,
        "rebalance_daily": 1,
    }

    candidates = [
        (
            "V12D_REAL_BASE",
            {
                "core_gross_base": 4.1,
                "turbo_gross_base": 5.6,
                "max_total_gross": 9.5,
                "max_single_weight": 3.5,
                "exp_stress_up": 0.65,
                "exp_chop": 0.22,
                "exp_neutral": 0.38,
                "turbo_mult_stress": 0.05,
                "bull_vixy_max": 1.23,
                "stress_vixy_min": 1.10,
                "stress_vixy_max": 1.28,
                "safe_overlay_stress": 0.12,
                "safe_overlay_chop": 0.12,
                "safe_overlay_neutral": 0.08,
                "circuit_dd_pct": 0.12,
                "daily_loss_limit_pct": 0.02,
                "monthly_dd_throttle_trigger": 0.08,
                "monthly_dd_throttle_mult": 0.50,
                "friction_mode": 0,
                "max_wchg_per_reb": 1.0,
            },
        ),
        (
            "V12D_REAL_CONSERV",
            {
                "core_gross_base": 4.0,
                "turbo_gross_base": 5.4,
                "max_total_gross": 9.2,
                "max_single_weight": 3.4,
                "exp_stress_up": 0.60,
                "exp_chop": 0.20,
                "exp_neutral": 0.35,
                "turbo_mult_stress": 0.00,
                "bull_vixy_max": 1.22,
                "stress_vixy_min": 1.10,
                "stress_vixy_max": 1.27,
                "safe_overlay_stress": 0.15,
                "safe_overlay_chop": 0.15,
                "safe_overlay_neutral": 0.10,
                "circuit_dd_pct": 0.10,
                "daily_loss_limit_pct": 0.018,
                "monthly_dd_throttle_trigger": 0.07,
                "monthly_dd_throttle_mult": 0.45,
                "friction_mode": 0,
                "max_wchg_per_reb": 1.0,
            },
        ),
        (
            "V12D_FRICTION_STRESS",
            {
                "core_gross_base": 4.1,
                "turbo_gross_base": 5.6,
                "max_total_gross": 9.5,
                "max_single_weight": 3.5,
                "exp_stress_up": 0.65,
                "exp_chop": 0.22,
                "exp_neutral": 0.38,
                "turbo_mult_stress": 0.05,
                "bull_vixy_max": 1.23,
                "stress_vixy_min": 1.10,
                "stress_vixy_max": 1.28,
                "safe_overlay_stress": 0.12,
                "safe_overlay_chop": 0.12,
                "safe_overlay_neutral": 0.08,
                "circuit_dd_pct": 0.12,
                "daily_loss_limit_pct": 0.02,
                "monthly_dd_throttle_trigger": 0.08,
                "monthly_dd_throttle_mult": 0.50,
                "friction_mode": 1,
                "friction_slippage_abs": 0.02,
                "friction_exposure_haircut": 0.06,
                "max_wchg_per_reb": 0.35,
            },
        ),
        (
            "V12D_FRICTION_HARD",
            {
                "core_gross_base": 4.1,
                "turbo_gross_base": 5.6,
                "max_total_gross": 9.5,
                "max_single_weight": 3.5,
                "exp_stress_up": 0.60,
                "exp_chop": 0.20,
                "exp_neutral": 0.35,
                "turbo_mult_stress": 0.00,
                "bull_vixy_max": 1.22,
                "stress_vixy_min": 1.10,
                "stress_vixy_max": 1.26,
                "safe_overlay_stress": 0.18,
                "safe_overlay_chop": 0.18,
                "safe_overlay_neutral": 0.10,
                "circuit_dd_pct": 0.10,
                "daily_loss_limit_pct": 0.018,
                "monthly_dd_throttle_trigger": 0.07,
                "monthly_dd_throttle_mult": 0.45,
                "friction_mode": 1,
                "friction_slippage_abs": 0.03,
                "friction_exposure_haircut": 0.10,
                "max_wchg_per_reb": 0.25,
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

    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        for sname, dates in scenarios:
            key = (label, sname)
            if key in done:
                continue
            params = dict(cfg)
            params.update(dates)
            set_params(uid, tok, params)
            bt = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            sm = summarize(bt)
            sm.update({"candidate": label, "scenario": sname})
            rows.append(sm)
            done.add(key)
            save_rows(rows)

    print(
        json.dumps(
            {"project_id": PROJECT_ID, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT), "rows": len(rows)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
