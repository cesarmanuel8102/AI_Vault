import base64
import hashlib
import json
import re
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase31_fastpass_vol_expansion.py")
RESTORE_MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase31_fastpass_vol_expansion_2026-04-25.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase31_fastpass_vol_expansion_2026-04-25.txt")


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
    if len(code) > 63000:
        payload = base64.b64encode(zlib.compress(code.encode("utf-8"), 9)).decode("ascii")
        code = "import base64,zlib\nexec(zlib.decompress(base64.b64decode('" + payload + "')).decode('utf-8'))\n"
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
        "days_to_6pct": pi(rt(rts, "DaysTo6Pct")),
        "profit_factor": pf(rt(rts, "ProfitFactor")),
        "tr_orb": pi(rt(rts, "TrORB")),
        "tr_mr": pi(rt(rts, "TrMR")),
        "tr_stress": pi(rt(rts, "TrST")),
        "tr_volx": pi(rt(rts, "TrVOLX")),
        "pnl_orb": pf(rt(rts, "PnlORB")),
        "pnl_volx": pf(rt(rts, "PnlVOLX")),
    }


def isolated_base():
    return {
        "alpha_mr_enabled": 0,
        "alpha_orb_enabled": 0,
        "alpha_stress_enabled": 0,
        "alpha_daytype_enabled": 0,
        "alpha_volx_enabled": 1,
        "trade_mnq": 1,
        "trade_mes": 1,
        "allow_shorts": 1,
        "trailing_lock_mode": "EOD",
        "guard_enabled": 1,
        "dynamic_risk_enabled": 1,
        "challenge_target_pct": 0.06,
        "max_open_positions": 2,
        "max_trades_per_symbol_day": 2,
        "daily_loss_limit_pct": 0.012,
        "daily_profit_lock_pct": 0.020,
        "trailing_dd_limit_pct": 0.035,
        "max_contracts_per_trade": 3,
        "ext_vixy_ratio_threshold": 1.03,
    }


def candidates():
    specs = [("P31_BASE_REF", {})]
    base = isolated_base()
    variants = [
        (
            "P31_A_COMP026",
            {
                "p31_entry_hour": 10,
                "p31_entry_min": 45,
                "p31_or_minutes": 20,
                "p31_compression_max_width_atr": 0.26,
                "p31_min_expansion_mult": 1.35,
                "p31_min_current_range_atr": 0.38,
                "p31_min_mom_pct": 0.0012,
                "p31_stop_atr_mult": 0.50,
                "p31_target_atr_mult": 1.55,
                "p31_risk": 0.0080,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
        (
            "P31_B_COMP030",
            {
                "p31_entry_hour": 10,
                "p31_entry_min": 45,
                "p31_or_minutes": 20,
                "p31_compression_max_width_atr": 0.30,
                "p31_min_expansion_mult": 1.25,
                "p31_min_current_range_atr": 0.35,
                "p31_min_mom_pct": 0.0010,
                "p31_stop_atr_mult": 0.50,
                "p31_target_atr_mult": 1.60,
                "p31_risk": 0.0080,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
        (
            "P31_C_STRICT",
            {
                "p31_entry_hour": 10,
                "p31_entry_min": 45,
                "p31_or_minutes": 20,
                "p31_compression_max_width_atr": 0.22,
                "p31_min_expansion_mult": 1.50,
                "p31_min_current_range_atr": 0.45,
                "p31_min_mom_pct": 0.0015,
                "p31_stop_atr_mult": 0.48,
                "p31_target_atr_mult": 1.80,
                "p31_risk": 0.0075,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
        (
            "P31_D_FAST",
            {
                "p31_entry_hour": 10,
                "p31_entry_min": 30,
                "p31_or_minutes": 15,
                "p31_compression_max_width_atr": 0.24,
                "p31_min_expansion_mult": 1.35,
                "p31_min_current_range_atr": 0.38,
                "p31_min_mom_pct": 0.0012,
                "p31_stop_atr_mult": 0.50,
                "p31_target_atr_mult": 1.55,
                "p31_risk": 0.0090,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
        (
            "P31_E_LATE",
            {
                "p31_entry_hour": 11,
                "p31_entry_min": 0,
                "p31_or_minutes": 30,
                "p31_compression_max_width_atr": 0.28,
                "p31_min_expansion_mult": 1.30,
                "p31_min_current_range_atr": 0.35,
                "p31_min_mom_pct": 0.0011,
                "p31_stop_atr_mult": 0.50,
                "p31_target_atr_mult": 1.65,
                "p31_risk": 0.0080,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
        (
            "P31_F_SECOND",
            {
                "p31_entry_hour": 10,
                "p31_entry_min": 45,
                "p31_second_entry_enabled": 1,
                "p31_second_entry_hour": 11,
                "p31_second_entry_min": 20,
                "p31_or_minutes": 20,
                "p31_compression_max_width_atr": 0.30,
                "p31_min_expansion_mult": 1.25,
                "p31_min_current_range_atr": 0.35,
                "p31_min_mom_pct": 0.0010,
                "p31_stop_atr_mult": 0.50,
                "p31_target_atr_mult": 1.55,
                "p31_risk": 0.0080,
                "p31_max_contracts": 1,
                "p31_strong_max_contracts": 2,
            },
        ),
    ]
    for label, extra in variants:
        ov = dict(base)
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


def ge_num(left, right):
    if left is None or right is None:
        return False
    return left >= right


def score_candidate(scenarios, baseline):
    is_s = scenarios.get("IS_2022_2024", {})
    oos = scenarios.get("OOS_2025_2026Q1", {})
    stress = scenarios.get("STRESS_2020", {})
    recent = scenarios.get("RECENT_0401_0424", {})
    week = scenarios.get("LIVE_WEEK_0420_0424", {})
    dds = [r.get("dd_pct") for r in scenarios.values() if r.get("dd_pct") is not None]
    checks = {
        "is_positive": (is_s.get("np_pct") is not None and is_s.get("np_pct") > 0),
        "oos_ge_baseline": ge_num(oos.get("np_pct"), baseline.get("OOS_2025_2026Q1", {}).get("np_pct")),
        "stress_positive": (stress.get("np_pct") is not None and stress.get("np_pct") > 0),
        "dd_ok": bool(dds) and max(dds) <= 3.5,
        "breaches_zero": all((r.get("dbr") or 0) == 0 and (r.get("tbr") or 0) == 0 for r in scenarios.values()),
        "recent_positive": (recent.get("np_pct") is not None and recent.get("np_pct") > 0),
        "live_week_non_negative": (week.get("np_pct") is not None and week.get("np_pct") >= 0),
    }
    passed = all(checks.values())
    dt6 = [r.get("days_to_6pct") for r in scenarios.values() if r.get("days_to_6pct") is not None and r.get("days_to_6pct") > 0]
    best_days_to_6 = min(dt6) if dt6 else -1
    volx_trades = sum((r.get("tr_volx") or 0) for r in scenarios.values())
    speed_proxy = (
        0.40 * (oos.get("np_pct") or 0)
        + 0.25 * (stress.get("np_pct") or 0)
        + 1.25 * (recent.get("np_pct") or 0)
        + 1.50 * (week.get("np_pct") or 0)
    )
    if best_days_to_6 > 0:
        speed_proxy += max(0.0, 20.0 - best_days_to_6) * 0.25
    return {
        "pass": passed,
        "checks": checks,
        "speed_proxy": round(speed_proxy, 4),
        "best_days_to_6pct": best_days_to_6,
        "volx_trades": volx_trades,
    }


def main():
    uid, tok = creds()
    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update({"trade_mnq": 1, "trade_mes": 1, "allow_shorts": 1})

    rows = []
    by = {}
    cid = None
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

        baseline = by.get("P31_BASE_REF", {}).get("scenarios", {})
        decision = {}
        for label, data in by.items():
            if label == "P31_BASE_REF":
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
            lines.append(
                f"{sname} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} "
                f"dbr={r.get('dbr')} tbr={r.get('tbr')} days6={r.get('days_to_6pct')} trVOLX={r.get('tr_volx')}"
            )
        lines.append("")
        lines.append("RANKED:")
        for label, dec in ranked:
            sc = by[label]["scenarios"]
            lines.append(
                f"{label} pass={dec['pass']} speed_proxy={dec['speed_proxy']} best_days6={dec['best_days_to_6pct']} "
                f"volx_trades={dec['volx_trades']} checks={dec['checks']}"
            )
            for sname in ("IS_2022_2024", "OOS_2025_2026Q1", "STRESS_2020", "RECENT_0401_0424", "LIVE_WEEK_0420_0424"):
                r = sc.get(sname, {})
                lines.append(
                    f"  {sname} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} "
                    f"dbr={r.get('dbr')} tbr={r.get('tbr')} days6={r.get('days_to_6pct')} "
                    f"pf={r.get('profit_factor')} trVOLX={r.get('tr_volx')} pnlVOLX={r.get('pnl_volx')}"
                )
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
