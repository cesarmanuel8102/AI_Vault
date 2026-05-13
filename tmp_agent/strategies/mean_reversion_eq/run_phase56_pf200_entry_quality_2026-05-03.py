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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase56_pf200_entry_quality.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase56_pf200_entry_quality_2026-05-03.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase56_pf200_entry_quality_2026-05-03.txt")


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


def strict_nodeg(base_res, cand_res):
    return (
        cand_res.get("np_pct") is not None
        and base_res.get("np_pct") is not None
        and cand_res.get("np_pct") >= base_res.get("np_pct")
        and cand_res.get("dd_pct") is not None
        and base_res.get("dd_pct") is not None
        and cand_res.get("dd_pct") <= base_res.get("dd_pct")
        and (cand_res.get("dbr") or 0) <= (base_res.get("dbr") or 0)
        and (cand_res.get("tbr") or 0) <= (base_res.get("tbr") or 0)
    )


def build_candidates():
    return [
        ("P56_BASE_REF", {}),
        ("P56_Q01_VWAP", {
            "or_require_vwap_alignment": 1,
            "or_min_vwap_dev_pct": 0.00010,
        }),
        ("P56_Q02_VWAP_RVOL", {
            "or_require_vwap_alignment": 1,
            "or_min_vwap_dev_pct": 0.00015,
            "or_relvol_lb": 0.85,
        }),
        ("P56_Q03_VWAP_RVOL_TIGHT", {
            "or_require_vwap_alignment": 1,
            "or_min_vwap_dev_pct": 0.00020,
            "or_relvol_lb": 0.90,
        }),
        ("P56_Q04_RVOL_ONLY", {
            "or_relvol_lb": 0.85,
        }),
        ("P56_Q05_LIGHT_QUALITY", {
            "or_require_vwap_alignment": 1,
            "or_min_vwap_dev_pct": 0.00010,
            "or_relvol_lb": 0.75,
        }),
    ]


def save_partial(meta):
    OUT_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main():
    uid, tok = creds()
    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update({"trade_mnq": 1, "trade_mes": 1, "allow_shorts": 1})
    candidates = build_candidates()
    scenarios = [
        ("IS_2022_2024", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
    ]

    rows = []
    results = {}

    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        results[label] = {"overrides": ov, "scenarios": {}, "pass_all": False}
        for sname, dates in scenarios:
            params = dict(cfg)
            params.update(dates)
            set_params(uid, tok, params)
            rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            results[label]["scenarios"][sname] = rr
            save_partial({
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "compile_id": cid,
                "results": results,
                "rows": rows,
            })

    baseline = results["P56_BASE_REF"]["scenarios"]
    winners = []
    for label, payload in results.items():
        if label == "P56_BASE_REF":
            payload["pass_all"] = True
            continue
        checks = {}
        for sname, _ in scenarios:
            checks[f"nodeg_{sname}"] = strict_nodeg(baseline[sname], payload["scenarios"][sname])
        payload["checks"] = checks
        payload["pass_all"] = all(checks.values())
        if payload["pass_all"]:
            winners.append(label)

    lines = []
    lines.append(f"generated_at_utc={datetime.now(timezone.utc).isoformat()}")
    lines.append(f"compile_id={cid}")
    lines.append("baseline=P56_BASE_REF")
    lines.append("")
    lines.append("BASELINE:")
    for sname, _ in scenarios:
        b = baseline[sname]
        lines.append(
            f"{sname}: np={b.get('np_pct')} dd={b.get('dd_pct')} dbr={b.get('dbr')} tbr={b.get('tbr')} orders={b.get('orders')} tr_orb={b.get('tr_orb')} tr_stress={b.get('tr_stress')}"
        )
    lines.append("")
    lines.append("CANDIDATES:")
    for label, payload in results.items():
        if label == "P56_BASE_REF":
            continue
        lines.append(f"{label} pass_all={payload.get('pass_all')} checks={payload.get('checks')}")
        lines.append(f"  overrides={payload.get('overrides')}")
        for sname, _ in scenarios:
            r = payload["scenarios"][sname]
            lines.append(
                f"  {sname}: np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} orders={r.get('orders')} tr_orb={r.get('tr_orb')} tr_stress={r.get('tr_stress')}"
            )
    lines.append("")
    lines.append("WINNERS:")
    if winners:
        for w in winners:
            lines.append(w)
    else:
        lines.append("NONE")

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    save_partial({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "compile_id": cid,
        "results": results,
        "rows": rows,
        "winners": winners,
    })


if __name__ == "__main__":
    main()
