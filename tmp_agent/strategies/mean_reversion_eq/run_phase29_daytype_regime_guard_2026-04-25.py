import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase25_pf200_daytype_continuation.py")
RESTORE_MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase29_daytype_regime_guard_2026-04-25.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase29_daytype_regime_guard_2026-04-25.txt")


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
        time.sleep(min(3 * (i + 1), 20))
    return last or {"success": False, "errors": ["request failed"]}


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def pi(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
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


def upload_main(uid, tok, path):
    code = path.read_text(encoding="utf-8")
    r = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not r.get("success", False):
        raise RuntimeError(f"files/update failed: {r}")


def compile_project(uid, tok):
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(200):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def set_params(uid, tok, params):
    wr = post(
        uid,
        tok,
        "projects/update",
        {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]},
        timeout=90,
    )
    if not wr.get("success", False):
        raise RuntimeError(f"projects/update failed: {wr}")


def run_backtest(uid, tok, compile_id, name):
    bid = None
    err = None
    for _ in range(45):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(45)
            continue
        return {"status": "CreateFailed", "error": err}
    if not bid:
        return {"status": "CreateFailed", "error": err or "missing backtest id"}

    bt = {}
    for _ in range(540):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            break
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": bt.get("error") or bt.get("message")}
        time.sleep(10)

    rd2 = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
    bt = rd2.get("backtest") or bt
    s = bt.get("statistics") or {}
    rts = bt.get("runtimeStatistics") or {}
    return {
        "status": str(bt.get("status", "")),
        "backtest_id": bid,
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "orders": pi(s.get("Total Orders")),
        "dbr": pi(rt(rts, "DailyLossBreaches")),
        "tbr": pi(rt(rts, "TrailingBreaches")),
        "tr_orb": pi(rt(rts, "TrORB")),
        "tr_mr": pi(rt(rts, "TrMR")),
        "tr_stress": pi(rt(rts, "TrST")),
        "pnl_orb": pf(rt(rts, "PnlORB")),
    }


def candidates():
    base_iso = {
        "alpha_orb_enabled": 0,
        "alpha_stress_enabled": 0,
        "alpha_daytype_enabled": 1,
        "p25_require_or_breakout": 0,
        "p25_require_cross_alignment": 0,
        "p25_require_trend_alignment": 1,
        "p25_entry_hour": 11,
        "p25_entry_min": 0,
        "p25_min_intraday_mom_pct": 0.0008,
        "p25_min_day_range_atr": 0.10,
        "p25_max_day_range_atr": 99.0,
        "p25_stop_atr_mult": 0.55,
        "p25_target_atr_mult": 1.80,
        "p25_risk": 0.010,
        "p25_max_contracts": 2,
        "max_contracts_per_trade": 2,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.040,
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 2,
    }
    specs = [("P29_BASE_REF", {})]
    variants = [
        ("P29_ORIG_R010_C2", {}),
        ("P29_VIX1025", {"ext_vixy_ratio_threshold": 1.025}),
        ("P29_VIX1020", {"ext_vixy_ratio_threshold": 1.020}),
        ("P29_VIX1015", {"ext_vixy_ratio_threshold": 1.015}),
        ("P29_VIX1010", {"ext_vixy_ratio_threshold": 1.010}),
        ("P29_CAP110", {"p25_max_day_range_atr": 1.10}),
        ("P29_CAP125", {"p25_max_day_range_atr": 1.25}),
        ("P29_CAP150", {"p25_max_day_range_atr": 1.50}),
        ("P29_VIX102_CAP125", {"ext_vixy_ratio_threshold": 1.020, "p25_max_day_range_atr": 1.25}),
        ("P29_VIX1025_MOM10", {"ext_vixy_ratio_threshold": 1.025, "p25_min_intraday_mom_pct": 0.0010}),
        ("P29_VIX102_MOM12", {"ext_vixy_ratio_threshold": 1.020, "p25_min_intraday_mom_pct": 0.0012}),
        ("P29_VIX102_ENTRY1115", {"ext_vixy_ratio_threshold": 1.020, "p25_entry_hour": 11, "p25_entry_min": 15}),
        ("P29_R012_C1_GUARD", {"p25_risk": 0.012, "p25_max_contracts": 1, "max_contracts_per_trade": 1, "ext_vixy_ratio_threshold": 1.020}),
    ]
    for label, extra in variants:
        ov = dict(base_iso)
        ov.update(extra)
        specs.append((label, ov))
    return specs


def scenario_defs():
    return [
        ("IS_2022_2024", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("RECENT_0401_0424", {"start_year": 2026, "start_month": 4, "start_day": 1, "end_year": 2026, "end_month": 4, "end_day": 24}),
        ("LIVE_WEEK_0420_0424", {"start_year": 2026, "start_month": 4, "start_day": 20, "end_year": 2026, "end_month": 4, "end_day": 24}),
    ]


def val(dct, key):
    value = dct.get(key)
    return value if value is not None else None


def ge_num(left, right):
    if left is None or right is None:
        return False
    return left >= right


def score_candidate(scenarios, baseline):
    oos = scenarios.get("OOS_2025_2026Q1", {})
    stress = scenarios.get("STRESS_2020", {})
    recent = scenarios.get("RECENT_0401_0424", {})
    week = scenarios.get("LIVE_WEEK_0420_0424", {})
    checks = {
        "oos_ge_baseline": ge_num(val(oos, "np_pct"), val(baseline.get("OOS_2025_2026Q1", {}), "np_pct")),
        "stress_positive": (val(stress, "np_pct") is not None and val(stress, "np_pct") > 0),
        "stress_dd_ok": (stress.get("dd_pct") is not None and stress.get("dd_pct") <= 3.2),
        "breaches_zero": all((r.get("dbr") or 0) == 0 and (r.get("tbr") or 0) == 0 for r in scenarios.values()),
        "recent_positive": (val(recent, "np_pct") is not None and val(recent, "np_pct") > 0),
        "live_week_non_negative": (val(week, "np_pct") is not None and val(week, "np_pct") >= 0),
    }
    passed = all(checks.values())
    speed_proxy = (recent.get("np_pct") or 0) + 0.35 * (oos.get("np_pct") or 0) + 0.25 * (stress.get("np_pct") or 0)
    return {"pass": passed, "checks": checks, "speed_proxy": round(speed_proxy, 4)}


def main():
    uid, tok = creds()
    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update({"trade_mnq": 1, "trade_mes": 1, "allow_shorts": 1})

    rows = []
    by = {}
    try:
        upload_main(uid, tok, MAIN_PATH)
        cid = compile_project(uid, tok)
        for label, ov in candidates():
            by[label] = {"overrides": ov, "scenarios": {}}
            cfg = dict(base)
            cfg.update(ov)
            for sname, dates in scenario_defs():
                p = dict(cfg)
                p.update(dates)
                set_params(uid, tok, p)
                rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
                rr.update({"candidate": label, "scenario": sname, "overrides": ov})
                rows.append(rr)
                by[label]["scenarios"][sname] = rr
                OUT_JSON.write_text(
                    json.dumps(
                        {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": cid, "rows": rows, "by": by},
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        baseline = by.get("P29_BASE_REF", {}).get("scenarios", {})
        decision = {}
        for label, data in by.items():
            if label == "P29_BASE_REF":
                continue
            decision[label] = score_candidate(data.get("scenarios", {}), baseline)
            decision[label]["overrides"] = data.get("overrides", {})

        final = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "compile_id": cid,
            "rows": rows,
            "by": by,
            "decision": decision,
        }
        OUT_JSON.write_text(json.dumps(final, indent=2), encoding="utf-8")

        ranked = sorted(decision.items(), key=lambda kv: (kv[1]["pass"], kv[1]["speed_proxy"]), reverse=True)
        lines = [f"generated_at_utc={final['generated_at_utc']}", f"compile_id={cid}", ""]
        lines.append("BASELINE:")
        for sname, r in baseline.items():
            lines.append(f"{sname} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} dbr={r.get('dbr')} tbr={r.get('tbr')}")
        lines.append("")
        lines.append("RANKED:")
        for label, dec in ranked:
            sc = by[label]["scenarios"]
            lines.append(f"{label} pass={dec['pass']} speed_proxy={dec['speed_proxy']} checks={dec['checks']}")
            for sname in ("IS_2022_2024", "OOS_2025_2026Q1", "STRESS_2020", "RECENT_0401_0424", "LIVE_WEEK_0420_0424"):
                r = sc.get(sname, {})
                lines.append(f"  {sname} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} dbr={r.get('dbr')} tbr={r.get('tbr')}")
            lines.append(f"  overrides={dec['overrides']}")
        OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(str(OUT_JSON))
    finally:
        try:
            upload_main(uid, tok, RESTORE_MAIN_PATH)
            set_params(uid, tok, base)
        except Exception as exc:
            print(f"restore failed: {exc}")


if __name__ == "__main__":
    main()
