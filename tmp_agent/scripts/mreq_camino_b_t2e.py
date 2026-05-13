"""
Camino B - T2 runner (dual regime)
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_t2e_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_t2e_results.txt")


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
    d = api_post("backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=90)
    bt = d.get("backtest", {})
    return d.get("success"), bt.get("backtestId"), d


def poll_bt(backtest_id, timeout_sec=2400):
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
        "max_vixy_ratio": parse_pct(rt.get("MaxVIXYRatio")),
    }


def base():
    return {
        "phase_mode": "T2_DUAL",
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
        "ext_vixy_ratio_threshold": 1.03,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
        "ext_min_signals": 1,
        "normal_risk_per_trade": 0.0050,
        "normal_gap_atr_mult": 0.22,
        "normal_stop_atr_mult": 0.60,
        "normal_gap_fill_fraction": 0.70,
        "normal_min_gap_pct": 0.0,
        "normal_max_gap_pct": 0.0055,
        "normal_max_atr_pct": 0.013,
        "normal_use_trend_filter": 0,
        "normal_max_contracts_per_trade": 5,
    }


def candidates():
    b = base()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    # Throughput sweep around robust C0/R65
    add(
        "CB_T2E_E1_M2TRADES",
        ext_vixy_ratio_threshold=1.03,
        normal_risk_per_trade=0.0055,
        stress_risk_per_trade=0.0048,
        stress_stop_atr_mult=0.70,
        stress_target_atr_mult=2.00,
        stress_breakout_buffer_pct=0.0005,
        stress_disable_shorts=0,
        max_trades_per_symbol_day=2,
    )
    add(
        "CB_T2E_E2_M2TRADES_M2K",
        ext_vixy_ratio_threshold=1.03,
        trade_m2k=1,
        normal_risk_per_trade=0.0065,
        stress_risk_per_trade=0.0048,
        stress_stop_atr_mult=0.70,
        stress_target_atr_mult=2.00,
        stress_breakout_buffer_pct=0.0005,
        stress_disable_shorts=0,
        max_trades_per_symbol_day=2,
    )
    add(
        "CB_T2E_E3_R65_M2TRADES",
        ext_vixy_ratio_threshold=1.03,
        normal_risk_per_trade=0.0065,
        stress_risk_per_trade=0.0048,
        stress_stop_atr_mult=0.70,
        stress_target_atr_mult=2.00,
        stress_breakout_buffer_pct=0.0005,
        stress_disable_shorts=0,
        max_trades_per_symbol_day=2,
    )
    add(
        "CB_T2E_E4_WIDER_GAP",
        ext_vixy_ratio_threshold=1.03,
        normal_risk_per_trade=0.0055,
        normal_max_gap_pct=0.0065,
        stress_risk_per_trade=0.0048,
        stress_stop_atr_mult=0.70,
        stress_target_atr_mult=2.00,
        stress_breakout_buffer_pct=0.0005,
        stress_disable_shorts=0,
        max_trades_per_symbol_day=2,
    )
    add(
        "CB_T2E_E5_R60_M2TRADES",
        ext_vixy_ratio_threshold=1.03,
        normal_risk_per_trade=0.0060,
        stress_risk_per_trade=0.0048,
        stress_stop_atr_mult=0.70,
        stress_target_atr_mult=2.00,
        stress_breakout_buffer_pct=0.0005,
        stress_disable_shorts=0,
        max_trades_per_symbol_day=2,
    )
    return rows


def run_scenario(compile_id, label, params, scenario_name, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})

    upd = set_params(p)
    if not upd.get("success"):
        return {"candidate": label, "scenario": scenario_name, "error": f"set_params_failed: {upd}"}

    ok, bt_id, d = create_backtest(compile_id, f"{label}_{scenario_name}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "scenario": scenario_name, "error": f"create_failed: {d}"}

    ok, bt = poll_bt(bt_id)
    if not ok:
        return {"candidate": label, "scenario": scenario_name, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = metrics(bt)
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
    return npv > 0.0


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== CAMINO B T2E ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"stress_days={r.get('external_stress_days')} max_vixy={r.get('max_vixy_ratio')} "
            f"stress_trades={r.get('stress_trades')} norm_trades={r.get('normal_trades')} err={r.get('error')} id={r.get('backtest_id')}"
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

        stress = run_scenario(cid, label, cfg, "STRESS_2020", 2020, 1, 1, 2020, 12, 31)
        rows.append(stress)
        save(rows)
        print(f"{label} STRESS np={stress.get('net_profit_pct')} dbr={stress.get('daily_loss_breaches')} tbr={stress.get('trailing_breaches')}")
        time.sleep(4)

        if not stress_survives(stress):
            continue

        full = run_scenario(cid, label, cfg, "FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31)
        rows.append(full)
        save(rows)
        print(f"{label} FULL np={full.get('net_profit_pct')} dd={full.get('drawdown_pct')}")
        time.sleep(4)

        oos = run_scenario(cid, label, cfg, "OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31)
        rows.append(oos)
        save(rows)
        print(f"{label} OOS np={oos.get('net_profit_pct')} dd={oos.get('drawdown_pct')}")
        time.sleep(4)


if __name__ == "__main__":
    main()
