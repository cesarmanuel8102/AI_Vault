"""
PF100 D7 risk x vixy microgrid:
- Mantiene core D7
- Barre riesgo y umbral vixy cercano
- Evalua STRESS/FULL/OOS
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_risk_vixy_microgrid_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_risk_vixy_microgrid_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=8, backoff=3):
    last = None
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(min(backoff * (2 ** i), 45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} err={last}")


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


def upload_source(path):
    code = path.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)


def compile_project():
    c = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId", "")
    if not cid:
        return False, "", c
    for _ in range(120):
        r = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return st == "BuildSuccess", cid, r
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    return api_post("projects/update", payload, timeout=60)


def create_backtest(compile_id, name):
    d = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
        timeout=90,
    )
    bt = d.get("backtest", {})
    return bool(d.get("success")), bt.get("backtestId", ""), d


def poll_backtest(backtest_id, timeout_sec=2400):
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


def monthly_stats(bt):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    pstats = perf.get("portfolioStatistics", {}) or {}
    start_equity = parse_num(pstats.get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        key = f"{dt.year:04d}-{dt.month:02d}"
        by_month[key] += float(pnl)

    if not by_month:
        return {"monthly_mean_pct": None, "monthly_median_pct": None, "monthly_count": 0}

    eq = float(start_equity)
    rets = []
    for m in sorted(by_month.keys()):
        pnl = by_month[m]
        rets.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl

    return {
        "monthly_mean_pct": round(statistics.mean(rets), 3),
        "monthly_median_pct": round(statistics.median(rets), 3),
        "monthly_count": len(rets),
    }


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    perf = bt.get("totalPerformance", {}) or {}
    closed = perf.get("closedTrades", []) or []

    m = {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "pf100_stress_trades": parse_int(rt.get("PF100StressTrades")),
        "pf100_trades_total": parse_int(rt.get("PF100TradesTotal")),
        "pf100_second_entries": parse_int(rt.get("PF100SecondEntries")),
        "pf100_second_blocked": parse_int(rt.get("PF100SecondBlocked")),
        "pf100_partial_fills": parse_int(rt.get("PF100PartialFills")),
        "pf100_trail_updates": parse_int(rt.get("PF100TrailUpdates")),
        "pf100_quality_blocked": parse_int(rt.get("PF100QualityBlocked")),
        "closed_trades": len(closed),
    }
    m.update(monthly_stats(bt))
    return m


def baseline_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "allow_shorts": 1,
        "trade_nq": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "risk_per_trade": 0.0100,
        "daily_profit_lock_pct": 0.04,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
    }


def candidates():
    b = baseline_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    common = dict(
        max_contracts_per_trade=5,
        pf1_risk=0.0085,
        pf1_rng=0.0055,
        pf1_buf=0.0005,
        pf1_gap_fb=1,
        pf1_gap_thr=0.0030,
        pf1_tpd=1,
        pf1_mom_on=1,
        pf1_mom=0.0006,
        pf1_no_shorts=1,
        pf1_maxc=1,
        second_entry_enabled=1,
        second_entry_breakout_enabled=1,
        second_stop_atr_mult=0.65,
        second_target_atr_mult=1.35,
        second_max_hold_hours=3,
        second_use_trend_filter=1,
    )

    add("PF100_MICRO_R1150_V1030", **common, max_trades_per_symbol_day=2, risk_per_trade=0.0115, ext_vixy_ratio_threshold=1.03, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)
    add("PF100_MICRO_R1150_V1025", **common, max_trades_per_symbol_day=2, risk_per_trade=0.0115, ext_vixy_ratio_threshold=1.025, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)
    add("PF100_MICRO_R1150_V1035", **common, max_trades_per_symbol_day=2, risk_per_trade=0.0115, ext_vixy_ratio_threshold=1.035, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)
    add("PF100_MICRO_R1175_V1030", **common, max_trades_per_symbol_day=2, risk_per_trade=0.01175, ext_vixy_ratio_threshold=1.03, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)
    add("PF100_MICRO_R1175_V1025", **common, max_trades_per_symbol_day=2, risk_per_trade=0.01175, ext_vixy_ratio_threshold=1.025, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)
    add("PF100_MICRO_R1175_V1035", **common, max_trades_per_symbol_day=2, risk_per_trade=0.01175, ext_vixy_ratio_threshold=1.035, ext_vixy_sma_period=5, pf1_stop=0.45, pf1_tgt=1.70, second_mom_entry_pct=0.0025, second_risk_mult=0.70, pf1_w2win=0, pf1_pt_on=0, pf1_tr_on=0, pf1_q_on=0)

    return rows


def run_scenario(compile_id, label, params, scenario_name, sy, sm, sd, ey, em, ed):
    p = dict(params)
    p.update({"start_year": sy, "start_month": sm, "start_day": sd, "end_year": ey, "end_month": em, "end_day": ed})

    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": label, "scenario": scenario_name, "error": f"set_parameters_failed: {upd}"}

    ok, bt_id, create = create_backtest(compile_id, f"{label}_{scenario_name}_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "scenario": scenario_name, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "scenario": scenario_name, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = extract_metrics(bt)
    m["candidate"] = label
    m["scenario"] = scenario_name
    return m


def stress_ok(m):
    if m.get("error"):
        return False
    npv = m.get("net_profit_pct")
    dbr = m.get("daily_loss_breaches") or 0
    tbr = m.get("trailing_breaches") or 0
    if npv is None:
        return False
    return dbr == 0 and tbr == 0 and npv >= 0.0


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 D7 RISK X VIXY MICROGRID ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"closed={r.get('closed_trades')} stress_tr={r.get('pf100_stress_trades')} total_tr={r.get('pf100_trades_total')} "
            f"sec_en={r.get('pf100_second_entries')} sec_blk={r.get('pf100_second_blocked')} "
            f"part={r.get('pf100_partial_fills')} trail={r.get('pf100_trail_updates')} qblk={r.get('pf100_quality_blocked')} "
            f"m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} err={r.get('error')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
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
            f"dbr={stress.get('daily_loss_breaches')} tbr={stress.get('trailing_breaches')} sec_en={stress.get('pf100_second_entries')}"
        )
        time.sleep(4)

        if not stress_ok(stress):
            continue

        full = run_scenario(compile_id, label, cfg, "FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31)
        rows.append(full)
        save(rows)
        print(
            f"{label} FULL np={full.get('net_profit_pct')} dd={full.get('drawdown_pct')} "
            f"m_mean={full.get('monthly_mean_pct')} sec_en={full.get('pf100_second_entries')}"
        )
        time.sleep(4)

        oos = run_scenario(compile_id, label, cfg, "OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31)
        rows.append(oos)
        save(rows)
        print(
            f"{label} OOS np={oos.get('net_profit_pct')} dd={oos.get('drawdown_pct')} "
            f"m_mean={oos.get('monthly_mean_pct')} sec_en={oos.get('pf100_second_entries')}"
        )
        time.sleep(4)


if __name__ == "__main__":
    main()
