"""
Slippage stress test for Mean Reversion Equity candidates.

Tests:
- C11 and C08
- slippage_bps in [0, 5, 10, 15]
- IS: 2022-01-01 to 2024-12-31
- OOS: 2025-01-01 to 2026-03-31
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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/slippage_stress_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/slippage_stress_results.txt")


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


def save_rows(rows):
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = [f"updated_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", ""]
    ranked = sorted(rows, key=lambda r: r.get("score", -9999), reverse=True)
    for r in ranked:
        lines.append(
            f"{r['label']} slp={r['slippage_bps']}bps score={r['score']:.3f} "
            f"IS(np={r['is_np']},dd={r['is_dd']}) OOS(np={r['oos_np']},dd={r['oos_dd']}) "
            f"is_id={r.get('is_id')} oos_id={r.get('oos_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def score_row(is_np, is_dd, oos_np, oos_dd):
    is_np = is_np if is_np is not None else -999.0
    is_dd = is_dd if is_dd is not None else 999.0
    oos_np = oos_np if oos_np is not None else -999.0
    oos_dd = oos_dd if oos_dd is not None else 999.0
    return (1.4 * oos_np) - (0.8 * oos_dd) + (0.5 * is_np) - (0.3 * is_dd)


def run_period(compile_id, name, params):
    ok, upd = set_parameters(params)
    if not ok:
        return {"error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest(compile_id, name)
    if not ok or not bt_id:
        return {"error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"backtest_id": bt_id, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt)
    return m


def main():
    ok, up = upload_source(SOURCE_FILE)
    if not ok:
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")

    base_common = {
        "initial_cash": 10000,
        "allow_shorts": 1,
        "max_positions": 4,
        "macro_short_filter": 0,
    }
    c11 = {
        "rsi_entry": 9,
        "risk_per_trade": 0.03,
        "atr_stop_mult": 1.6,
        "max_alloc_pct": 0.5,
    }
    c08 = {
        "rsi_entry": 9,
        "risk_per_trade": 0.025,
        "atr_stop_mult": 1.6,
        "max_alloc_pct": 0.45,
    }
    candidates = [("C11", c11), ("C08", c08)]
    slippages = [0, 5, 10, 15]

    rows = []
    for label, cfg in candidates:
        for slp in slippages:
            params_is = dict(base_common)
            params_is.update(cfg)
            params_is.update(
                {
                    "slippage_bps": slp,
                    "start_year": 2022,
                    "start_month": 1,
                    "start_day": 1,
                    "end_year": 2024,
                    "end_month": 12,
                    "end_day": 31,
                }
            )
            params_oos = dict(base_common)
            params_oos.update(cfg)
            params_oos.update(
                {
                    "slippage_bps": slp,
                    "start_year": 2025,
                    "start_month": 1,
                    "start_day": 1,
                    "end_year": 2026,
                    "end_month": 3,
                    "end_day": 31,
                }
            )

            run_tag = f"{label}_SLP{slp}"
            print(f"\n=== {run_tag} ===")

            is_name = f"{run_tag}_IS_{int(time.time())}"
            is_row = run_period(compile_id, is_name, params_is)
            print(f"IS: np={is_row.get('net_profit_pct')} dd={is_row.get('drawdown_pct')} id={is_row.get('backtest_id')}")
            time.sleep(6)

            oos_name = f"{run_tag}_OOS_{int(time.time())}"
            oos_row = run_period(compile_id, oos_name, params_oos)
            print(f"OOS: np={oos_row.get('net_profit_pct')} dd={oos_row.get('drawdown_pct')} id={oos_row.get('backtest_id')}")

            row = {
                "label": label,
                "slippage_bps": slp,
                "is_np": is_row.get("net_profit_pct"),
                "is_dd": is_row.get("drawdown_pct"),
                "is_id": is_row.get("backtest_id"),
                "oos_np": oos_row.get("net_profit_pct"),
                "oos_dd": oos_row.get("drawdown_pct"),
                "oos_id": oos_row.get("backtest_id"),
                "is_error": is_row.get("error"),
                "oos_error": oos_row.get("error"),
            }
            row["score"] = score_row(row["is_np"], row["is_dd"], row["oos_np"], row["oos_dd"])
            rows.append(row)
            save_rows(rows)
            time.sleep(8)

    ranked = sorted(rows, key=lambda r: r.get("score", -9999), reverse=True)
    print("\n=== TOP ===")
    for r in ranked[:5]:
        print(
            f"{r['label']} slp={r['slippage_bps']} score={r['score']:.3f} "
            f"IS {r['is_np']}%/{r['is_dd']}% OOS {r['oos_np']}%/{r['oos_dd']}%"
        )


if __name__ == "__main__":
    main()

