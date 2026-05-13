"""
QC consistency suite for Mean Reversion Equity strategy.

Runs the same strategy config across multiple market scenarios and two
execution-friction settings (slippage 0 bps and 5 bps), then summarizes
stability of QC metrics.
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/qc_consistency_suite.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/qc_consistency_suite.txt")


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
            # Exponential backoff for transient DNS/network/API hiccups.
            sleep_for = backoff_sec * (2 ** attempt)
            time.sleep(min(sleep_for, 60))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} payload={payload} err={last_err}")


def parse_pct(s):
    try:
        return float(str(s).replace("%", "").replace(" ", ""))
    except Exception:
        return None


def parse_int(s):
    try:
        return int(str(s).replace(",", "").strip())
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
    for _ in range(80):
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


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "sharpe": parse_pct(s.get("Sharpe Ratio")),
        "win_rate_pct": parse_pct(s.get("Win Rate")),
        "loss_rate_pct": parse_pct(s.get("Loss Rate")),
        "profit_loss_ratio": parse_pct(s.get("Profit-Loss Ratio")),
        "total_orders": parse_int(s.get("Total Orders")),
    }


def scenarios():
    # label, start_y,m,d, end_y,m,d
    return [
        ("RECOVERY_2010_2012", 2010, 1, 1, 2012, 12, 31),
        ("BULL_2013_2017", 2013, 1, 1, 2017, 12, 31),
        ("CHOP_2018_2019", 2018, 1, 1, 2019, 12, 31),
        ("COVID_2020", 2020, 1, 1, 2020, 12, 31),
        ("BULL_2021", 2021, 1, 1, 2021, 12, 31),
        ("BEAR_2022", 2022, 1, 1, 2022, 12, 31),
        ("RECENT_2023_2024", 2023, 1, 1, 2024, 12, 31),
        ("LATEST_2025_2026Q1", 2025, 1, 1, 2026, 3, 31),
    ]


def summarize(rows):
    by_slip = {}
    for r in rows:
        by_slip.setdefault(r["slippage_bps"], []).append(r)

    summary = {}
    for slp, group in by_slip.items():
        np_vals = [r["net_profit_pct"] for r in group if r.get("net_profit_pct") is not None]
        dd_vals = [r["drawdown_pct"] for r in group if r.get("drawdown_pct") is not None]
        wr_vals = [r["win_rate_pct"] for r in group if r.get("win_rate_pct") is not None]
        sh_vals = [r["sharpe"] for r in group if r.get("sharpe") is not None]

        summary[slp] = {
            "scenarios": len(group),
            "positive_net_profit_count": sum(1 for v in np_vals if v > 0),
            "positive_net_profit_rate_pct": round(100 * sum(1 for v in np_vals if v > 0) / len(np_vals), 2) if np_vals else None,
            "avg_net_profit_pct": round(statistics.mean(np_vals), 3) if np_vals else None,
            "median_net_profit_pct": round(statistics.median(np_vals), 3) if np_vals else None,
            "stdev_net_profit_pct": round(statistics.pstdev(np_vals), 3) if len(np_vals) > 1 else 0.0,
            "worst_net_profit_pct": min(np_vals) if np_vals else None,
            "best_net_profit_pct": max(np_vals) if np_vals else None,
            "avg_drawdown_pct": round(statistics.mean(dd_vals), 3) if dd_vals else None,
            "worst_drawdown_pct": max(dd_vals) if dd_vals else None,
            "avg_win_rate_pct": round(statistics.mean(wr_vals), 3) if wr_vals else None,
            "avg_sharpe": round(statistics.mean(sh_vals), 3) if sh_vals else None,
        }
    return summary


def save_output(rows, summary):
    payload = {"rows": rows, "summary": summary, "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"updated_utc={payload['updated_utc']}", ""]
    for slp in sorted(summary.keys()):
        s = summary[slp]
        lines.append(
            f"slippage={slp}bps | positive={s['positive_net_profit_count']}/{s['scenarios']} "
            f"({s['positive_net_profit_rate_pct']}%) | avg_np={s['avg_net_profit_pct']} "
            f"| median_np={s['median_net_profit_pct']} | stdev_np={s['stdev_net_profit_pct']} "
            f"| avg_dd={s['avg_drawdown_pct']} | worst_dd={s['worst_drawdown_pct']}"
        )
    lines.append("")
    for r in rows:
        lines.append(
            f"{r['label']} slp={r['slippage_bps']} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"sh={r.get('sharpe')} wr={r.get('win_rate_pct')} orders={r.get('total_orders')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def load_existing_rows() -> List[Dict]:
    if not OUT_JSON.exists():
        return []
    try:
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        return data.get("rows", []) if isinstance(data, dict) else []
    except Exception:
        return []


def main():
    # Robust defaults (S08 profile)
    base = {
        "initial_cash": 10000,
        "rsi_entry": 10,
        "allow_shorts": 1,
        "risk_per_trade": 0.02,
        "atr_stop_mult": 2.0,
        "max_alloc_pct": 0.35,
        "max_positions": 3,
        "macro_short_filter": 0,
    }
    slippage_levels = [0, 5]

    ok, up = upload_source(SOURCE_FILE)
    if not ok:
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    rows = load_existing_rows()
    completed = {(r.get("label"), r.get("slippage_bps")) for r in rows if r.get("backtest_id")}
    for slp in slippage_levels:
        for label, sy, sm, sd, ey, em, ed in scenarios():
            if (label, slp) in completed:
                continue
            params = dict(base)
            params.update(
                {
                    "slippage_bps": slp,
                    "start_year": sy,
                    "start_month": sm,
                    "start_day": sd,
                    "end_year": ey,
                    "end_month": em,
                    "end_day": ed,
                }
            )
            run_label = f"{label}_SLP{slp}"
            ok, upd = set_parameters(params)
            if not ok:
                rows.append({"label": label, "slippage_bps": slp, "error": f"set_parameters_failed: {upd}"})
                save_output(rows, summarize(rows))
                time.sleep(8)
                continue

            bt_name = f"{run_label}_{int(time.time())}"
            ok, bt_id, create = create_backtest(compile_id, bt_name)
            if not ok or not bt_id:
                rows.append({"label": label, "slippage_bps": slp, "error": f"create_backtest_failed: {create}"})
                save_output(rows, summarize(rows))
                time.sleep(8)
                continue

            ok, bt = poll_backtest(bt_id)
            if not ok:
                rows.append({"label": label, "slippage_bps": slp, "backtest_id": bt_id, "error": f"poll_failed: {bt}"})
                save_output(rows, summarize(rows))
                time.sleep(8)
                continue

            m = extract_metrics(bt)
            m["label"] = label
            m["slippage_bps"] = slp
            rows.append(m)
            save_output(rows, summarize(rows))
            print(
                f"{label} slp={slp} np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} "
                f"wr={m.get('win_rate_pct')} id={m.get('backtest_id')}"
            )
            time.sleep(8)

    summary = summarize(rows)
    save_output(rows, summary)
    print("\n=== SUMMARY ===")
    for slp in sorted(summary.keys()):
        print(f"slippage={slp}bps -> {summary[slp]}")


if __name__ == "__main__":
    main()
