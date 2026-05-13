"""
PF81 dual-alpha search runner.

Goal:
- Push monthly return materially higher
- Keep prop-firm safety constraints under multi-scenario validation
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf81_dual_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf81_dual_results.txt")


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
            sleep_for = min(backoff_sec * (2 ** attempt), 45)
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
            return True, bt
        if "Error" in status or "Runtime" in status:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def read_backtest(backtest_id):
    data = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
    return data.get("backtest", {}) if isinstance(data, dict) else {}


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
        "sharpe": parse_num(s.get("Sharpe Ratio")),
        "win_rate_pct": parse_pct(s.get("Win Rate")),
        "total_orders": parse_int(s.get("Total Orders")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "consistency_pct": parse_num(rt.get("ConsistencyPct")),
        "price_guard_skips": parse_int(rt.get("PriceGuardSkips")),
    }
    m.update(monthly_stats(bt))
    return m


def scenarios():
    return [
        ("FULL_2022_2026Q1", 2022, 1, 1, 2026, 3, 31, None),
        ("OOS_2025_2026Q1", 2025, 1, 1, 2026, 3, 31, 6.0),
        ("STRESS_2020", 2020, 1, 1, 2020, 12, 31, 0.0),
    ]


def candidates():
    base = {
        "allow_shorts": 1,
        "trade_nq": 1,
        "trade_m2k": 0,
        "trade_mym": 0,
        "regime_mode": "PF81",
        "profile_mode": "PAYOUT_AGGR",
        "entry_hour": 9,
        "entry_min": 40,
        "flatten_hour": 15,
        "flatten_min": 58,
        "max_open_positions": 3,
        "max_trades_per_symbol_day": 2,
        "daily_loss_limit_pct": 0.018,
        "daily_profit_lock_pct": 0.06,
        "trailing_dd_limit_pct": 0.035,
        "dynamic_risk_enabled": 0,
        "second_entry_enabled": 0,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
        "ext_min_signals": 1,
        "ext_vixy_sma_period": 5,
        "max_atr_pct": 0.02,
        "stress_overlay_enabled": 0,
    }

    rows = []
    # Anchor low-risk dual alpha
    c0 = dict(base)
    c0.update(
        {
            "label": "PF81_A0_ANCHOR",
            "risk_per_trade": 0.010,
            "max_contracts_per_trade": 5,
            "ext_vixy_ratio_threshold": 1.03,
            "pf81_stress_risk_mult": 0.35,
            "pf81_stress_min_gap_entry_pct": 0.008,
            "pf81_stress_target_atr_mult": 1.45,
            "pf81_stress_intraday_mom_pct": 0.0012,
        }
    )
    rows.append(c0)

    # Balanced sweep
    for i, (rpt, cmax, vixy_th, srm, sgap, smom) in enumerate(
        [
            (0.012, 6, 1.025, 0.40, 0.0075, 0.0010),
            (0.013, 7, 1.022, 0.45, 0.0070, 0.0009),
            (0.014, 8, 1.020, 0.50, 0.0065, 0.0008),
            (0.015, 8, 1.018, 0.55, 0.0060, 0.0007),
        ],
        start=1,
    ):
        c = dict(base)
        c.update(
            {
                "label": f"PF81_B{i}",
                "risk_per_trade": rpt,
                "max_contracts_per_trade": cmax,
                "ext_vixy_ratio_threshold": vixy_th,
                "pf81_stress_risk_mult": srm,
                "pf81_stress_min_gap_entry_pct": sgap,
                "pf81_stress_intraday_mom_pct": smom,
                "pf81_stress_target_atr_mult": 1.55,
            }
        )
        rows.append(c)

    # Aggressive sweep for 5% monthly attempt
    for i, (rpt, cmax, vixy_th, srm, sstop, stgt, smom) in enumerate(
        [
            (0.018, 9, 1.018, 0.60, 0.85, 1.70, 0.0008),
            (0.020, 10, 1.016, 0.65, 0.85, 1.80, 0.0007),
            (0.022, 11, 1.014, 0.70, 0.80, 1.90, 0.0006),
            (0.024, 12, 1.012, 0.75, 0.80, 2.00, 0.0005),
        ],
        start=1,
    ):
        c = dict(base)
        c.update(
            {
                "label": f"PF81_X{i}",
                "risk_per_trade": rpt,
                "max_contracts_per_trade": cmax,
                "ext_vixy_ratio_threshold": vixy_th,
                "pf81_stress_risk_mult": srm,
                "pf81_stress_stop_atr_mult": sstop,
                "pf81_stress_target_atr_mult": stgt,
                "pf81_stress_intraday_mom_pct": smom,
                "pf81_stress_min_gap_entry_pct": 0.006,
            }
        )
        rows.append(c)

    # Long-bias stress controls
    for i, (rpt, cmax, vixy_th) in enumerate(
        [
            (0.014, 8, 1.020),
            (0.018, 10, 1.016),
            (0.022, 12, 1.012),
        ],
        start=1,
    ):
        c = dict(base)
        c.update(
            {
                "label": f"PF81_L{i}",
                "risk_per_trade": rpt,
                "max_contracts_per_trade": cmax,
                "ext_vixy_ratio_threshold": vixy_th,
                "pf81_stress_risk_mult": 0.55,
                "pf81_stress_disable_shorts": 1,
                "pf81_stress_stop_atr_mult": 0.85,
                "pf81_stress_target_atr_mult": 1.70,
                "pf81_stress_min_gap_entry_pct": 0.0065,
                "pf81_stress_intraday_mom_pct": 0.0008,
            }
        )
        rows.append(c)
    return rows


def pass_safety(row):
    npv = row.get("net_profit_pct")
    dd = row.get("drawdown_pct")
    dbr = row.get("daily_loss_breaches") or 0
    tbr = row.get("trailing_breaches") or 0
    if npv is None or dd is None:
        return False
    if dbr > 0 or tbr > 0:
        return False
    if dd > 4.0:
        return False
    return True


def pass_target(row):
    if not pass_safety(row):
        return False
    target = row.get("target_np_pct")
    if target is None:
        return True
    npv = row.get("net_profit_pct")
    return npv is not None and npv >= target


def score_full(row):
    mean = row.get("monthly_mean_pct")
    med = row.get("monthly_median_pct")
    p25 = row.get("monthly_p25_pct")
    worst = row.get("monthly_worst_pct")
    npv = row.get("net_profit_pct") or 0.0
    if mean is None or med is None or p25 is None or worst is None:
        return -999.0
    score = 5.0 * mean + 2.0 * med + 1.5 * p25 + 0.3 * npv
    if worst < -4.0:
        score -= 12.0 * abs(worst + 4.0)
    return round(score, 3)


def summarize(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["candidate"]].append(r)

    summary = []
    for cand, group in grouped.items():
        by_sc = {g["scenario"]: g for g in group}
        full = by_sc.get("FULL_2022_2026Q1", {})
        oos = by_sc.get("OOS_2025_2026Q1", {})
        stress = by_sc.get("STRESS_2020", {})
        hard = pass_target(oos) and pass_target(stress) and pass_safety(full)
        score = score_full(full) if hard else -999.0
        summary.append(
            {
                "candidate": cand,
                "hard_pass": hard,
                "full_np_pct": full.get("net_profit_pct"),
                "full_dd_pct": full.get("drawdown_pct"),
                "full_monthly_mean_pct": full.get("monthly_mean_pct"),
                "full_monthly_median_pct": full.get("monthly_median_pct"),
                "full_monthly_p25_pct": full.get("monthly_p25_pct"),
                "full_monthly_worst_pct": full.get("monthly_worst_pct"),
                "oos_np_pct": oos.get("net_profit_pct"),
                "stress_np_pct": stress.get("net_profit_pct"),
                "score": score,
            }
        )
    summary.sort(key=lambda x: (x["hard_pass"], x["score"]), reverse=True)
    return summary


def save_output(rows, summary):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows, "summary": summary}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"updated_utc={payload['updated_utc']}")
    lines.append("")
    lines.append("=== SUMMARY ===")
    for s in summary:
        lines.append(
            f"{s['candidate']} hard_pass={s['hard_pass']} score={s['score']} "
            f"full_np={s['full_np_pct']} full_dd={s['full_dd_pct']} mean_m={s['full_monthly_mean_pct']} "
            f"med_m={s['full_monthly_median_pct']} oos={s['oos_np_pct']} stress={s['stress_np_pct']}"
        )
    lines.append("")
    lines.append("=== ROWS ===")
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} pass_target={r.get('pass_target')} "
            f"mean={r.get('monthly_mean_pct')} med={r.get('monthly_median_pct')} p25={r.get('monthly_p25_pct')} "
            f"worst={r.get('monthly_worst_pct')} id={r.get('backtest_id')}"
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
        for sc, sy, sm, sd, ey, em, ed, target_np in scenarios():
            params = dict(cfg)
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
                rows.append({"candidate": label, "scenario": sc, "error": f"set_parameters_failed: {upd}"})
                save_output(rows, summarize(rows))
                continue

            bt_name = f"{label}_{sc}_{int(time.time())}"
            ok, bt_id, create = create_backtest(compile_id, bt_name)
            if not ok or not bt_id:
                rows.append({"candidate": label, "scenario": sc, "error": f"create_backtest_failed: {create}"})
                save_output(rows, summarize(rows))
                continue

            ok, bt = poll_backtest(bt_id)
            if not ok:
                rows.append(
                    {
                        "candidate": label,
                        "scenario": sc,
                        "backtest_id": bt_id,
                        "error": f"poll_failed: {bt}",
                    }
                )
                save_output(rows, summarize(rows))
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
            m["pass_target"] = pass_target(m)
            rows.append(m)
            save_output(rows, summarize(rows))
            print(
                f"{label} {sc} np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} "
                f"mean={m.get('monthly_mean_pct')} med={m.get('monthly_median_pct')} p25={m.get('monthly_p25_pct')} "
                f"dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')} id={m.get('backtest_id')}"
            )
            time.sleep(6)

    summary = summarize(rows)
    save_output(rows, summary)
    print("\n=== RANKING ===")
    for s in summary:
        print(
            f"{s['candidate']} hard_pass={s['hard_pass']} score={s['score']} "
            f"mean={s['full_monthly_mean_pct']} med={s['full_monthly_median_pct']} "
            f"oos={s['oos_np_pct']} stress={s['stress_np_pct']}"
        )


if __name__ == "__main__":
    main()
