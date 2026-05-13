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
MAIN_ORIGINAL = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
MAIN_DIAG = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_diagnostic_week.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf200_live_week_diagnostic_2026-04-25.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf200_live_week_diagnostic_2026-04-25.txt")


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
                raise RuntimeError(f"Compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, cid, name):
    bid = None
    for _ in range(45):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
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
    for _ in range(520):
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


def current_project_params(uid, tok):
    rd = post(uid, tok, "projects/read", {"projectId": PROJECT_ID}, timeout=60)
    projs = rd.get("projects") or []
    if not projs:
        return {}
    params = projs[0].get("parameters") or []
    out = {}
    for p in params:
        k = p.get("key")
        v = p.get("value")
        if k is not None:
            out[str(k)] = str(v) if v is not None else ""
    return out


def set_project_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    wr = post(uid, tok, "projects/update", payload, timeout=90)
    if not wr.get("success", False):
        raise RuntimeError(f"projects/update failed: {wr}")


def rt(runtime, key):
    if isinstance(runtime, dict):
        return runtime.get(key)
    if isinstance(runtime, list):
        for it in runtime:
            if isinstance(it, dict) and str(it.get("name") or it.get("Name")) == key:
                return it.get("value") or it.get("Value")
    return None


def summarize(bt):
    s = bt.get("statistics") or {}
    rts = bt.get("runtimeStatistics") or {}
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    return {
        "backtest_id": bt.get("backtestId"),
        "status": bt.get("status"),
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "total_orders": pi(s.get("Total Orders")),
        "closed_trades": len(trades),
        "external_stress_days": pi(rt(rts, "ExternalStressDays")),
        "alpha_tr_mr": pi(rt(rts, "TrMR")),
        "alpha_tr_orb": pi(rt(rts, "TrORB")),
        "alpha_tr_stress": pi(rt(rts, "TrST")),
        "diag_orb_calls": pi(rt(rts, "Diag_ORB_Calls")),
        "diag_orb_block_stress": pi(rt(rts, "Diag_ORB_BlockStress")),
        "diag_orb_break_fail": pi(rt(rts, "Diag_ORB_BreakFail")),
        "diag_orb_gapmin_fail": pi(rt(rts, "Diag_ORB_GapMinFail")),
        "diag_orb_mom_fail": pi(rt(rts, "Diag_ORB_MomFail")),
        "diag_orb_gapalign_fail": pi(rt(rts, "Diag_ORB_GapAlignFail")),
        "diag_orb_width_fail": pi(rt(rts, "Diag_ORB_WidthFail")),
        "diag_orb_signal_pass": pi(rt(rts, "Diag_ORB_SignalPass")),
        "diag_st_calls": pi(rt(rts, "Diag_ST_Calls")),
        "diag_st_no_stress": pi(rt(rts, "Diag_ST_NoStress")),
        "diag_st_gapmin_fail": pi(rt(rts, "Diag_ST_GapMinFail")),
        "diag_st_momtrend_fail": pi(rt(rts, "Diag_ST_MomTrendFail")),
        "diag_st_signal_pass": pi(rt(rts, "Diag_ST_SignalPass")),
        "diag_max_vixy_ratio": pf(rt(rts, "Diag_MaxVIXYRatio")),
        "diag_max_rv20": pf(rt(rts, "Diag_MaxRV20")),
        "diag_max_spy_gap_abs": pf(rt(rts, "Diag_MaxSpyGapAbs")),
        "diag_max_orb_gap_abs": pf(rt(rts, "Diag_MaxOrbGapAbs")),
        "diag_max_orb_mom_abs": pf(rt(rts, "Diag_MaxOrbMomAbs")),
        "diag_max_orb_width_atr": pf(rt(rts, "Diag_MaxOrbWidthATR")),
        "diag_max_orb_break_edge": pf(rt(rts, "Diag_MaxOrbBreakEdge")),
        "diag_max_st_gap_abs": pf(rt(rts, "Diag_MaxStGapAbs")),
        "diag_max_st_mom_abs": pf(rt(rts, "Diag_MaxStMomAbs")),
        "runtime": rts,
    }


def run_window(uid, tok, cid, original_params, y1, m1, d1, y2, m2, d2, label):
    p = dict(original_params)
    p.update(
        {
            "start_year": y1,
            "start_month": m1,
            "start_day": d1,
            "end_year": y2,
            "end_month": m2,
            "end_day": d2,
        }
    )
    set_project_params(uid, tok, p)
    bt = run_backtest(uid, tok, cid, f"PF200_DIAG_{label}_{int(time.time())}")
    sm = summarize(bt)
    sm["label"] = label
    sm["window"] = f"{y1:04d}-{m1:02d}-{d1:02d}..{y2:04d}-{m2:02d}-{d2:02d}"
    return sm


def main():
    uid, tok = creds()
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "source_diag": str(MAIN_DIAG),
        "windows": [],
        "steps": [],
    }

    original_params = current_project_params(uid, tok)

    try:
        upload_main(uid, tok, MAIN_DIAG)
        out["steps"].append({"step": "upload_diag_main", "ok": True})
        cid = compile_project(uid, tok)
        out["steps"].append({"step": "compile_diag", "compileId": cid})

        # Previous observed window (from prior report)
        out["windows"].append(run_window(uid, tok, cid, original_params, 2026, 4, 15, 2026, 4, 21, "W_PREV_0415_0421"))
        # Current full week
        out["windows"].append(run_window(uid, tok, cid, original_params, 2026, 4, 20, 2026, 4, 24, "W_CURR_0420_0424"))

    finally:
        # Restore original live source and full parameter set.
        upload_main(uid, tok, MAIN_ORIGINAL)
        set_project_params(uid, tok, original_params)
        out["steps"].append({"step": "restored_main_and_params", "ok": True, "params_count": len(original_params)})

    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"generated_at_utc={out['generated_at_utc']}",
        f"project_id={PROJECT_ID}",
        "",
    ]
    for w in out["windows"]:
        lines.append(f"[{w['label']}] window={w['window']} id={w.get('backtest_id')} status={w.get('status')}")
        lines.append(
            f"orders={w.get('total_orders')} trades={w.get('closed_trades')} np={w.get('np_pct')} dd={w.get('dd_pct')} "
            f"stress_days={w.get('external_stress_days')} tr_mr={w.get('alpha_tr_mr')} tr_orb={w.get('alpha_tr_orb')} tr_st={w.get('alpha_tr_stress')}"
        )
        lines.append(
            f"ORB calls={w.get('diag_orb_calls')} block_stress={w.get('diag_orb_block_stress')} break_fail={w.get('diag_orb_break_fail')} "
            f"gapmin_fail={w.get('diag_orb_gapmin_fail')} mom_fail={w.get('diag_orb_mom_fail')} gapalign_fail={w.get('diag_orb_gapalign_fail')} "
            f"width_fail={w.get('diag_orb_width_fail')} signal_pass={w.get('diag_orb_signal_pass')}"
        )
        lines.append(
            f"ST calls={w.get('diag_st_calls')} no_stress={w.get('diag_st_no_stress')} gapmin_fail={w.get('diag_st_gapmin_fail')} "
            f"momtrend_fail={w.get('diag_st_momtrend_fail')} signal_pass={w.get('diag_st_signal_pass')}"
        )
        lines.append(
            f"Max vixy_ratio={w.get('diag_max_vixy_ratio')} rv20={w.get('diag_max_rv20')} spy_gap_abs={w.get('diag_max_spy_gap_abs')} "
            f"orb_gap_abs={w.get('diag_max_orb_gap_abs')} orb_mom_abs={w.get('diag_max_orb_mom_abs')} "
            f"orb_width_atr={w.get('diag_max_orb_width_atr')} orb_break_edge={w.get('diag_max_orb_break_edge')} "
            f"st_gap_abs={w.get('diag_max_st_gap_abs')} st_mom_abs={w.get('diag_max_st_mom_abs')}"
        )
        lines.append("")

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
