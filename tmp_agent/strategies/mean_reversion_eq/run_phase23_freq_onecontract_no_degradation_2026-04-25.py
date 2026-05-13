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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase23_freq_onecontract_no_degradation_2026-04-25.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase23_freq_onecontract_no_degradation_2026-04-25.txt")


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


def build_candidates():
    cands = [("P23_BASE_REF", {})]

    focused = [
        # Frequency candidates: relaxed ORB + one-contract cap
        ("P23_C01", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 1, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        ("P23_C02", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00030, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 1, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        ("P23_C03", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 0, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        ("P23_C04", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00030, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 0, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        ("P23_C05", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.190, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0008, "or_require_gap_alignment": 1, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        ("P23_C06", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.190, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0008, "or_require_gap_alignment": 0, "or_risk": 0.0090, "max_contracts_per_trade": 1}),
        # same triggers with slightly lower risk to test one-contract fill in both symbols
        ("P23_C07", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 1, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
        ("P23_C08", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00030, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 1, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
        ("P23_C09", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 0, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
        ("P23_C10", {"alpha_mr_enabled": 0, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00030, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 0, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
        # Micro MR sidecar with one-contract cap
        ("P23_C11", {"alpha_mr_enabled": 1, "n_risk": 0.0020, "or_min_width_atr": 0.185, "or_breakout_buffer_pct": 0.00030, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0006, "or_require_gap_alignment": 1, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
        ("P23_C12", {"alpha_mr_enabled": 1, "n_risk": 0.0015, "or_min_width_atr": 0.190, "or_breakout_buffer_pct": 0.00035, "or_min_gap_pct": 0.0010, "or_mom_entry_pct": 0.0008, "or_require_gap_alignment": 0, "or_risk": 0.0075, "max_contracts_per_trade": 1}),
    ]
    cands.extend(focused)
    return cands


def save_partial(meta):
    OUT_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def strict_nodeg(b, c):
    return (
        c.get("np_pct") is not None
        and b.get("np_pct") is not None
        and c.get("np_pct") >= b.get("np_pct")
        and c.get("dd_pct") is not None
        and b.get("dd_pct") is not None
        and c.get("dd_pct") <= b.get("dd_pct")
        and (c.get("dbr") or 0) <= (b.get("dbr") or 0)
        and (c.get("tbr") or 0) <= (b.get("tbr") or 0)
    )


def main():
    uid, tok = creds()
    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    base.update({"trade_mnq": 1, "trade_mes": 1, "allow_shorts": 1})
    candidates = build_candidates()

    week_scenarios = [
        ("LIVE_WEEK_0420_0424", {"start_year": 2026, "start_month": 4, "start_day": 20, "end_year": 2026, "end_month": 4, "end_day": 24}),
        ("LIVE_WEEK_0415_0421", {"start_year": 2026, "start_month": 4, "start_day": 15, "end_year": 2026, "end_month": 4, "end_day": 21}),
    ]
    core_scenarios = [
        ("IS_2022_2024", {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}),
        ("OOS_2025_2026Q1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
    ]

    rows = []
    stage1 = {}

    # Stage 1: live-like week frequency filter
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        stage1[label] = {"overrides": ov, "weeks": {}}
        for sname, dates in week_scenarios:
            p = dict(cfg)
            p.update(dates)
            set_params(uid, tok, p)
            rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            stage1[label]["weeks"][sname] = rr
            save_partial(
                {
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "compile_id": cid,
                    "stage": "stage1_weeks",
                    "stage1": stage1,
                    "rows": rows,
                }
            )

    base_w1 = (stage1["P23_BASE_REF"]["weeks"].get("LIVE_WEEK_0420_0424", {}).get("orders") or 0)
    base_w2 = (stage1["P23_BASE_REF"]["weeks"].get("LIVE_WEEK_0415_0421", {}).get("orders") or 0)

    shortlisted = []
    for label, _ in candidates:
        if label == "P23_BASE_REF":
            shortlisted.append(label)
            continue
        w1 = (stage1[label]["weeks"].get("LIVE_WEEK_0420_0424", {}).get("orders") or 0)
        w2 = (stage1[label]["weeks"].get("LIVE_WEEK_0415_0421", {}).get("orders") or 0)
        if (w1 > base_w1) or (w2 > base_w2):
            shortlisted.append(label)

    # Stage 2: strict no-degradation on IS/OOS/STRESS for shortlist
    by = {}
    for label in shortlisted:
        ov = stage1[label]["overrides"]
        cfg = dict(base)
        cfg.update(ov)
        by[label] = {}
        for sname, dates in core_scenarios:
            p = dict(cfg)
            p.update(dates)
            set_params(uid, tok, p)
            rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            by[label][sname] = rr
            save_partial(
                {
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "compile_id": cid,
                    "stage": "stage2_core",
                    "stage1": stage1,
                    "shortlisted": shortlisted,
                    "core": by,
                    "rows": rows,
                }
            )

    baseline = by.get("P23_BASE_REF", {})
    decision = {}
    for label in shortlisted:
        if label == "P23_BASE_REF":
            continue
        checks = {}
        ok = True
        for key in ("IS_2022_2024", "OOS_2025_2026Q1", "STRESS_2020"):
            cond = strict_nodeg(baseline.get(key, {}), by.get(label, {}).get(key, {}))
            checks[f"nodeg_{key}"] = cond
            ok = ok and cond
        w1 = (stage1[label]["weeks"].get("LIVE_WEEK_0420_0424", {}).get("orders") or 0)
        w2 = (stage1[label]["weeks"].get("LIVE_WEEK_0415_0421", {}).get("orders") or 0)
        freq = (w1 > base_w1) or (w2 > base_w2)
        checks["freq_improves_week"] = freq
        ok = ok and freq
        decision[label] = {
            "pass": ok,
            "checks": checks,
            "candidate_week_orders": {"0420_0424": w1, "0415_0421": w2},
            "baseline_week_orders": {"0420_0424": base_w1, "0415_0421": base_w2},
            "overrides": stage1[label]["overrides"],
        }

    final = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "compile_id": cid,
        "stage1_candidates_total": len(candidates),
        "shortlisted_count": len(shortlisted),
        "shortlisted": shortlisted,
        "stage1": stage1,
        "core": by,
        "decision": decision,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(final, indent=2), encoding="utf-8")

    lines = [
        f"generated_at_utc={final['generated_at_utc']}",
        f"compile_id={cid}",
        f"stage1_candidates_total={len(candidates)}",
        f"shortlisted_count={len(shortlisted)}",
        f"baseline_week_orders=({base_w1},{base_w2})",
        "",
        "SHORTLISTED:",
    ]
    for x in shortlisted:
        lines.append(x)
    lines.append("")
    lines.append("DECISION:")
    if not decision:
        lines.append("No week-frequency-improving candidates under current search.")
    for k, v in decision.items():
        lines.append(f"{k} pass={v['pass']} checks={v['checks']} week_orders={v['candidate_week_orders']}")
        lines.append(f"  overrides={v['overrides']}")

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
