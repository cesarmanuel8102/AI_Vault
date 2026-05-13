import argparse
import hashlib
import json
import time
from base64 import b64encode
from datetime import datetime
from pathlib import Path

import requests


UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/debug_qc/matrix_results_2024_now.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/debug_qc/matrix_results_2024_now.txt")


def headers():
    ts = str(int(time.time()))
    sig = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=60):
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    data = api_post("projects/update", payload, timeout=30)
    return bool(data.get("success")), data


def compile_project():
    create = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=60)
    cid = create.get("compileId", "")
    if not cid:
        return False, "", create
    for _ in range(60):
        read = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=30)
        state = read.get("state", "")
        if state in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return state == "BuildSuccess", cid, read
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def create_backtest(compile_id, name):
    data = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
        timeout=60,
    )
    bt = data.get("backtest", {})
    return bool(data.get("success")), bt.get("backtestId", ""), data


def poll_backtest(backtest_id, timeout_sec=900):
    elapsed = 0
    while elapsed < timeout_sec:
        data = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=60)
        bt = data.get("backtest", {})
        status = str(bt.get("status", ""))
        if "Completed" in status:
            return True, bt
        if "Error" in status or "Runtime" in status:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


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


def extract_metrics(bt):
    stats = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "name": bt.get("name"),
        "status": bt.get("status"),
        "backtest_start": bt.get("backtestStart"),
        "backtest_end": bt.get("backtestEnd"),
        "tradeable_dates": bt.get("tradeableDates"),
        "net_profit_pct": parse_pct(stats.get("Net Profit")),
        "drawdown_pct": parse_pct(stats.get("Drawdown")),
        "sharpe": parse_pct(stats.get("Sharpe Ratio")),
        "win_rate_pct": parse_pct(stats.get("Win Rate")),
        "loss_rate_pct": parse_pct(stats.get("Loss Rate")),
        "car_pct": parse_pct(stats.get("Compounding Annual Return")),
        "total_orders": parse_int(stats.get("Total Orders")),
        "profit_loss_ratio": parse_pct(stats.get("Profit-Loss Ratio")),
        "fees_usd": stats.get("Total Fees") or rt.get("Fees"),
        "runtime_equity": rt.get("Equity"),
        "runtime_return": rt.get("Return"),
        "runtime_volume": rt.get("Volume"),
    }


def matrix_combos():
    combos = []
    idx = 1
    for atr in (0.10, 0.15, 0.20):
        for start_min in (1, 5):
            for rsi_low, rsi_high in ((45, 70), (48, 68)):
                combos.append(
                    {
                        "label": f"M{idx:02d}",
                        "min_atr_ratio": atr,
                        "trade_start_min": start_min,
                        "rsi_low": rsi_low,
                        "rsi_high": rsi_high,
                    }
                )
                idx += 1
    return combos


def base_params():
    return {
        "start_year": 2024,
        "start_month": 1,
        "start_day": 1,
        "end_year": 2026,
        "end_month": 4,
        "end_day": 10,
        "trade_end_min": 30,
        "diag_every_min": 60,
        "stop_loss": 0.002,
        "profit_target": 0.004,
        "risk_per_trade": 0.01,
        "max_daily_trades": 6,
    }


def load_results():
    if OUT_JSON.exists():
        try:
            return json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_results(rows):
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = []
    lines.append(f"updated_utc={datetime.utcnow().isoformat()}Z")
    for r in sorted(rows, key=lambda x: ((x.get("net_profit_pct") or -999), -(x.get("sharpe") or -999), -(x.get("win_rate_pct") or -999)), reverse=True):
        lines.append(
            f"{r.get('label','?')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"sh={r.get('sharpe')} wr={r.get('win_rate_pct')} orders={r.get('total_orders')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def run_one(label, params):
    merged = base_params()
    merged.update(params)
    ok, resp = set_parameters(merged)
    if not ok:
        return {"label": label, "error": f"set_parameters_failed: {resp}"}

    ok, cid, cdata = compile_project()
    if not ok:
        return {"label": label, "error": f"compile_failed: {cdata}"}

    bt_name = f"{label}_2024_now_{int(time.time())}"
    ok, bt_id, create = create_backtest(cid, bt_name)
    if not ok or not bt_id:
        return {"label": label, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"label": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    metrics = extract_metrics(bt)
    metrics["label"] = label
    metrics["params"] = merged
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["flex", "matrix"], required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()

    rows = load_results()

    if args.mode == "flex":
        flex_params = {
            "min_atr_ratio": 0.10,
            "trade_start_min": 1,
            "rsi_low": 45,
            "rsi_high": 70,
            "trade_end_min": 20,
            "max_daily_trades": 8,
            "stop_loss": 0.0025,
            "profit_target": 0.0050,
        }
        result = run_one("FLEX", flex_params)
        rows = [r for r in rows if r.get("label") != "FLEX"]
        rows.append(result)
        save_results(rows)
        print(json.dumps(result, indent=2))
        return

    combos = matrix_combos()
    subset = combos[args.start : args.start + args.count]
    print(f"running matrix subset start={args.start} count={len(subset)}")
    for item in subset:
        label = item["label"]
        params = {k: v for k, v in item.items() if k != "label"}
        print(f"run {label} params={params}")
        result = run_one(label, params)
        rows = [r for r in rows if r.get("label") != label]
        rows.append(result)
        save_results(rows)
        print(f"done {label} np={result.get('net_profit_pct')} dd={result.get('drawdown_pct')} id={result.get('backtest_id')}")


if __name__ == "__main__":
    main()
