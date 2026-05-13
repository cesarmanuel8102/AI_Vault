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
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_main_snapshot_30047357.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_patch_regression_2026-04-21.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_patch_regression_2026-04-21.txt")
SOURCE_BACKTEST_ID = "be8a65a36c345e626c1a1dc7284df4e5"  # REC_E5_BASE OOS


def load_creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Credenciales QC invalidas")
    return uid, tok


def headers(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    basic = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {basic}", "Timestamp": str(ts), "Content-Type": "application/json"}


def api_post(uid, tok, endpoint, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
        data.setdefault("errors", [f"HTTP {r.status_code}"])
    if data.get("success", False):
        return data
    errs = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return data


def parse_float(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def get_rt(rt, key):
    if isinstance(rt, dict):
        return rt.get(key)
    if isinstance(rt, list):
        for item in rt:
            if isinstance(item, dict) and str(item.get("name") or item.get("Name")) == key:
                return item.get("value") or item.get("Value")
    return None


def upload_main(uid, tok):
    payload = {"projectId": PROJECT_ID, "name": "main.py", "content": MAIN_PATH.read_text(encoding="utf-8")}
    resp = api_post(uid, tok, "files/update", payload, timeout=180)
    if not resp.get("success", False):
        raise RuntimeError(f"files/update main.py failed: {resp}")


def compile_project(uid, tok):
    c = api_post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(180):
        r = api_post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile no exitoso: {st} | {r}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    resp = api_post(uid, tok, "projects/update", payload, timeout=60)
    if not resp.get("success", False):
        raise RuntimeError(f"projects/update failed: {resp}")


def fetch_source_params(uid, tok):
    rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": SOURCE_BACKTEST_ID}, timeout=60)
    bt = rd.get("backtest") or {}
    ps = bt.get("parameterSet") or {}
    if not isinstance(ps, dict) or not ps:
        raise RuntimeError(f"No parameterSet en backtest {SOURCE_BACKTEST_ID}")
    ps.pop("label", None)
    return ps


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
    bid = ((bt.get("backtest") or {}).get("backtestId"))
    if not bid:
        return {"status": "CreateFailed", "error": str(bt)}
    for _ in range(420):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        if "Completed" in st:
            s = b.get("statistics") or {}
            rt = b.get("runtimeStatistics") or {}
            return {
                "status": st,
                "backtest_id": bid,
                "np_pct": parse_float(s.get("Net Profit")),
                "dd_pct": parse_float(s.get("Drawdown")),
                "sharpe": parse_float(s.get("Sharpe Ratio")),
                "orders": parse_int(s.get("Total Orders")),
                "dbr": parse_int(get_rt(rt, "DailyLossBreaches")),
                "tbr": parse_int(get_rt(rt, "TrailingBreaches")),
                "stress_trades": parse_int(get_rt(rt, "StressTrades")),
                "normal_trades": parse_int(get_rt(rt, "NormalTrades")),
                "stress_days": parse_int(get_rt(rt, "ExternalStressDays")),
                "error": b.get("error") or b.get("message"),
            }
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def summarize(rows):
    lines = []
    byw = {r["window"]: r for r in rows}
    for k in ["LIVE_WEEK_2026_04_14_04_21", "CH_2026_Q1", "OOS_2025_2026Q1", "STRESS_2020"]:
        r = byw.get(k)
        if not r:
            continue
        lines.append(
            f"{k}: np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
            f"stress_days={r.get('stress_days')} stress_trades={r.get('stress_trades')} normal_trades={r.get('normal_trades')} id={r.get('backtest_id')}"
        )
    return lines


def main():
    uid, tok = load_creds()
    source_params = fetch_source_params(uid, tok)

    # Force the exact intended profile identity
    base = dict(source_params)
    base.update({
        "phase_mode": "T2_DUAL",
        "label": "REC_E5_BASE_PATCHED",
    })

    windows = [
        ("LIVE_WEEK_2026_04_14_04_21", {"start_year": "2026", "start_month": "4", "start_day": "14", "end_year": "2026", "end_month": "4", "end_day": "21"}),
        ("CH_2026_Q1", {"start_year": "2026", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"}),
        ("OOS_2025_2026Q1", {"start_year": "2025", "start_month": "1", "start_day": "1", "end_year": "2026", "end_month": "3", "end_day": "31"}),
        ("STRESS_2020", {"start_year": "2020", "start_month": "1", "start_day": "1", "end_year": "2020", "end_month": "12", "end_day": "31"}),
    ]

    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    rows = []
    for wname, wdates in windows:
        params = dict(base)
        params.update(wdates)
        set_params(uid, tok, params)
        bt_name = f"CB_PATCH_{wname}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        row = run_backtest(uid, tok, cid, bt_name)
        row["window"] = wname
        rows.append(row)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "source_backtest": SOURCE_BACKTEST_ID,
        "compile_id": cid,
        "base_params": base,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    OUT_TXT.write_text("\n".join(summarize(rows)) + "\n", encoding="utf-8")
    print(OUT_JSON)
    for line in summarize(rows):
        print(line)


if __name__ == "__main__":
    main()
