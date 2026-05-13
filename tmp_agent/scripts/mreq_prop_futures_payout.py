"""
Payout optimization runner for prop-futures strategy.

Goal:
- Keep survival constraints (no daily/trailing breaches, bounded DD)
- Maximize monthly utility profile on full period (2022 -> 2026Q1)
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/prop_futures_payout_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/prop_futures_payout_results.txt")


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


def poll_backtest(backtest_id, timeout_sec=1500):
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
        "regime_mode": "PF80",
        "profile_mode": "PAYOUT_SAFE",
        "stress_overlay_enabled": 0,
        "ext_use_vix": 0,
        "ext_use_vixy": 1,
        "ext_vixy_ratio_threshold": 1.03,
        "ext_vixy_sma_period": 5,
        "ext_rv_threshold": 1.0,
        "ext_gap_z_threshold": 99.0,
        "ext_gap_abs_threshold": 1.0,
        "entry_hour": 9,
        "entry_min": 40,
        "second_entry_enabled": 0,
        "max_trades_per_symbol_day": 1,
        "daily_profit_lock_pct": 0.04,
        "daily_loss_limit_pct": 0.018,
        "trailing_dd_limit_pct": 0.035,
        "max_open_positions": 3,
        "max_contracts_per_trade": 3,
        "dynamic_risk_enabled": 0,
    }
    rows = []

    b = dict(base)
    b.update({"label": "PF90_BASELINE_PASS", "risk_per_trade": 0.00825, "dynamic_risk_enabled": 0, "second_entry_enabled": 0})
    rows.append(b)

    p120 = dict(base)
    p120.update(
        {
            "label": "PF120_PAYOUT_SCALE_R1000_C5",
            "profile_mode": "PAYOUT_SAFE",
            "risk_per_trade": 0.0100,
            "max_contracts_per_trade": 5,
            "dynamic_risk_enabled": 0,
            "second_entry_enabled": 0,
        }
    )
    rows.append(p120)

    s1 = dict(base)
    s1.update(
        {
            "label": "PF100_SAFE_A",
            "profile_mode": "PAYOUT_SAFE",
            "risk_per_trade": 0.0095,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.80,
            "dynamic_risk_ceiling_mult": 1.20,
            "dynamic_risk_soft_dd_pct": 0.010,
            "dynamic_risk_hard_dd_pct": 0.027,
            "dynamic_risk_profit_boost_pct": 0.006,
            "dynamic_risk_profit_boost_mult": 1.10,
            "max_trades_per_symbol_day": 2,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 20,
        }
    )
    rows.append(s1)

    s2 = dict(base)
    s2.update(
        {
            "label": "PF100_SAFE_B",
            "profile_mode": "PAYOUT_SAFE",
            "risk_per_trade": 0.0105,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.78,
            "dynamic_risk_ceiling_mult": 1.25,
            "dynamic_risk_soft_dd_pct": 0.009,
            "dynamic_risk_hard_dd_pct": 0.026,
            "dynamic_risk_profit_boost_pct": 0.006,
            "dynamic_risk_profit_boost_mult": 1.12,
            "max_trades_per_symbol_day": 2,
            "max_contracts_per_trade": 4,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 20,
        }
    )
    rows.append(s2)

    s3 = dict(base)
    s3.update(
        {
            "label": "PF100_SAFE_C",
            "profile_mode": "PAYOUT_SAFE",
            "risk_per_trade": 0.0110,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.75,
            "dynamic_risk_ceiling_mult": 1.30,
            "dynamic_risk_soft_dd_pct": 0.009,
            "dynamic_risk_hard_dd_pct": 0.025,
            "dynamic_risk_profit_boost_pct": 0.007,
            "dynamic_risk_profit_boost_mult": 1.15,
            "max_trades_per_symbol_day": 2,
            "max_contracts_per_trade": 4,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 25,
        }
    )
    rows.append(s3)

    a1 = dict(base)
    a1.update(
        {
            "label": "PF110_AGGR_A",
            "profile_mode": "PAYOUT_AGGR",
            "risk_per_trade": 0.0125,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.70,
            "dynamic_risk_ceiling_mult": 1.45,
            "dynamic_risk_soft_dd_pct": 0.008,
            "dynamic_risk_hard_dd_pct": 0.024,
            "dynamic_risk_profit_boost_pct": 0.007,
            "dynamic_risk_profit_boost_mult": 1.18,
            "max_trades_per_symbol_day": 2,
            "max_contracts_per_trade": 4,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 25,
            "daily_profit_lock_pct": 0.05,
        }
    )
    rows.append(a1)

    a2 = dict(base)
    a2.update(
        {
            "label": "PF110_AGGR_B",
            "profile_mode": "PAYOUT_AGGR",
            "risk_per_trade": 0.0135,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.68,
            "dynamic_risk_ceiling_mult": 1.55,
            "dynamic_risk_soft_dd_pct": 0.008,
            "dynamic_risk_hard_dd_pct": 0.023,
            "dynamic_risk_profit_boost_pct": 0.008,
            "dynamic_risk_profit_boost_mult": 1.20,
            "max_trades_per_symbol_day": 2,
            "max_contracts_per_trade": 4,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 30,
            "daily_profit_lock_pct": 0.06,
        }
    )
    rows.append(a2)

    a3 = dict(base)
    a3.update(
        {
            "label": "PF110_AGGR_C",
            "profile_mode": "PAYOUT_AGGR",
            "risk_per_trade": 0.0150,
            "dynamic_risk_enabled": 1,
            "dynamic_risk_floor_mult": 0.65,
            "dynamic_risk_ceiling_mult": 1.65,
            "dynamic_risk_soft_dd_pct": 0.007,
            "dynamic_risk_hard_dd_pct": 0.022,
            "dynamic_risk_profit_boost_pct": 0.008,
            "dynamic_risk_profit_boost_mult": 1.22,
            "max_trades_per_symbol_day": 2,
            "max_contracts_per_trade": 5,
            "second_entry_enabled": 1,
            "second_entry_hour": 11,
            "second_entry_min": 30,
            "daily_profit_lock_pct": 0.07,
        }
    )
    rows.append(a3)

    fail_ref = dict(base)
    fail_ref.update(
        {
            "label": "PF121_HIGH_RET_REFERENCE",
            "profile_mode": "PAYOUT_AGGR",
            "risk_per_trade": 0.0120,
            "max_contracts_per_trade": 4,
            "ext_vixy_ratio_threshold": 1.02,
            "dynamic_risk_enabled": 0,
            "second_entry_enabled": 0,
        }
    )
    rows.append(fail_ref)

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
    npv = row.get("net_profit_pct") or 0.0
    med = row.get("monthly_median_pct")
    mean = row.get("monthly_mean_pct")
    p25 = row.get("monthly_p25_pct")
    worst = row.get("monthly_worst_pct")
    pos = row.get("monthly_positive_rate_pct")
    if med is None or mean is None or p25 is None or worst is None or pos is None:
        return -999.0
    score = 4.0 * med + 1.5 * mean + 2.0 * p25 + 0.4 * npv + 0.02 * pos
    if worst < -3.0:
        score -= 10.0 * abs(worst + 3.0)
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
                "full_monthly_median_pct": full.get("monthly_median_pct"),
                "full_monthly_p25_pct": full.get("monthly_p25_pct"),
                "full_monthly_worst_pct": full.get("monthly_worst_pct"),
                "full_monthly_positive_rate_pct": full.get("monthly_positive_rate_pct"),
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
            f"full_np={s['full_np_pct']} med_m={s['full_monthly_median_pct']} p25_m={s['full_monthly_p25_pct']} "
            f"oos={s['oos_np_pct']} stress={s['stress_np_pct']}"
        )
    lines.append("")
    lines.append("=== ROWS ===")
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} pass_target={r.get('pass_target')} "
            f"med={r.get('monthly_median_pct')} p25={r.get('monthly_p25_pct')} worst={r.get('monthly_worst_pct')} "
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
                f"med={m.get('monthly_median_pct')} p25={m.get('monthly_p25_pct')} "
                f"dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')} id={m.get('backtest_id')}"
            )
            time.sleep(6)

    summary = summarize(rows)
    save_output(rows, summary)
    print("\n=== RANKING ===")
    for s in summary:
        print(
            f"{s['candidate']} hard_pass={s['hard_pass']} score={s['score']} "
            f"med={s['full_monthly_median_pct']} p25={s['full_monthly_p25_pct']} "
            f"oos={s['oos_np_pct']} stress={s['stress_np_pct']}"
        )


if __name__ == "__main__":
    main()
