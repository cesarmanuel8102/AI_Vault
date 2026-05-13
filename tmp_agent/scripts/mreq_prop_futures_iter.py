"""
Prop-firm readiness iteration for the micro futures strategy.

Runs candidate parameter sets across key scenarios:
- IS: 2022-2024
- OOS: 2025-2026Q1
- Stress: 2020

Then scores and ranks candidates with explicit penalties for:
- drawdown above comfort levels
- daily-loss or trailing-DD breaches
- poor consistency profile
"""
import json
import statistics
import time
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import Dict, List

import requests


UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/prop_futures_iter_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/prop_futures_iter_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=6, backoff_sec=3):
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            sleep_for = min(backoff_sec * (2 ** attempt), 60)
            time.sleep(sleep_for)
    raise RuntimeError(f"api_post_failed endpoint={endpoint} payload={payload} err={last_err}")


def parse_pct(s):
    try:
        return float(str(s).replace("%", "").replace(" ", "").replace(",", ""))
    except Exception:
        return None


def parse_num(s):
    try:
        return float(str(s).replace("$", "").replace("%", "").replace(",", "").strip())
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
    for _ in range(90):
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


def poll_backtest(backtest_id, timeout_sec=1200):
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


def read_backtest(backtest_id):
    data = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
    return data.get("backtest", {}) if isinstance(data, dict) else {}


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "sharpe": parse_num(s.get("Sharpe Ratio")),
        "win_rate_pct": parse_pct(s.get("Win Rate")),
        "total_orders": parse_int(s.get("Total Orders")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "best_day_usd": parse_num(rt.get("BestDayUSD")),
        "worst_day_usd": parse_num(rt.get("WorstDayUSD")),
        "consistency_pct": parse_num(rt.get("ConsistencyPct")),
        "runtime_dd_pct": parse_num(rt.get("DrawdownPct")),
    }


def candidates():
    base = {}

    rows = []
    baseline = dict(base)
    baseline.update({"label": "PF70_PF19_BASELINE_RERUN", "risk_per_trade": 0.0095, "stress_overlay_enabled": 0})
    rows.append(baseline)

    pf81_a = dict(base)
    pf81_a.update(
        {
            "label": "PF81_DUAL_ALPHA_A",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0030,
            "regime_atr_pct_threshold": 0.0115,
            "regime_gap_pct_threshold": 0.0100,
            "regime_rv_threshold": 0.0180,
            "regime_vix_level_threshold": 28.0,
            "regime_signal_count_required": 2,
            "stress_min_gap_entry_pct": 0.0080,
            "stress_max_gap_entry_pct": 0.0350,
            "stress_stop_atr_mult": 0.90,
            "stress_target_atr_mult": 1.40,
            "stress_max_hold_hours": 6,
            "stress_use_trend_filter": 1,
            "stress_confirm_intraday": 1,
            "stress_intraday_mom_pct": 0.0015,
            "stress_disable_shorts": 0,
        }
    )
    rows.append(pf81_a)

    pf81_b = dict(base)
    pf81_b.update(
        {
            "label": "PF81_DUAL_ALPHA_B",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0025,
            "regime_atr_pct_threshold": 0.0110,
            "regime_gap_pct_threshold": 0.0090,
            "regime_rv_threshold": 0.0160,
            "regime_vix_level_threshold": 26.0,
            "regime_signal_count_required": 2,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_max_gap_entry_pct": 0.0300,
            "stress_stop_atr_mult": 0.85,
            "stress_target_atr_mult": 1.30,
            "stress_max_hold_hours": 5,
            "stress_use_trend_filter": 1,
            "stress_confirm_intraday": 1,
            "stress_intraday_mom_pct": 0.0010,
            "stress_disable_shorts": 0,
        }
    )
    rows.append(pf81_b)

    pf81_c = dict(base)
    pf81_c.update(
        {
            "label": "PF81_DUAL_ALPHA_C_LONG_BIAS",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0025,
            "regime_atr_pct_threshold": 0.0110,
            "regime_gap_pct_threshold": 0.0090,
            "regime_rv_threshold": 0.0160,
            "regime_vix_level_threshold": 26.0,
            "regime_signal_count_required": 2,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_max_gap_entry_pct": 0.0300,
            "stress_stop_atr_mult": 0.85,
            "stress_target_atr_mult": 1.25,
            "stress_max_hold_hours": 5,
            "stress_use_trend_filter": 1,
            "stress_confirm_intraday": 1,
            "stress_intraday_mom_pct": 0.0010,
            "stress_disable_shorts": 1,
        }
    )
    rows.append(pf81_c)

    pf81v2_a = dict(base)
    pf81v2_a.update(
        {
            "label": "PF81V2_VIX32_SKIP",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0020,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 32.0,
            "regime_vix_above_sma_required": 1,
            "stress_skip_entries": 1,
        }
    )
    rows.append(pf81v2_a)

    pf81v2_b = dict(base)
    pf81v2_b.update(
        {
            "label": "PF81V2_VIX30_SKIP",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0020,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 30.0,
            "regime_vix_above_sma_required": 1,
            "stress_skip_entries": 1,
        }
    )
    rows.append(pf81v2_b)

    pf81v2_c = dict(base)
    pf81v2_c.update(
        {
            "label": "PF81V2_VIX28_SKIP",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0020,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 28.0,
            "regime_vix_above_sma_required": 1,
            "stress_skip_entries": 1,
        }
    )
    rows.append(pf81v2_c)

    pf81v2_d = dict(base)
    pf81v2_d.update(
        {
            "label": "PF81V2_VIX26_SKIP",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0020,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 26.0,
            "regime_vix_above_sma_required": 1,
            "stress_skip_entries": 1,
        }
    )
    rows.append(pf81v2_d)

    pf81v2_e = dict(base)
    pf81v2_e.update(
        {
            "label": "PF81V2_VIX30_SKIP_NO_SMA",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0020,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 30.0,
            "regime_vix_above_sma_required": 0,
            "stress_skip_entries": 1,
        }
    )
    rows.append(pf81v2_e)

    pf81v2_f = dict(base)
    pf81v2_f.update(
        {
            "label": "PF81V2_VIX30_TREND_LOW_RISK",
            "regime_mode": "PF81",
            "normal_risk_per_trade": 0.0095,
            "stress_risk_per_trade": 0.0015,
            "regime_use_vix_only": 1,
            "regime_vix_level_threshold": 30.0,
            "regime_vix_above_sma_required": 1,
            "stress_skip_entries": 0,
            "stress_min_gap_entry_pct": 0.0100,
            "stress_max_gap_entry_pct": 0.0300,
            "stress_stop_atr_mult": 1.00,
            "stress_target_atr_mult": 1.60,
            "stress_max_hold_hours": 4,
            "stress_use_trend_filter": 1,
            "stress_confirm_intraday": 1,
            "stress_intraday_mom_pct": 0.0020,
            "stress_disable_shorts": 0,
        }
    )
    rows.append(pf81v2_f)

    c_pf80a = dict(base)
    c_pf80a.update(
        {
            "label": "PF80_EXT_GATE_A",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.26,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.80,
            "ext_gap_abs_threshold": 0.0090,
        }
    )
    rows.append(c_pf80a)

    c_pf80b = dict(base)
    c_pf80b.update(
        {
            "label": "PF80_EXT_GATE_B",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.24,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.60,
            "ext_gap_abs_threshold": 0.0085,
        }
    )
    rows.append(c_pf80b)

    c_pf80c = dict(base)
    c_pf80c.update(
        {
            "label": "PF80_EXT_GATE_C",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.30,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 2.00,
            "ext_gap_abs_threshold": 0.0100,
        }
    )
    rows.append(c_pf80c)

    c_pf80d = dict(base)
    c_pf80d.update(
        {
            "label": "PF80_EXT_GATE_D",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.20,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.40,
            "ext_gap_abs_threshold": 0.0060,
        }
    )
    rows.append(c_pf80d)

    c_pf80e = dict(base)
    c_pf80e.update(
        {
            "label": "PF80_EXT_GATE_E",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.18,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.20,
            "ext_gap_abs_threshold": 0.0050,
        }
    )
    rows.append(c_pf80e)

    c_pf80f = dict(base)
    c_pf80f.update(
        {
            "label": "PF80_EXT_GATE_F",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_rv_lookback": 40,
            "ext_rv_threshold": 0.22,
            "ext_gap_lookback": 90,
            "ext_gap_z_threshold": 1.35,
            "ext_gap_abs_threshold": 0.0065,
        }
    )
    rows.append(c_pf80f)

    c_pf80v1 = dict(base)
    c_pf80v1.update(
        {
            "label": "PF80_VIX_GATE_A",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 1,
            "ext_vix_threshold": 25.0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.24,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.60,
            "ext_gap_abs_threshold": 0.0085,
        }
    )
    rows.append(c_pf80v1)

    c_pf80v2 = dict(base)
    c_pf80v2.update(
        {
            "label": "PF80_VIX_GATE_B",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 1,
            "ext_vix_threshold": 23.0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.22,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.50,
            "ext_gap_abs_threshold": 0.0080,
        }
    )
    rows.append(c_pf80v2)

    c_pf80v3 = dict(base)
    c_pf80v3.update(
        {
            "label": "PF80_VIX_GATE_C",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 1,
            "ext_vix_threshold": 20.0,
            "ext_rv_lookback": 20,
            "ext_rv_threshold": 0.20,
            "ext_gap_lookback": 60,
            "ext_gap_z_threshold": 1.40,
            "ext_gap_abs_threshold": 0.0070,
        }
    )
    rows.append(c_pf80v3)

    pf90_a = dict(base)
    pf90_a.update(
        {
            "label": "PF90_VIXY112_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.12,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_a)

    pf90_b = dict(base)
    pf90_b.update(
        {
            "label": "PF90_VIXY110_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.10,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_b)

    pf90_c = dict(base)
    pf90_c.update(
        {
            "label": "PF90_VIXY108_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.08,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_c)

    pf90_d = dict(base)
    pf90_d.update(
        {
            "label": "PF90_VIXY106_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.06,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_d)

    pf90_e = dict(base)
    pf90_e.update(
        {
            "label": "PF90_VIXY104_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.04,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_e)

    pf90_f = dict(base)
    pf90_f.update(
        {
            "label": "PF90_VIXY102_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.02,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_f)

    pf90_g = dict(base)
    pf90_g.update(
        {
            "label": "PF90_VIXY100_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.00,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_g)

    pf90_h = dict(base)
    pf90_h.update(
        {
            "label": "PF90_VIXY098_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 0.98,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_h)

    pf90_i = dict(base)
    pf90_i.update(
        {
            "label": "PF90_VIXY096_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 0.96,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_i)

    pf90_j = dict(base)
    pf90_j.update(
        {
            "label": "PF90_VIXY094_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 0.94,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_j)

    pf90_k = dict(base)
    pf90_k.update(
        {
            "label": "PF90_VIXY092_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 0.92,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_k)

    pf90_l = dict(base)
    pf90_l.update(
        {
            "label": "PF90_VIXY090_ONLY",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 0.90,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_l)

    pf90_m = dict(base)
    pf90_m.update(
        {
            "label": "PF90_VIXY102_R85",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0085,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.02,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_m)

    pf90_n = dict(base)
    pf90_n.update(
        {
            "label": "PF90_VIXY102_R80",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0080,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.02,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_n)

    pf90_o = dict(base)
    pf90_o.update(
        {
            "label": "PF90_VIXY102_R75",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0075,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.02,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_o)

    pf90_p = dict(base)
    pf90_p.update(
        {
            "label": "PF90_VIXY103_R85",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0085,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.03,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_p)

    pf90_q = dict(base)
    pf90_q.update(
        {
            "label": "PF90_VIXY101_R85",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0085,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.01,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_q)

    pf90_r = dict(base)
    pf90_r.update(
        {
            "label": "PF90_VIXY100_R85",
            "regime_mode": "PF80",
            "risk_per_trade": 0.0085,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.00,
            "ext_vixy_sma_period": 20,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_r)

    micro_thresholds = [1.015, 1.020, 1.025, 1.030]
    micro_risks = [0.0080, 0.00825, 0.0085]
    micro_smas = [15, 20, 25]
    for th in micro_thresholds:
        for rk in micro_risks:
            for sm in micro_smas:
                cand = dict(base)
                cand.update(
                    {
                        "label": f"PF90_MICRO_T{int(round(th * 1000)):04d}_R{int(round(rk * 100000)):04d}_S{sm}",
                        "regime_mode": "PF80",
                        "risk_per_trade": rk,
                        "stress_overlay_enabled": 0,
                        "ext_use_vix": 0,
                        "ext_use_vixy": 1,
                        "ext_vixy_ratio_threshold": th,
                        "ext_vixy_sma_period": sm,
                        "ext_rv_threshold": 1.0,
                        "ext_gap_z_threshold": 99.0,
                        "ext_gap_abs_threshold": 1.0,
                    }
                )
                rows.append(cand)

    pf90_final_sma5 = dict(base)
    pf90_final_sma5.update(
        {
            "label": "PF90_FINAL_SMA5_PRICE_GUARD",
            "regime_mode": "PF80",
            "risk_per_trade": 0.00825,
            "stress_overlay_enabled": 0,
            "ext_use_vix": 0,
            "ext_use_vixy": 1,
            "ext_vixy_ratio_threshold": 1.03,
            "ext_vixy_sma_period": 5,
            "ext_rv_threshold": 1.0,
            "ext_gap_z_threshold": 99.0,
            "ext_gap_abs_threshold": 1.0,
        }
    )
    rows.append(pf90_final_sma5)

    c_pf70 = dict(base)
    c_pf70.update(
        {
            "label": "PF70_NO_TRADE_STRESS",
            "regime_mode": "PF70",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 1,
            "stress_skip_entries": 1,
            "stress_atr_pct": 0.0115,
            "stress_gap_pct": 0.0100,
            "stress_trend_dev_pct": 0.060,
        }
    )
    rows.append(c_pf70)

    c_pf71 = dict(base)
    c_pf71.update(
        {
            "label": "PF71_DUAL_REGIME",
            "regime_mode": "PF71",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 1,
            "stress_skip_entries": 0,
            "stress_use_trend_mode": 1,
            "stress_atr_pct": 0.0115,
            "stress_gap_pct": 0.0100,
            "stress_trend_dev_pct": 0.060,
            "stress_min_gap_entry_pct": 0.0080,
            "stress_max_gap_entry_pct": 0.0300,
            "stress_stop_atr_mult": 0.85,
            "stress_target_atr_mult": 1.25,
            "stress_risk_mult": 0.20,
            "stress_max_hold_hours": 6,
        }
    )
    rows.append(c_pf71)

    c_pf70b = dict(base)
    c_pf70b.update(
        {
            "label": "PF70B_NO_TRADE_BAL",
            "regime_mode": "PF70",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 1,
            "stress_skip_entries": 1,
            "stress_atr_pct": 0.0120,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.080,
        }
    )
    rows.append(c_pf70b)

    c_pf71b = dict(base)
    c_pf71b.update(
        {
            "label": "PF71B_DUAL_REGIME_BAL",
            "regime_mode": "PF71",
            "risk_per_trade": 0.0095,
            "stress_overlay_enabled": 1,
            "stress_skip_entries": 0,
            "stress_use_trend_mode": 1,
            "stress_atr_pct": 0.0115,
            "stress_gap_pct": 0.0100,
            "stress_trend_dev_pct": 0.300,
            "stress_min_gap_entry_pct": 0.0080,
            "stress_max_gap_entry_pct": 0.0300,
            "stress_stop_atr_mult": 0.85,
            "stress_target_atr_mult": 1.25,
            "stress_risk_mult": 0.20,
            "stress_max_hold_hours": 6,
        }
    )
    rows.append(c_pf71b)

    c1 = dict(base)
    c1.update(
        {
            "label": "PF71_STRESS_XTREME_A",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0125,
            "stress_gap_pct": 0.0120,
            "stress_trend_dev_pct": 0.10,
            "stress_min_gap_entry_pct": 0.0100,
            "stress_target_atr_mult": 1.35,
            "stress_risk_mult": 0.30,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c1)

    c2 = dict(base)
    c2.update(
        {
            "label": "PF72_STRESS_XTREME_B",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0125,
            "stress_gap_pct": 0.0125,
            "stress_trend_dev_pct": 0.10,
            "stress_min_gap_entry_pct": 0.0105,
            "stress_target_atr_mult": 1.50,
            "stress_risk_mult": 0.40,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c2)

    c2_confirm = dict(base)
    c2_confirm.update(
        {
            "label": "PF72_STRESS_XTREME_B_CONFIRM_20260411",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0125,
            "stress_gap_pct": 0.0125,
            "stress_trend_dev_pct": 0.10,
            "stress_min_gap_entry_pct": 0.0105,
            "stress_target_atr_mult": 1.50,
            "stress_risk_mult": 0.40,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c2_confirm)

    c3 = dict(base)
    c3.update(
        {
            "label": "PF73_STRESS_XTREME_LONGONLY",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0120,
            "stress_gap_pct": 0.0115,
            "stress_trend_dev_pct": 0.09,
            "stress_min_gap_entry_pct": 0.0090,
            "stress_target_atr_mult": 1.35,
            "stress_risk_mult": 0.35,
            "stress_disable_shorts": 1,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c3)

    c4 = dict(base)
    c4.update(
        {
            "label": "PF74_STRESS_ULTRA_RARE",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0130,
            "stress_gap_pct": 0.0135,
            "stress_trend_dev_pct": 0.12,
            "stress_min_gap_entry_pct": 0.0115,
            "stress_target_atr_mult": 1.60,
            "stress_risk_mult": 0.45,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c4)

    c5 = dict(base)
    c5.update(
        {
            "label": "PF75_STRESS_KILLSWITCH",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0115,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.085,
            "stress_min_gap_entry_pct": 0.0090,
            "stress_target_atr_mult": 1.40,
            "stress_skip_entries": 1,
            "stress_risk_mult": 0.25,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c5)

    c6 = dict(base)
    c6.update(
        {
            "label": "PF76_STRESS_ACTIVE_A",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0125,
            "stress_gap_pct": 0.0120,
            "stress_trend_dev_pct": 0.10,
            "stress_min_gap_entry_pct": 0.0085,
            "stress_target_atr_mult": 1.55,
            "stress_risk_mult": 0.35,
            "stress_disable_shorts": 1,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c6)

    c7 = dict(base)
    c7.update(
        {
            "label": "PF77_STRESS_ACTIVE_B",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0120,
            "stress_gap_pct": 0.0115,
            "stress_trend_dev_pct": 0.09,
            "stress_min_gap_entry_pct": 0.0080,
            "stress_target_atr_mult": 1.50,
            "stress_risk_mult": 0.30,
            "stress_disable_shorts": 1,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c7)

    c8 = dict(base)
    c8.update(
        {
            "label": "PF78_STRESS_ACTIVE_C",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0118,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.085,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_target_atr_mult": 1.45,
            "stress_risk_mult": 0.28,
            "stress_disable_shorts": 1,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c8)

    c9 = dict(base)
    c9.update(
        {
            "label": "PF79_STRESS_ACTIVE_D",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0118,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.085,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_target_atr_mult": 1.45,
            "stress_risk_mult": 0.28,
            "stress_disable_shorts": 0,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c9)

    c10 = dict(base)
    c10.update(
        {
            "label": "PF80_STRESS_ACTIVE_E",
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0128,
            "stress_gap_pct": 0.0125,
            "stress_trend_dev_pct": 0.11,
            "stress_min_gap_entry_pct": 0.0088,
            "stress_target_atr_mult": 1.65,
            "stress_risk_mult": 0.40,
            "stress_disable_shorts": 1,
            "stress_max_hold_hours": 12,
        }
    )
    rows.append(c10)

    c11 = dict(base)
    c11.update(
        {
            "label": "PF81_BASE_R93",
            "risk_per_trade": 0.0093,
            "stress_overlay_enabled": 0,
        }
    )
    rows.append(c11)

    c12 = dict(base)
    c12.update(
        {
            "label": "PF82_BASE_R90",
            "risk_per_trade": 0.0090,
            "stress_overlay_enabled": 0,
        }
    )
    rows.append(c12)

    c13 = dict(base)
    c13.update(
        {
            "label": "PF83_STRESS_R93",
            "risk_per_trade": 0.0093,
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0118,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.085,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_target_atr_mult": 1.45,
            "stress_risk_mult": 0.28,
            "stress_disable_shorts": 0,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c13)

    c14 = dict(base)
    c14.update(
        {
            "label": "PF84_STRESS_R90",
            "risk_per_trade": 0.0090,
            "stress_overlay_enabled": 1,
            "stress_atr_pct": 0.0118,
            "stress_gap_pct": 0.0110,
            "stress_trend_dev_pct": 0.085,
            "stress_min_gap_entry_pct": 0.0075,
            "stress_target_atr_mult": 1.45,
            "stress_risk_mult": 0.28,
            "stress_disable_shorts": 0,
            "stress_max_hold_hours": 10,
        }
    )
    rows.append(c14)

    return rows


def scenarios():
    # label, start_y,m,d, end_y,m,d, target profit %
    return [
        ("IS_2022_2024", 2022, 1, 1, 2024, 12, 31, 6.0),
        ("OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31, 6.0),
        ("STRESS_2020", 2020, 1, 1, 2020, 12, 31, 0.0),
    ]


def score_row(r):
    npv = r.get("net_profit_pct")
    dd = r.get("drawdown_pct")
    sh = r.get("sharpe")
    cons = r.get("consistency_pct")
    dbr = r.get("daily_loss_breaches") or 0
    tbr = r.get("trailing_breaches") or 0

    if npv is None or dd is None:
        return -9999.0

    score = npv - (1.8 * dd)
    if sh is not None:
        score += 0.6 * sh
    if cons is not None and cons < 900 and cons > 40:
        score -= 0.2 * (cons - 40)
    score -= 25.0 * dbr
    score -= 35.0 * tbr
    return round(score, 3)


def pass_holgado(r):
    npv = r.get("net_profit_pct")
    dd = r.get("drawdown_pct")
    cons = r.get("consistency_pct")
    dbr = r.get("daily_loss_breaches") or 0
    tbr = r.get("trailing_breaches") or 0
    target_np = r.get("target_np_pct", 0.0)

    if npv is None or dd is None:
        return False
    if dbr > 0 or tbr > 0:
        return False
    if dd > 4.0:
        return False
    if npv < target_np:
        return False
    if cons is not None and cons < 900 and cons > 50:
        return False
    return True


def summarize(rows):
    by_candidate: Dict[str, List[Dict]] = {}
    for r in rows:
        by_candidate.setdefault(r["candidate"], []).append(r)

    summary = []
    for cand, group in by_candidate.items():
        scores = [g.get("score") for g in group if g.get("score") is not None]
        nps = [g.get("net_profit_pct") for g in group if g.get("net_profit_pct") is not None]
        dds = [g.get("drawdown_pct") for g in group if g.get("drawdown_pct") is not None]
        pass_count = sum(1 for g in group if g.get("pass_holgado"))
        summary.append(
            {
                "candidate": cand,
                "scenarios": len(group),
                "pass_holgado_count": pass_count,
                "pass_holgado_rate_pct": round(100 * pass_count / len(group), 2) if group else 0.0,
                "avg_score": round(statistics.mean(scores), 3) if scores else None,
                "avg_net_profit_pct": round(statistics.mean(nps), 3) if nps else None,
                "min_net_profit_pct": round(min(nps), 3) if nps else None,
                "avg_drawdown_pct": round(statistics.mean(dds), 3) if dds else None,
                "worst_drawdown_pct": round(max(dds), 3) if dds else None,
            }
        )
    summary.sort(key=lambda x: (x["pass_holgado_count"], x["avg_score"] if x["avg_score"] is not None else -999), reverse=True)
    return summary


def save_output(rows, summary):
    payload = {
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rows": rows,
        "summary": summary,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"updated_utc={payload['updated_utc']}", ""]
    lines.append("=== SUMMARY ===")
    for s in summary:
        lines.append(
            f"{s['candidate']} pass={s['pass_holgado_count']}/{s['scenarios']} "
            f"({s['pass_holgado_rate_pct']}%) avg_score={s['avg_score']} "
            f"avg_np={s['avg_net_profit_pct']} worst_dd={s['worst_drawdown_pct']}"
        )
    lines.append("")
    lines.append("=== DETAIL ===")
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} score={r.get('score')} pass={r.get('pass_holgado')} "
            f"np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"daily_breach={r.get('daily_loss_breaches')} trailing_breach={r.get('trailing_breaches')} "
            f"cons={r.get('consistency_pct')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def load_existing():
    if not OUT_JSON.exists():
        return []
    try:
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        return data.get("rows", []) if isinstance(data, dict) else []
    except Exception:
        return []


def main():
    ok, up = upload_source(SOURCE_FILE)
    if not ok:
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    common = {
        "max_open_positions": 3,
        "max_contracts_per_trade": 3,
        "daily_profit_lock_pct": 0.015,
        "entry_hour": 9,
        "entry_min": 40,
    }

    rows = load_existing()
    done = {(r.get("candidate"), r.get("scenario")) for r in rows if r.get("backtest_id")}

    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        for sc, sy, sm, sd, ey, em, ed, target_np in scenarios():
            if (label, sc) in done:
                continue

            params = dict(common)
            params.update(cfg)
            params.update(
                {
                    "start_year": sy,
                    "start_month": sm,
                    "start_day": sd,
                    "end_year": ey,
                    "end_month": em,
                    "end_day": ed,
                }
            )
            ok, upd = set_parameters(params)
            if not ok:
                row = {"candidate": label, "scenario": sc, "error": f"set_parameters_failed: {upd}"}
                rows.append(row)
                save_output(rows, summarize(rows))
                time.sleep(6)
                continue

            bt_name = f"{label}_{sc}_{int(time.time())}"
            ok, bt_id, create = create_backtest(compile_id, bt_name)
            if not ok or not bt_id:
                row = {"candidate": label, "scenario": sc, "error": f"create_backtest_failed: {create}"}
                rows.append(row)
                save_output(rows, summarize(rows))
                time.sleep(6)
                continue

            ok, bt = poll_backtest(bt_id)
            if not ok:
                row = {"candidate": label, "scenario": sc, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}
                rows.append(row)
                save_output(rows, summarize(rows))
                time.sleep(6)
                continue

            m = extract_metrics(bt)
            if m.get("net_profit_pct") is None or m.get("drawdown_pct") is None:
                time.sleep(6)
                bt2 = read_backtest(bt_id)
                if bt2:
                    m = extract_metrics(bt2)
            m["candidate"] = label
            m["scenario"] = sc
            m["target_np_pct"] = target_np
            m["score"] = score_row(m)
            m["pass_holgado"] = pass_holgado(m)
            rows.append(m)
            save_output(rows, summarize(rows))
            print(
                f"{label} {sc} np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} "
                f"cons={m.get('consistency_pct')} dbr={m.get('daily_loss_breaches')} "
                f"tbr={m.get('trailing_breaches')} pass={m.get('pass_holgado')} id={m.get('backtest_id')}"
            )
            time.sleep(8)

    summary = summarize(rows)
    save_output(rows, summary)
    print("\n=== RANKING ===")
    for s in summary:
        print(
            f"{s['candidate']} pass={s['pass_holgado_count']}/{s['scenarios']} "
            f"avg_score={s['avg_score']} avg_np={s['avg_net_profit_pct']} worst_dd={s['worst_drawdown_pct']}"
        )


if __name__ == "__main__":
    main()
