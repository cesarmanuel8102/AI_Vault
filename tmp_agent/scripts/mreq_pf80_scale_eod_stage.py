"""
PF80 scaling search with EOD trailing mode.

Workflow:
1) STRESS first
2) FULL + OOS only for STRESS survivors
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

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf80_scale_eod_stage_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf80_scale_eod_stage_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=8, backoff_sec=3):
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(min(backoff_sec * (2 ** attempt), 45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} payload={payload} err={last_err}")


def parse_pct(s):
    try:
        return float(str(s).replace("%", "").replace(" ", "").replace(",", ""))
    except Exception:
        return None


def parse_int(s):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


def upload_source(path: Path):
    code = path.read_text(encoding="utf-8")
    resp = api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    return bool(resp.get("success")), resp


def compile_project():
    create = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = create.get("compileId", "")
    if not cid:
        return False, "", create
    for _ in range(120):
        read = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = read.get("state", "")
        if st in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return st == "BuildSuccess", cid, read
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    resp = api_post("projects/update", payload, timeout=60)
    return bool(resp.get("success")), resp


def create_backtest(compile_id, bt_name):
    data = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": bt_name},
        timeout=90,
    )
    bt = data.get("backtest", {})
    return bool(data.get("success")), bt.get("backtestId", ""), data


def poll_backtest(backtest_id, timeout_sec=1600):
    elapsed = 0
    while elapsed < timeout_sec:
        data = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
        bt = data.get("backtest", {})
        status = str(bt.get("status", ""))
        if "Completed" in status:
            return True, bt
        if "Error" in status or "Runtime" in status:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
    }


def base_cfg():
    return {
        "allow_shorts": 1,
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "regime_mode": "PF80",
        "profile_mode": "PAYOUT_AGGR",
        "entry_hour": 9,
        "entry_min": 40,
        "flatten_hour": 15,
        "flatten_min": 58,
        "max_open_positions": 4,
        "max_trades_per_symbol_day": 2,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.07,
        "trailing_dd_limit_pct": 0.035,
        "trailing_lock_mode": "EOD",
        "dynamic_risk_enabled": 0,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_vixy_sma_period": 5,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
        "ext_min_signals": 1,
        "second_entry_enabled": 0,
        "max_atr_pct": 0.02,
        "stress_overlay_enabled": 0,
    }


def candidates():
    b = base_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c.update({"label": label})
        c.update(kw)
        rows.append(c)

    add("PF80_EOD_A1", risk_per_trade=0.010, max_contracts_per_trade=5)
    add("PF80_EOD_A2", risk_per_trade=0.012, max_contracts_per_trade=6, ext_vixy_ratio_threshold=1.028)
    add("PF80_EOD_A3", risk_per_trade=0.015, max_contracts_per_trade=8, ext_vixy_ratio_threshold=1.026)
    add("PF80_EOD_A4", risk_per_trade=0.018, max_contracts_per_trade=10, ext_vixy_ratio_threshold=1.024)
    add("PF80_EOD_A5", risk_per_trade=0.022, max_contracts_per_trade=12, ext_vixy_ratio_threshold=1.022)
    add("PF80_EOD_A6", risk_per_trade=0.026, max_contracts_per_trade=14, ext_vixy_ratio_threshold=1.020)
    add("PF80_EOD_B1", risk_per_trade=0.018, max_contracts_per_trade=10, second_entry_enabled=1, second_entry_hour=11, second_entry_min=20, second_mom_entry_pct=0.0030, second_risk_mult=0.55, second_target_atr_mult=1.20)
    add("PF80_EOD_B2", risk_per_trade=0.022, max_contracts_per_trade=12, second_entry_enabled=1, second_entry_hour=11, second_entry_min=20, second_mom_entry_pct=0.0028, second_risk_mult=0.60, second_target_atr_mult=1.25)
    add("PF80_EOD_C1", risk_per_trade=0.018, max_contracts_per_trade=10, trade_m2k=1)
    add("PF80_EOD_C2", risk_per_trade=0.022, max_contracts_per_trade=12, trade_m2k=1, trade_mym=1)
    return rows


def run_scenario(compile_id, label, params, scenario_name, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update(
        {
            "start_year": sy,
            "start_month": sm,
            "start_day": sd,
            "end_year": ey,
            "end_month": em,
            "end_day": ed,
        }
    )
    ok, upd = set_parameters(p)
    if not ok:
        return {"candidate": label, "scenario": scenario_name, "error": f"set_parameters_failed: {upd}"}

    bt_name = f"{label}_{scenario_name}_{int(time.time())}"
    ok, bt_id, create = create_backtest(compile_id, bt_name)
    if not ok or not bt_id:
        return {"candidate": label, "scenario": scenario_name, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "scenario": scenario_name, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = extract_metrics(bt)
    m["candidate"] = label
    m["scenario"] = scenario_name
    return m


def stress_survives(m):
    if m.get("error"):
        return False
    npv = m.get("net_profit_pct")
    dbr = m.get("daily_loss_breaches") or 0
    tbr = m.get("trailing_breaches") or 0
    if npv is None:
        return False
    if dbr > 0 or tbr > 0:
        return False
    return npv >= -0.80


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== ROWS ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} err={r.get('error')} "
            f"id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    ok, up = upload_source(SOURCE_FILE)
    if not ok:
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    rows = []
    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}

        stress = run_scenario(compile_id, label, cfg, "STRESS_2020", 2020, 1, 1, 2020, 12, 31)
        rows.append(stress)
        save(rows)
        print(
            f"{label} STRESS np={stress.get('net_profit_pct')} dd={stress.get('drawdown_pct')} "
            f"dbr={stress.get('daily_loss_breaches')} tbr={stress.get('trailing_breaches')}"
        )
        time.sleep(5)
        if not stress_survives(stress):
            continue

        full = run_scenario(compile_id, label, cfg, "FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31)
        rows.append(full)
        save(rows)
        print(
            f"{label} FULL np={full.get('net_profit_pct')} dd={full.get('drawdown_pct')} "
            f"dbr={full.get('daily_loss_breaches')} tbr={full.get('trailing_breaches')}"
        )
        time.sleep(5)

        oos = run_scenario(compile_id, label, cfg, "OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31)
        rows.append(oos)
        save(rows)
        print(
            f"{label} OOS np={oos.get('net_profit_pct')} dd={oos.get('drawdown_pct')} "
            f"dbr={oos.get('daily_loss_breaches')} tbr={oos.get('trailing_breaches')}"
        )
        time.sleep(5)


if __name__ == "__main__":
    main()
