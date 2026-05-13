"""
Quarterly walk-forward stability run for Mean Reversion Equity strategy.

Runs one backtest per quarter over:
2022Q1 ... 2026Q1
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/wf_quarterly_c11.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/wf_quarterly_c11.txt")


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
        "profit_loss_ratio": parse_pct(s.get("Profit-Loss Ratio")),
        "total_orders": s.get("Total Orders"),
    }


def quarter_periods():
    # (start_y, start_m, start_d, end_y, end_m, end_d, label)
    periods = []
    for y in (2022, 2023, 2024, 2025):
        periods += [
            (y, 1, 1,  y, 3, 31, f"{y}Q1"),
            (y, 4, 1,  y, 6, 30, f"{y}Q2"),
            (y, 7, 1,  y, 9, 30, f"{y}Q3"),
            (y, 10, 1, y, 12, 31, f"{y}Q4"),
        ]
    periods.append((2026, 1, 1, 2026, 3, 31, "2026Q1"))
    return periods


def save_rows(rows):
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    pos = sum(1 for r in rows if (r.get("net_profit_pct") or 0) > 0)
    total = len(rows)
    avg_np = sum((r.get("net_profit_pct") or 0) for r in rows) / total if total else 0
    worst_dd = max((r.get("drawdown_pct") or 0) for r in rows) if rows else 0
    lines = [
        f"updated_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"quarters={total} positive={pos} positive_rate={100.0*pos/total if total else 0:.1f}%",
        f"avg_net_profit_pct={avg_np:.3f}",
        f"worst_drawdown_pct={worst_dd:.3f}",
        "",
    ]
    for r in rows:
        lines.append(
            f"{r['period']}: np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"sh={r.get('sharpe')} wr={r.get('win_rate_pct')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    base_params = {
        "initial_cash": 10000,
        "rsi_entry": 9,
        "allow_shorts": 1,
        "risk_per_trade": 0.03,
        "atr_stop_mult": 1.6,
        "max_alloc_pct": 0.5,
        "max_positions": 4,
        "macro_short_filter": 0,
        "slippage_bps": 0,
    }

    ok, up = upload_source(SOURCE_FILE)
    if not ok:
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    rows = []
    for sy, sm, sd, ey, em, ed, label in quarter_periods():
        params = dict(base_params)
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
            rows.append({"period": label, "error": f"set_parameters_failed: {upd}"})
            save_rows(rows)
            time.sleep(8)
            continue

        bt_name = f"WF_C11_{label}_{int(time.time())}"
        ok, bt_id, create = create_backtest(compile_id, bt_name)
        if not ok or not bt_id:
            rows.append({"period": label, "error": f"create_backtest_failed: {create}"})
            save_rows(rows)
            time.sleep(8)
            continue

        ok, bt = poll_backtest(bt_id)
        if not ok:
            rows.append({"period": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"})
            save_rows(rows)
            time.sleep(8)
            continue

        m = extract_metrics(bt)
        m["period"] = label
        rows.append(m)
        save_rows(rows)
        print(f"{label} np={m.get('net_profit_pct')} dd={m.get('drawdown_pct')} id={m.get('backtest_id')}")
        time.sleep(8)

    pos = sum(1 for r in rows if (r.get("net_profit_pct") or 0) > 0)
    total = len(rows)
    print(f"\nWF done: {pos}/{total} positive quarters")


if __name__ == "__main__":
    main()

