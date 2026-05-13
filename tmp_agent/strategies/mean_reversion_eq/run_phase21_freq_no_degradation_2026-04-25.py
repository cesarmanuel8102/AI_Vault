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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase21_freq_no_degradation_2026-04-25.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase21_freq_no_degradation_2026-04-25.txt")


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
    for i in range(7):
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
            m = re.search(r"Server Time:\\s*(\\d+)", " ".join(d.get("errors") or []))
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
    for _ in range(200):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


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
    for _ in range(520):
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
        "stress_days": pi(rt(rts, "ExternalStressDays")),
        "tr_mr": pi(rt(rts, "TrMR")),
        "tr_orb": pi(rt(rts, "TrORB")),
        "tr_stress": pi(rt(rts, "TrST")),
    }


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


def decision(rows):
    by = {}
    for r in rows:
        by.setdefault(r["candidate"], {})[r["scenario"]] = r

    baseline = by.get("P21_BASE_REF", {})
    out = {}

    for cand, sc in by.items():
        if cand == "P21_BASE_REF":
            continue

        # No-degradation checks on IS/OOS/STRESS
        checks = {}
        ok_all = True
        for key in ("IS_2022_2024", "OOS_2025_2026Q1", "STRESS_2020"):
            b = baseline.get(key, {})
            c = sc.get(key, {})
            cond = (
                c.get("np_pct") is not None
                and b.get("np_pct") is not None
                and c.get("np_pct") >= b.get("np_pct")
                and c.get("dd_pct") is not None
                and b.get("dd_pct") is not None
                and c.get("dd_pct") <= b.get("dd_pct")
                and (c.get("dbr") or 0) <= (b.get("dbr") or 0)
                and (c.get("tbr") or 0) <= (b.get("tbr") or 0)
            )
            checks[f"nodeg_{key}"] = cond
            ok_all = ok_all and cond

        # Frequency improvement on live-like weeks
        b_w1 = baseline.get("LIVE_WEEK_0420_0424", {}).get("orders") or 0
        c_w1 = sc.get("LIVE_WEEK_0420_0424", {}).get("orders") or 0
        b_w2 = baseline.get("LIVE_WEEK_0415_0421", {}).get("orders") or 0
        c_w2 = sc.get("LIVE_WEEK_0415_0421", {}).get("orders") or 0
        freq_better = (c_w1 > b_w1) or (c_w2 > b_w2)
        checks["freq_improves_week"] = freq_better
        ok_all = ok_all and freq_better

        out[cand] = {
            "pass": ok_all,
            "checks": checks,
            "baseline_week_orders": {"0420_0424": b_w1, "0415_0421": b_w2},
            "candidate_week_orders": {"0420_0424": c_w1, "0415_0421": c_w2},
        }

    return out


def main():
    uid, tok = creds()
    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update(
        {
            "trade_mnq": 1,
            "trade_mes": 1,
            "allow_shorts": 1,
        }
    )

    candidates = [
        ("P21_BASE_REF", {}),
        ("P21_FQ_A_ORW018", {"or_min_width_atr": 0.18}),
        ("P21_FQ_B_ORW018_BUF05", {"or_min_width_atr": 0.18, "or_breakout_buffer_pct": 0.0005}),
        ("P21_FQ_C_MR_LOW", {"alpha_mr_enabled": 1, "n_risk": 0.0035}),
        ("P21_FQ_D_MR_MICRO", {"alpha_mr_enabled": 1, "n_risk": 0.0025}),
        ("P21_FQ_E_VIX102", {"ext_vixy_ratio_threshold": 1.02}),
        (
            "P21_FQ_F_COMBO_SAFE",
            {
                "alpha_mr_enabled": 1,
                "n_risk": 0.0025,
                "or_risk": 0.0085,
                "or_min_width_atr": 0.18,
                "or_breakout_buffer_pct": 0.0005,
            },
        ),
    ]

    scenarios = [
        ("IS_2022_2024", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
        ("LIVE_WEEK_0420_0424", {"start_year": 2026, "start_month": 4, "start_day": 20, "end_year": 2026, "end_month": 4, "end_day": 24}),
        ("LIVE_WEEK_0415_0421", {"start_year": 2026, "start_month": 4, "start_day": 15, "end_year": 2026, "end_month": 4, "end_day": 21}),
    ]

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        for sname, dates in scenarios:
            p = dict(cfg)
            p.update(dates)
            set_params(uid, tok, p)
            rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            OUT_JSON.write_text(
                json.dumps(
                    {
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "compile_id": cid,
                        "rows": rows,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    dec = decision(rows)
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "compile_id": cid,
                "rows": rows,
                "decision": dec,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"compile_id={cid}", ""]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
            f"orders={r.get('orders')} tr_mr={r.get('tr_mr')} tr_orb={r.get('tr_orb')} tr_st={r.get('tr_stress')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("DECISION:")
    for k, v in dec.items():
        lines.append(f"{k} pass={v['pass']} checks={v['checks']} week_orders={v['candidate_week_orders']}")

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
