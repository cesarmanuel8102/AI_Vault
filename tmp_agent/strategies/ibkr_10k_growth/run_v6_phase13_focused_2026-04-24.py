import base64
import hashlib
import json
import math
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 30507388
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/main_v6_hybrid_turbo.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v6_phase13_focused_2026-04-24.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/v6_phase13_focused_2026-04-24.txt")


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


def load_state():
    if not OUT_JSON.exists():
        return {"stage_a_rows": [], "stage_b_rows": [], "candidate_params": {}}
    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"stage_a_rows": [], "stage_b_rows": [], "candidate_params": {}}


def save_state(state):
    state["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["project_id"] = PROJECT_ID
    OUT_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")

    lines = [f"generated_at_utc={state['generated_at_utc']}", f"project_id={PROJECT_ID}", ""]
    lines.append("STAGE_A")
    for r in state.get("stage_a_rows", []):
        lines.append(
            f"{r['candidate']} {r['scenario']} m_eq={r.get('monthly_equiv_pct')} dd={r.get('dd_pct')} "
            f"sharpe={r.get('sharpe')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("STAGE_B")
    for r in state.get("stage_b_rows", []):
        lines.append(
            f"{r['candidate']} {r['scenario']} m_eq={r.get('monthly_equiv_pct')} dd={r.get('dd_pct')} "
            f"sharpe={r.get('sharpe')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_candidates():
    base_ref = {
        "lookback_fast": 63,
        "lookback_slow": 252,
        "w_fast": 0.35,
        "w_slow": 0.65,
        "vol_penalty": 0.65,
        "core_gross_risk_on": 3.8,
        "core_gross_risk_off": 0.7,
        "turbo_gross": 5.2,
        "max_total_gross": 8.8,
        "max_single_weight": 3.2,
        "max_core_active": 2,
        "max_turbo_active": 1,
        "vixy_ratio_riskoff": 1.25,
        "vixy_ratio_bull": 1.20,
        "bull_sma_buffer": 1.0,
        "bull_mom_threshold": -2.0,
        "rebalance_buffer": 0.015,
        "bear_hedge_enabled": 0,
        "bear_hedge_weight": 0.25,
        "bear_trigger_mom": -1.0,
        "bear_sma_mult": 1.0,
        "rebalance_daily": 1,
        "circuit_dd_pct": 0.95,
        "cooldown_days": 20,
    }

    rng = random.Random(2026042402)
    candidates = [("V6P13_REF", dict(base_ref))]

    # Deterministic micro-variants around the reference
    deterministic = [
        ("V6P13_MV_01", {"bear_hedge_enabled": 1, "bear_hedge_weight": 0.10, "bear_trigger_mom": -1.8, "bear_sma_mult": 1.0}),
        ("V6P13_MV_02", {"vixy_ratio_riskoff": 1.23, "vixy_ratio_bull": 1.18}),
        ("V6P13_MV_03", {"vixy_ratio_riskoff": 1.27, "vixy_ratio_bull": 1.22}),
        ("V6P13_MV_04", {"max_turbo_active": 2, "max_total_gross": 9.4, "max_single_weight": 2.8}),
        ("V6P13_MV_05", {"core_gross_risk_on": 4.0, "turbo_gross": 5.4, "max_total_gross": 9.1}),
        ("V6P13_MV_06", {"core_gross_risk_on": 3.6, "turbo_gross": 4.9, "max_total_gross": 8.2, "vol_penalty": 0.72}),
        ("V6P13_MV_07", {"lookback_fast": 42, "lookback_slow": 189, "w_fast": 0.45, "w_slow": 0.55}),
        ("V6P13_MV_08", {"bull_mom_threshold": -2.8, "bull_sma_buffer": 0.998}),
    ]
    for label, ov in deterministic:
        p = dict(base_ref)
        p.update(ov)
        candidates.append((label, p))

    for i in range(1, 29):
        use_fast = rng.random() < 0.45
        look_fast = 21 if use_fast else (42 if rng.random() < 0.5 else 63)
        look_slow = 126 if use_fast else (189 if rng.random() < 0.5 else 252)
        w_fast = round(rng.uniform(0.28, 0.68), 3)
        w_slow = round(max(0.2, 1.0 - w_fast), 3)

        core_on = round(rng.uniform(3.4, 4.8), 3)
        turbo = round(rng.uniform(4.8, 6.6), 3)
        max_total = round(max(core_on + turbo - rng.uniform(0.3, 1.0), rng.uniform(8.5, 10.4)), 3)
        vixy_off = round(rng.uniform(1.22, 1.30), 3)
        vixy_bull = round(min(vixy_off - 0.02, rng.uniform(1.17, 1.24)), 3)
        hedged = 1 if rng.random() < 0.28 else 0

        p = {
            "lookback_fast": look_fast,
            "lookback_slow": look_slow,
            "w_fast": w_fast,
            "w_slow": w_slow,
            "vol_penalty": round(rng.uniform(0.55, 0.80), 3),
            "core_gross_risk_on": core_on,
            "core_gross_risk_off": round(rng.uniform(0.65, 0.95), 3),
            "turbo_gross": turbo,
            "max_total_gross": max_total,
            "max_single_weight": round(rng.uniform(2.8, 4.0), 3),
            "max_core_active": rng.choice([2, 3]),
            "max_turbo_active": rng.choice([1, 2]),
            "vixy_ratio_riskoff": vixy_off,
            "vixy_ratio_bull": vixy_bull,
            "bull_sma_buffer": round(rng.uniform(0.996, 1.008), 4),
            "bull_mom_threshold": round(rng.uniform(-3.3, 0.2), 3),
            "rebalance_buffer": round(rng.uniform(0.010, 0.020), 3),
            "bear_hedge_enabled": hedged,
            "bear_hedge_weight": round(rng.uniform(0.10, 0.30), 3),
            "bear_trigger_mom": round(rng.uniform(-2.2, -0.7), 3),
            "bear_sma_mult": round(rng.uniform(0.99, 1.006), 4),
            "rebalance_daily": 1,
            "circuit_dd_pct": round(rng.uniform(0.91, 0.95), 3),
            "cooldown_days": rng.choice([15, 20]),
        }
        candidates.append((f"V6P13_RS_{i:02d}", p))
    return candidates


def stage_a_score(rows_by_candidate):
    ranked = []
    for c, rows in rows_by_candidate.items():
        o = rows.get("OOS_2023_2026Q1", {}).get("monthly_equiv_pct")
        r = rows.get("RECENT_2025_2026Q1", {}).get("monthly_equiv_pct")
        if o is None or r is None:
            continue
        # Prioritize high return while discouraging low-quality plateaus.
        score = 0.50 * float(o) + 0.50 * float(r)
        if float(o) < 2.2:
            score -= 0.6
        if float(r) < 3.0:
            score -= 0.6
        ranked.append((score, c, float(o), float(r)))
    return sorted(ranked, reverse=True)


def main():
    uid, tok = creds()
    state = load_state()

    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    common = {
        "initial_cash": 10000,
        "atr_period": 20,
        "sma_filter_period": 200,
        "vixy_sma_period": 20,
        "min_core_signal": 0.0,
        "min_turbo_signal": 0.02,
    }

    candidates = make_candidates()
    candidate_params = state.get("candidate_params", {})
    for label, p in candidates:
        candidate_params[label] = p
    state["candidate_params"] = candidate_params

    stage_a_scenarios = [
        ("OOS_2023_2026Q1", {"start_year": 2023, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("RECENT_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
    ]
    stage_b_scenarios = [
        ("FULL_2018_2026Q1", {"start_year": 2018, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("BEAR_2022", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2022, "end_month": 12, "end_day": 31}),
    ]

    done_a = {(r.get("candidate"), r.get("scenario")) for r in state.get("stage_a_rows", [])}
    for label, p in candidates:
        cfg = dict(common)
        cfg.update(p)
        for sname, dates in stage_a_scenarios:
            key = (label, sname)
            if key in done_a:
                continue
            params = dict(cfg)
            params.update(dates)
            set_params(uid, tok, params)
            bt = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            sm = summarize(bt)
            sm.update({"candidate": label, "scenario": sname, "stage": "A"})
            state.setdefault("stage_a_rows", []).append(sm)
            done_a.add(key)
            save_state(state)

    by_cand = {}
    for r in state.get("stage_a_rows", []):
        by_cand.setdefault(r["candidate"], {})
        by_cand[r["candidate"]][r["scenario"]] = r

    ranked = stage_a_score(by_cand)
    top_labels = [c for _, c, _, _ in ranked[:8]]
    if "V6P13_REF" not in top_labels:
        top_labels.append("V6P13_REF")

    done_b = {(r.get("candidate"), r.get("scenario")) for r in state.get("stage_b_rows", [])}
    for label in top_labels:
        p = candidate_params[label]
        cfg = dict(common)
        cfg.update(p)
        for sname, dates in stage_b_scenarios:
            key = (label, sname)
            if key in done_b:
                continue
            params = dict(cfg)
            params.update(dates)
            set_params(uid, tok, params)
            bt = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            sm = summarize(bt)
            sm.update({"candidate": label, "scenario": sname, "stage": "B"})
            state.setdefault("stage_b_rows", []).append(sm)
            done_b.add(key)
            save_state(state)

    # Final summary lines
    ref = {}
    top_map = {}
    for r in state.get("stage_a_rows", []):
        if r["candidate"] in top_labels:
            top_map.setdefault(r["candidate"], {})[r["scenario"]] = r
    for r in state.get("stage_b_rows", []):
        if r["candidate"] in top_labels:
            top_map.setdefault(r["candidate"], {})[r["scenario"]] = r
            if r["candidate"] == "V6P13_REF":
                ref[r["scenario"]] = r

    final_rank = []
    for c in top_labels:
        x = top_map.get(c, {})
        o = (x.get("OOS_2023_2026Q1") or {}).get("monthly_equiv_pct")
        r = (x.get("RECENT_2025_2026Q1") or {}).get("monthly_equiv_pct")
        f = (x.get("FULL_2018_2026Q1") or {}).get("monthly_equiv_pct")
        s = (x.get("STRESS_2020") or {}).get("monthly_equiv_pct")
        b = (x.get("BEAR_2022") or {}).get("monthly_equiv_pct")
        if None in (o, r, f, s, b):
            continue
        # Final ranking for decision making.
        score = 0.42 * float(o) + 0.38 * float(r) + 0.10 * float(s) + 0.10 * float(b)
        final_rank.append((score, c, float(o), float(r), float(f), float(s), float(b)))
    final_rank.sort(reverse=True)
    state["final_rank"] = [
        {
            "score": x[0],
            "candidate": x[1],
            "oos_m_eq": x[2],
            "recent_m_eq": x[3],
            "full_m_eq": x[4],
            "stress_m_eq": x[5],
            "bear_m_eq": x[6],
        }
        for x in final_rank
    ]
    save_state(state)

    print(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "out_json": str(OUT_JSON),
                "out_txt": str(OUT_TXT),
                "stage_a_rows": len(state.get("stage_a_rows", [])),
                "stage_b_rows": len(state.get("stage_b_rows", [])),
                "top_labels": top_labels,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
