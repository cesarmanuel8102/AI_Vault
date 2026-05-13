"""
Deep parameter search for Mean Reversion Equity strategy on QuantConnect.

Workflow:
1) Upload selected source file to project main.py
2) Compile once
3) For each candidate parameter set:
   - Run IS backtest (2022-2024)
   - Run OOS backtest (2025-2026 Mar)
4) Save ranked results to JSON and TXT
"""
import json
import time
from base64 import b64encode
from hashlib import sha256
from pathlib import Path

import requests


UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/x10_search_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/x10_search_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90):
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


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
        state = read.get("state", "")
        if state in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return state == "BuildSuccess", cid, read
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    p = [{"key": k, "value": str(v)} for k, v in params.items()]
    resp = api_post("projects/update", {"projectId": PROJECT_ID, "parameters": p}, timeout=60)
    return bool(resp.get("success")), resp


def create_backtest(compile_id, name):
    data = api_post(
        "backtests/create",
        {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name},
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
    stats = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    return {
        "backtest_id": bt.get("backtestId"),
        "name": bt.get("name"),
        "status": bt.get("status"),
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
    }


def run_period(compile_id, label, params, start_year, end_year, end_month):
    p = dict(params)
    p.update({"start_year": start_year, "end_year": end_year, "end_month": end_month, "initial_cash": 10000})
    ok, upd = set_parameters(p)
    if not ok:
        return {"label": label, "error": f"set_parameters_failed: {upd}"}

    bt_name = f"{label}_{int(time.time())}"
    ok, bt_id, create = create_backtest(compile_id, bt_name)
    if not ok or not bt_id:
        return {"label": label, "error": f"create_backtest_failed: {create}"}

    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"label": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}

    m = extract_metrics(bt)
    m["label"] = label
    m["params"] = p
    return m


def score_row(is_row, oos_row):
    if is_row.get("error") or oos_row.get("error"):
        return -9999.0
    is_np = is_row.get("net_profit_pct") or -999.0
    is_dd = is_row.get("drawdown_pct") or 999.0
    oos_np = oos_row.get("net_profit_pct") or -999.0
    oos_dd = oos_row.get("drawdown_pct") or 999.0
    # prioritize OOS profitability and risk-adjusted robustness
    return (1.2 * oos_np) - (0.7 * oos_dd) + (0.6 * is_np) - (0.3 * is_dd)


def candidates():
    return [
        {"label": "C01", "rsi_entry": 10, "allow_shorts": 1, "risk_per_trade": 0.015, "atr_stop_mult": 2.0, "max_alloc_pct": 0.30, "max_positions": 4},
        {"label": "C02", "rsi_entry": 10, "allow_shorts": 1, "risk_per_trade": 0.020, "atr_stop_mult": 2.0, "max_alloc_pct": 0.30, "max_positions": 4},
        {"label": "C03", "rsi_entry": 10, "allow_shorts": 1, "risk_per_trade": 0.025, "atr_stop_mult": 2.0, "max_alloc_pct": 0.35, "max_positions": 4},
        {"label": "C04", "rsi_entry": 10, "allow_shorts": 1, "risk_per_trade": 0.030, "atr_stop_mult": 1.8, "max_alloc_pct": 0.40, "max_positions": 4},
        {"label": "C05", "rsi_entry": 12, "allow_shorts": 1, "risk_per_trade": 0.020, "atr_stop_mult": 2.2, "max_alloc_pct": 0.35, "max_positions": 4},
        {"label": "C06", "rsi_entry": 8,  "allow_shorts": 1, "risk_per_trade": 0.020, "atr_stop_mult": 1.8, "max_alloc_pct": 0.35, "max_positions": 4},
        {"label": "C07", "rsi_entry": 12, "allow_shorts": 1, "risk_per_trade": 0.030, "atr_stop_mult": 1.5, "max_alloc_pct": 0.50, "max_positions": 4},
        {"label": "C08", "rsi_entry": 9,  "allow_shorts": 1, "risk_per_trade": 0.025, "atr_stop_mult": 1.6, "max_alloc_pct": 0.45, "max_positions": 4},
        {"label": "C09", "rsi_entry": 10, "allow_shorts": 0, "risk_per_trade": 0.030, "atr_stop_mult": 1.5, "max_alloc_pct": 0.60, "max_positions": 4},
        {"label": "C10", "rsi_entry": 12, "allow_shorts": 0, "risk_per_trade": 0.035, "atr_stop_mult": 1.5, "max_alloc_pct": 0.60, "max_positions": 4},
    ]


def save_rows(rows):
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = []
    lines.append(f"updated_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    ranked = sorted(rows, key=lambda r: r.get("score", -9999), reverse=True)
    for r in ranked:
        lines.append(
            f"{r['label']} score={r.get('score'):.3f} "
            f"IS(np={r.get('is_np')},dd={r.get('is_dd')}) "
            f"OOS(np={r.get('oos_np')},dd={r.get('oos_dd')}) "
            f"is_id={r.get('is_id')} oos_id={r.get('oos_id')}"
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
        params = {k: v for k, v in c.items() if k != "label"}
        print(f"\n=== {label} params={params} ===")

        is_row = run_period(compile_id, f"{label}_IS_2022_2024", params, 2022, 2024, 12)
        print(f"IS done: np={is_row.get('net_profit_pct')} dd={is_row.get('drawdown_pct')} id={is_row.get('backtest_id')}")

        time.sleep(5)

        oos_row = run_period(compile_id, f"{label}_OOS_2025_2026M3", params, 2025, 2026, 3)
        print(f"OOS done: np={oos_row.get('net_profit_pct')} dd={oos_row.get('drawdown_pct')} id={oos_row.get('backtest_id')}")

        row = {
            "label": label,
            "params": params,
            "is_np": is_row.get("net_profit_pct"),
            "is_dd": is_row.get("drawdown_pct"),
            "is_id": is_row.get("backtest_id"),
            "oos_np": oos_row.get("net_profit_pct"),
            "oos_dd": oos_row.get("drawdown_pct"),
            "oos_id": oos_row.get("backtest_id"),
            "is_error": is_row.get("error"),
            "oos_error": oos_row.get("error"),
        }
        row["score"] = score_row(is_row, oos_row)
        rows.append(row)
        save_rows(rows)

        # small cooldown to avoid QC rate limits
        time.sleep(7)

    ranked = sorted(rows, key=lambda r: r.get("score", -9999), reverse=True)
    print("\n=== TOP 3 ===")
    for r in ranked[:3]:
        print(
            f"{r['label']} score={r['score']:.3f} "
            f"IS {r['is_np']}%/{r['is_dd']}% OOS {r['oos_np']}%/{r['oos_dd']}%"
        )


if __name__ == "__main__":
    main()

