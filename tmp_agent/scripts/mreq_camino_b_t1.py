"""
Camino B - T1 runner (stress trend standalone)
"""

import json
import time
from base64 import b64encode
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_t1_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_t1_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=7):
    last = None
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(min(3 * (2 ** i), 30))
    raise RuntimeError(f"api_post failed endpoint={endpoint} err={last}")


def parse_pct(x):
    try:
        return float(str(x).replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def upload_source():
    code = SOURCE_FILE.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})


def compile_project():
    c = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        return False, "", c
    for _ in range(120):
        r = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return st == "BuildSuccess", cid, r
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_params(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    return api_post("projects/update", payload, timeout=60)


def create_backtest(compile_id, name):
    d = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
        timeout=90,
    )
    bt = d.get("backtest", {})
    return d.get("success"), bt.get("backtestId"), d


def poll_bt(backtest_id, timeout_sec=1800):
    elapsed = 0
    while elapsed < timeout_sec:
        d = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
        bt = d.get("backtest", {})
        st = str(bt.get("status", ""))
        if "Completed" in st:
            time.sleep(2)
            d2 = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
            return True, d2.get("backtest", bt)
        if "Error" in st or "Runtime" in st:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "stress_trades": parse_int(rt.get("StressTrades")),
        "normal_trades": parse_int(rt.get("NormalTrades")),
        "external_stress_days": parse_int(rt.get("ExternalStressDays")),
    }


def base():
    return {
        "phase_mode": "T1_TREND_ONLY",
        "allow_shorts": 1,
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "entry_hour": 9,
        "entry_min": 40,
        "flatten_hour": 15,
        "flatten_min": 58,
        "trailing_lock_mode": "EOD",
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 1,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.04,
        "trailing_dd_limit_pct": 0.035,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "normal_risk_per_trade": 0.009,
    }


def candidates():
    b = base()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    add("CB_T1_A", ext_vixy_ratio_threshold=1.03, stress_risk_per_trade=0.0040, stress_stop_atr_mult=0.80, stress_target_atr_mult=1.80, stress_breakout_buffer_pct=0.0007, stress_disable_shorts=0)
    add("CB_T1_B", ext_vixy_ratio_threshold=1.02, stress_risk_per_trade=0.0045, stress_stop_atr_mult=0.75, stress_target_atr_mult=1.90, stress_breakout_buffer_pct=0.0006, stress_disable_shorts=0)
    add("CB_T1_C_LONG", ext_vixy_ratio_threshold=1.03, stress_risk_per_trade=0.0040, stress_stop_atr_mult=0.75, stress_target_atr_mult=1.70, stress_breakout_buffer_pct=0.0005, stress_disable_shorts=1)
    add("CB_T1_D_DEF", ext_vixy_ratio_threshold=1.04, stress_risk_per_trade=0.0035, stress_stop_atr_mult=0.85, stress_target_atr_mult=1.70, stress_breakout_buffer_pct=0.0008, stress_disable_shorts=0)
    add("CB_T1_E_AGGR", ext_vixy_ratio_threshold=1.02, stress_risk_per_trade=0.0050, stress_stop_atr_mult=0.70, stress_target_atr_mult=2.00, stress_breakout_buffer_pct=0.0005, stress_disable_shorts=0)
    return rows


def run(compile_id, label, params):
    p = dict(params)
    p.update({
        "start_year": 2020,
        "start_month": 1,
        "start_day": 1,
        "end_year": 2020,
        "end_month": 12,
        "end_day": 31,
    })

    upd = set_params(p)
    if not upd.get("success"):
        return {"candidate": label, "error": f"set_params_failed: {upd}"}

    ok, bt_id, d = create_backtest(compile_id, f"{label}_STRESS2020_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "error": f"create_failed: {d}"}

    ok, bt = poll_bt(bt_id)
    if not ok:
        return {"candidate": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = metrics(bt)
    m["candidate"] = label
    return m


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== STRESS_2020 ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"stress_trades={r.get('stress_trades')} norm_trades={r.get('normal_trades')} "
            f"stress_days={r.get('external_stress_days')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    u = upload_source()
    if not u.get("success"):
        raise RuntimeError(f"upload_failed: {u}")

    ok, cid, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    rows = []
    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        r = run(cid, label, cfg)
        rows.append(r)
        save(rows)
        print(
            f"{label} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} stress_trades={r.get('stress_trades')}"
        )
        time.sleep(4)


if __name__ == "__main__":
    main()
