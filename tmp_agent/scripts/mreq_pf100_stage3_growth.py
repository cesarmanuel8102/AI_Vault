"""
PF100 Stage 3 growth optimization.

Focus: keep C6 robustness and increase return with a second entry only in normal regime.
"""

import json
import statistics
import time
from base64 import b64encode
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import requests


UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_stage3_growth_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_stage3_growth_results.txt")


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


def poll_backtest(backtest_id, timeout_sec=1800):
    elapsed = 0
    while elapsed < timeout_sec:
        data = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
        bt = data.get("backtest", {})
        status = str(bt.get("status", ""))
        if "Completed" in status:
            # QC can report "Completed" slightly before all stats fields are populated.
            time.sleep(2)
            data2 = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
            return True, data2.get("backtest", bt)
        if "Error" in status or "Runtime" in status:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def monthly_stats(bt):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    pstats = perf.get("portfolioStatistics", {}) or {}
    start_equity = parse_num(pstats.get("startEquity")) or 50000.0

    pnl_by_month = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        month_key = f"{dt.year:04d}-{dt.month:02d}"
        pnl_by_month[month_key] += float(pnl)

    if not pnl_by_month:
        return {
            "monthly_count": 0,
            "monthly_mean_pct": None,
            "monthly_median_pct": None,
            "monthly_p25_pct": None,
            "monthly_worst_pct": None,
            "monthly_positive_rate_pct": None,
        }

    eq = float(start_equity)
    returns = []
    for month in sorted(pnl_by_month.keys()):
        pnl = pnl_by_month[month]
        ret = 0.0 if eq <= 0 else (pnl / eq) * 100.0
        returns.append(ret)
        eq += pnl

    sret = sorted(returns)
    pos = sum(1 for r in returns if r > 0)
    return {
        "monthly_count": len(returns),
        "monthly_mean_pct": round(statistics.mean(returns), 3),
        "monthly_median_pct": round(statistics.median(returns), 3),
        "monthly_p25_pct": round(percentile(sret, 0.25), 3),
        "monthly_worst_pct": round(min(returns), 3),
        "monthly_positive_rate_pct": round(100.0 * pos / len(returns), 2),
    }


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    m = {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "external_stress_days": parse_int(rt.get("ExternalStressDays")),
        "pf100_stress_trades": parse_int(rt.get("PF100StressTrades")),
        "pf100_trades_total": parse_int(rt.get("PF100TradesTotal")),
    }
    m.update(monthly_stats(bt))
    return m


def base_cfg():
    return {
        "allow_shorts": 1,
        "trade_nq": 1,
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "entry_hour": 9,
        "entry_min": 40,
        "risk_per_trade": 0.010,
        "trailing_lock_mode": "EOD",
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_vixy_sma_period": 5,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
    }


def candidates():
    b = base_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c.update({"label": label})
        c.update(kw)
        rows.append(c)

    # Baseline C6 from stage 2.
    add(
        "PF100_D1_BASELINE_C6",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0100,
        max_contracts_per_trade=5,
    )
    # Conservative 2nd entry: strict momentum + lower risk.
    add(
        "PF100_D2_SECOND_CONS",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0100,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0048,
        second_stop_atr_mult=0.70,
        second_target_atr_mult=1.20,
        second_risk_mult=0.35,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    # Moderate 2nd entry: slightly higher participation.
    add(
        "PF100_D3_SECOND_MOD",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0100,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0042,
        second_stop_atr_mult=0.68,
        second_target_atr_mult=1.25,
        second_risk_mult=0.45,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    # Defensive 2nd entry: very selective.
    add(
        "PF100_D4_SECOND_SELECTIVE",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0100,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0053,
        second_stop_atr_mult=0.72,
        second_target_atr_mult=1.15,
        second_risk_mult=0.30,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    # Extra symbol test to increase throughput.
    add(
        "PF100_D5_SECOND_PLUS_M2K",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0100,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0046,
        second_stop_atr_mult=0.70,
        second_target_atr_mult=1.20,
        second_risk_mult=0.35,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
        trade_m2k=1,
    )
    add(
        "PF100_D6_SECOND_CORE_RISK_105",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0105,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0048,
        second_stop_atr_mult=0.70,
        second_target_atr_mult=1.20,
        second_risk_mult=0.35,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    add(
        "PF100_D7_SECOND_AGGR",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0110,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0025,
        second_stop_atr_mult=0.65,
        second_target_atr_mult=1.35,
        second_risk_mult=0.70,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    add(
        "PF100_D8_SECOND_AGGR_EARLY",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0110,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        second_entry_hour=11,
        second_entry_min=5,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=1,
        second_mom_entry_pct=0.0020,
        second_stop_atr_mult=0.65,
        second_target_atr_mult=1.40,
        second_risk_mult=0.85,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )
    add(
        "PF100_D9_SECOND_RECHECK_MR",
        pf1_risk=0.0085,
        pf1_stop=0.45,
        pf1_tgt=1.70,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        ext_vixy_ratio_threshold=1.03,
        risk_per_trade=0.0110,
        max_contracts_per_trade=5,
        second_entry_enabled=1,
        max_trades_per_symbol_day=2,
        second_entry_breakout_enabled=0,
    )
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
    pf100_trades = m.get("pf100_trades_total") or 0
    if npv is None:
        return False
    if dbr > 0 or tbr > 0:
        return False
    if pf100_trades < 2:
        return False
    return npv >= 0.0


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== ROWS ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"ext_days={r.get('external_stress_days')} "
            f"pf100_day={r.get('pf100_stress_trades')} pf100_tot={r.get('pf100_trades_total')} "
            f"m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} err={r.get('error')} id={r.get('backtest_id')}"
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
            f"dbr={stress.get('daily_loss_breaches')} tbr={stress.get('trailing_breaches')} "
            f"pf100_tot={stress.get('pf100_trades_total')}"
        )
        time.sleep(5)
        if not stress_survives(stress):
            continue

        full = run_scenario(compile_id, label, cfg, "FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31)
        rows.append(full)
        save(rows)
        print(
            f"{label} FULL np={full.get('net_profit_pct')} dd={full.get('drawdown_pct')} "
            f"m_mean={full.get('monthly_mean_pct')} m_med={full.get('monthly_median_pct')} "
            f"dbr={full.get('daily_loss_breaches')} tbr={full.get('trailing_breaches')}"
        )
        time.sleep(5)

        oos = run_scenario(compile_id, label, cfg, "OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31)
        rows.append(oos)
        save(rows)
        print(
            f"{label} OOS np={oos.get('net_profit_pct')} dd={oos.get('drawdown_pct')} "
            f"m_mean={oos.get('monthly_mean_pct')} m_med={oos.get('monthly_median_pct')} "
            f"dbr={oos.get('daily_loss_breaches')} tbr={oos.get('trailing_breaches')}"
        )
        time.sleep(5)


if __name__ == "__main__":
    main()
