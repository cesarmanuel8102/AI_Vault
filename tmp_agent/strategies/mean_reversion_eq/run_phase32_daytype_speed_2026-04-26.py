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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase32_daytype_speed_2026-04-26.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase32_daytype_speed_2026-04-26.txt")

BASELINE = {
    "IS_2022_2024": {"np_pct": -1.068, "dd_pct": 3.1},
    "OOS_2025_2026Q1": {"np_pct": 7.451, "dd_pct": 2.8},
    "STRESS_2020": {"np_pct": 0.331, "dd_pct": 1.4},
    "RECENT_0401_0424": {"np_pct": -0.595, "dd_pct": 0.7},
    "LIVE_WEEK_0420_0424": {"np_pct": 0.0, "dd_pct": 0.0},
}


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()


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
    wr = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}, timeout=90)
    if not wr.get("success", False):
        raise RuntimeError(f"projects/update failed: {wr}")


def run_backtest(uid, tok, compile_id, name):
    bid = None
    for _ in range(45):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45)
            continue
        return {"status": "CreateFailed", "error": str(bc)}
    if not bid:
        return {"status": "CreateFailed", "error": "missing backtest id"}
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
        "tr_orb": pi(rt(rts, "TrORB")),
        "tr_stress": pi(rt(rts, "TrST")),
        "pnl_orb": pf(rt(rts, "PnlORB")),
    }


def base_params():
    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update({"trade_mnq": 1, "trade_mes": 1, "allow_shorts": 1, "challenge_target_pct": 0.06})
    return base


def r04_common():
    return {
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
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 2,
    }


def candidates():
    c = []
    # Standalone trend-day engine.
    for label, risk, maxc in [
        ("P32_ISO_R006_C1", 0.006, 1),
        ("P32_ISO_R010_C2", 0.010, 2),
        ("P32_ISO_R012_C1", 0.012, 1),
    ]:
        ov = {"alpha_orb_enabled": 0, "alpha_stress_enabled": 0, **r04_common()}
        ov.update({"p25_risk": risk, "p25_max_contracts": maxc, "max_contracts_per_trade": maxc})
        c.append((label, ov))

    # Sidecar: keep baseline ORB, add trend-day with limited risk.
    for label, risk, maxc in [
        ("P32_SIDE_R0025_C1", 0.0025, 1),
        ("P32_SIDE_R0040_C1", 0.0040, 1),
        ("P32_SIDE_R0060_C1", 0.0060, 1),
    ]:
        ov = {**r04_common()}
        ov.update({"p25_risk": risk, "p25_max_contracts": maxc, "max_contracts_per_trade": max(8, maxc)})
        c.append((label, ov))

    # Defensive standalone that previously improved recent/live.
    ov = {"alpha_orb_enabled": 0, "alpha_stress_enabled": 0, **r04_common()}
    ov.update({"p25_stop_atr_mult": 0.50, "p25_target_atr_mult": 2.00, "p25_risk": 0.012, "p25_max_contracts": 1, "max_contracts_per_trade": 1, "ext_vixy_ratio_threshold": 1.02})
    c.append(("P32_ISO_STOP50_TGT20", ov))
    return c


def scenarios():
    return [
        ("IS_2022_2024", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("RECENT_0401_0424", {"start_year": 2026, "start_month": 4, "start_day": 1, "end_year": 2026, "end_month": 4, "end_day": 24}),
        ("LIVE_WEEK_0420_0424", {"start_year": 2026, "start_month": 4, "start_day": 20, "end_year": 2026, "end_month": 4, "end_day": 24}),
    ]


def score(sc):
    oos, stress, recent, week = sc.get("OOS_2025_2026Q1", {}), sc.get("STRESS_2020", {}), sc.get("RECENT_0401_0424", {}), sc.get("LIVE_WEEK_0420_0424", {})
    dds = [r.get("dd_pct") for r in sc.values() if r.get("dd_pct") is not None]
    checks = {
        "oos_ge_baseline": oos.get("np_pct") is not None and oos["np_pct"] >= BASELINE["OOS_2025_2026Q1"]["np_pct"],
        "stress_ge_baseline": stress.get("np_pct") is not None and stress["np_pct"] >= BASELINE["STRESS_2020"]["np_pct"],
        "dd_ok": bool(dds) and max(dds) <= 3.5,
        "breaches_zero": all((r.get("dbr") or 0) == 0 and (r.get("tbr") or 0) == 0 for r in sc.values()),
        "recent_ge_baseline": recent.get("np_pct") is not None and recent["np_pct"] >= BASELINE["RECENT_0401_0424"]["np_pct"],
        "live_week_nonnegative": week.get("np_pct") is not None and week["np_pct"] >= 0,
    }
    dt6 = [r.get("days_to_6pct") for r in sc.values() if r.get("days_to_6pct") and r.get("days_to_6pct") > 0]
    best_days = min(dt6) if dt6 else -1
    speed = 0.5 * (oos.get("np_pct") or 0) + 0.35 * (stress.get("np_pct") or 0) + 1.2 * (recent.get("np_pct") or 0) + 1.4 * (week.get("np_pct") or 0)
    if best_days > 0:
        speed += max(0, 60 - best_days) * 0.08
    return {"pass": all(checks.values()), "checks": checks, "best_days_to_6pct": best_days, "speed_proxy": round(speed, 4)}


def main():
    uid, tok = creds()
    restore = base_params()
    rows, by = [], {}
    try:
        upload_main(uid, tok, MAIN_PATH)
        cid = compile_project(uid, tok)
        for label, ov in candidates():
            by[label] = {"overrides": ov, "scenarios": {}}
            cfg = base_params()
            cfg.update(ov)
            for sname, dates in scenarios():
                p = dict(cfg)
                p.update(dates)
                set_params(uid, tok, p)
                rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
                rr.update({"candidate": label, "scenario": sname, "overrides": ov})
                rows.append(rr)
                by[label]["scenarios"][sname] = rr
                OUT_JSON.write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": cid, "rows": rows, "by": by}, indent=2), encoding="utf-8")
        decision = {k: {**score(v["scenarios"]), "overrides": v["overrides"]} for k, v in by.items()}
        final = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "rows": rows, "by": by, "decision": decision, "baseline": BASELINE}
        OUT_JSON.write_text(json.dumps(final, indent=2), encoding="utf-8")
        ranked = sorted(decision.items(), key=lambda kv: (kv[1]["pass"], kv[1]["speed_proxy"]), reverse=True)
        lines = [f"generated_at_utc={final['generated_at_utc']}", ""]
        for label, dec in ranked:
            lines.append(f"{label} pass={dec['pass']} speed={dec['speed_proxy']} days6={dec['best_days_to_6pct']} checks={dec['checks']}")
            for sname in ("IS_2022_2024", "OOS_2025_2026Q1", "STRESS_2020", "RECENT_0401_0424", "LIVE_WEEK_0420_0424"):
                r = by[label]["scenarios"].get(sname, {})
                lines.append(f"  {sname} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} dbr/tbr={r.get('dbr')}/{r.get('tbr')} days6={r.get('days_to_6pct')} trORB={r.get('tr_orb')} trST={r.get('tr_stress')}")
            lines.append(f"  overrides={dec['overrides']}")
        OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(str(OUT_JSON))
    finally:
        try:
            upload_main(uid, tok, RESTORE_MAIN_PATH)
            set_params(uid, tok, restore)
        except Exception as exc:
            print(f"restore failed: {exc}")


if __name__ == "__main__":
    main()
