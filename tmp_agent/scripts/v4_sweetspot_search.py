"""
V4 Sweet Spot Search: 3 intermediate combos between BASELINE and G22
Goal: Find DD < 30% that still passes kill gates (CAGR>=12%, Sharpe>=1.0)

Already known:
  V4 BASELINE (PT=0.35, R=0.05): Return=+190.9%, Sharpe=1.563, DD=34.1% -> PASS
  V4 G22     (PT=0.40, R=0.04): Return=+67.2%,  Sharpe=0.727, DD=29.4% -> FAIL

Testing 3 intermediate combos:
  V4-A: PT=0.35, R=0.045  (slightly less risk, champion PT)
  V4-B: PT=0.35, R=0.04   (G22 risk, champion PT)
  V4-C: PT=0.40, R=0.05   (G22 PT, champion risk)
"""
import sys
import time
import json
import requests
from hashlib import sha256
from base64 import b64encode

sys.stdout.reconfigure(encoding='ascii', errors='replace')

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

RESULT_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v4_sweetspot_results.json"

RUNS = [
    {
        "name": "V4-A (PT=0.35 R=0.045)",
        "params": {
            "profit_target_pct": "0.35",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.045",
        },
    },
    {
        "name": "V4-B (PT=0.35 R=0.04)",
        "params": {
            "profit_target_pct": "0.35",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.04",
        },
    },
    {
        "name": "V4-C (PT=0.40 R=0.05)",
        "params": {
            "profit_target_pct": "0.40",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.05",
        },
    },
]

FIXED_PARAMS = {
    "start_year": "2023",
    "end_year": "2024",
    "end_month": "12",
    "dte_min": "14",
    "dte_max": "30",
}


def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}{endpoint}", headers=headers(), json=payload, timeout=timeout)
            return r.json()
        except Exception as e:
            print(f"  API error ({attempt+1}/{retries}): {str(e)[:80]}")
            time.sleep(5)
    return {"success": False, "errors": ["max retries"]}


def run_backtest(run_config):
    name = run_config["name"]
    params = {**run_config["params"], **FIXED_PARAMS}

    print(f"\n{'='*60}")
    print(f"RUNNING: {name}")
    print(f"Time: {time.strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    print("  Setting parameters...")
    param_list = [{"key": k, "value": v} for k, v in params.items()]
    data = api_post("/projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    if not data.get("success"):
        print(f"  FAILED to set params: {data}")
        return None

    print("  Compiling...")
    data = api_post("/compile/create", {"projectId": PROJECT_ID})
    cid = data.get("compileId", "")
    state = data.get("state", "")
    waited = 0
    while state not in ("BuildSuccess", "BuildError") and waited < 120:
        time.sleep(3)
        waited += 3
        data = api_post("/compile/read", {"projectId": PROJECT_ID, "compileId": cid})
        state = data.get("state", "")
    if state != "BuildSuccess":
        print(f"  COMPILE FAILED: {state}")
        return None
    print(f"  Compiled: {cid}")

    print(f"  Launching: {name}")
    for attempt in range(30):
        data = api_post("/backtests/create", {
            "projectId": PROJECT_ID, "compileId": cid, "backtestName": name
        })
        if data.get("success"):
            bt_id = data.get("backtest", {}).get("backtestId", "")
            print(f"  BT ID: {bt_id}")
            break
        errors = " ".join(data.get("errors", []))
        if "no spare nodes" in errors.lower():
            print(f"  Node busy, waiting 30s... ({attempt+1}/30)")
            time.sleep(30)
        else:
            print(f"  Launch error: {errors[:200]}")
            return None
    else:
        print("  Max retries exhausted")
        return None

    print("  Waiting for completion...")
    bt = {}
    for i in range(120):
        time.sleep(10)
        data = api_post("/backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = data.get("backtest", {})
        status = bt.get("status", "")
        progress = bt.get("progress", 0)
        elapsed = (i + 1) * 10
        if elapsed % 30 == 0:
            pstr = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
            print(f"    [{elapsed}s] status={status} progress={pstr}")
        if status in ("Completed.", "Completed"):
            break
        if "Error" in str(status) or "Runtime" in str(status):
            print(f"  BACKTEST ERROR: {status}")
            return None
    else:
        print("  TIMEOUT")
        return None

    stats = bt.get("statistics", {}) or {}

    def sf(key, default="0"):
        try:
            return float(str(stats.get(key, default)).replace("%", "").replace(",", ""))
        except:
            return 0.0

    result = {
        "name": name,
        "bt_id": bt_id,
        "params": run_config["params"],
        "net_profit": sf("Net Profit"),
        "cagr": sf("Compounding Annual Return"),
        "sharpe": sf("Sharpe Ratio"),
        "sortino": sf("Sortino Ratio"),
        "max_dd": sf("Drawdown"),
        "total_trades": int(sf("Total Orders")),
        "win_rate": sf("Win Rate"),
        "profit_factor": sf("Profit-Loss Ratio"),
        "annual_vol": sf("Annual Standard Deviation"),
        "psr": sf("Probabilistic Sharpe Ratio"),
    }

    gate = "PASS" if (result["cagr"] >= 12.0 and result["sharpe"] >= 1.0) else "FAIL"
    result["gate"] = gate

    print(f"\n  {'='*50}")
    print(f"  {name}")
    print(f"  {'='*50}")
    print(f"  Return:  {result['net_profit']:+.1f}%")
    print(f"  CAGR:    {result['cagr']:.1f}%")
    print(f"  Sharpe:  {result['sharpe']:.3f}")
    print(f"  Sortino: {result['sortino']:.3f}")
    print(f"  Max DD:  {result['max_dd']:.1f}%")
    print(f"  Trades:  {result['total_trades']}")
    print(f"  WR:      {result['win_rate']:.0f}%")
    print(f"  PF:      {result['profit_factor']:.2f}")
    print(f"  Vol:     {result['annual_vol']:.1f}%")
    print(f"  PSR:     {result['psr']:.1f}%")
    print(f"  Gate:    {gate}")
    print(f"  {'='*50}")

    return result


def main():
    print("=" * 60)
    print("V4 SWEET SPOT SEARCH (3 combos)")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("V4 code already uploaded from previous run (v20b_v4.py)")

    results = []
    for run in RUNS:
        r = run_backtest(run)
        if r:
            results.append(r)

    with open(RESULT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n\n{'='*90}")
    print("V4 COMPLETE LANDSCAPE: All configs ranked by Sharpe")
    print(f"{'='*90}")
    print(f"{'Config':<35} {'PT':>5} {'Risk':>6} {'Return':>8} {'CAGR':>7} {'Sharpe':>7} {'DD':>7} {'Trades':>7} {'Gate':>5}")
    print("-" * 90)
    # All V4 configs including previously known
    all_configs = [
        {"name": "V4 BASELINE", "pt": "0.35", "risk": "0.05", "ret": 190.9, "cagr": 70.9, "sharpe": 1.563, "dd": 34.1, "trades": 312, "gate": "PASS"},
    ]
    for r in results:
        all_configs.append({
            "name": r["name"], "pt": r["params"]["profit_target_pct"], "risk": r["params"]["risk_per_trade"],
            "ret": r["net_profit"], "cagr": r["cagr"], "sharpe": r["sharpe"],
            "dd": r["max_dd"], "trades": r["total_trades"], "gate": r["gate"],
        })
    all_configs.append({"name": "V4 G22", "pt": "0.40", "risk": "0.04", "ret": 67.2, "cagr": 29.4, "sharpe": 0.727, "dd": 29.4, "trades": 289, "gate": "FAIL"})

    all_configs.sort(key=lambda x: x["sharpe"], reverse=True)
    for c in all_configs:
        marker = " ***" if c["dd"] < 30 and c["gate"] == "PASS" else ""
        print(f"{c['name']:<35} {c['pt']:>5} {c['risk']:>6} {c['ret']:>+7.1f}% {c['cagr']:>6.1f}% {c['sharpe']:>7.3f} {c['dd']:>6.1f}% {c['trades']:>7} {c['gate']:>5}{marker}")

    print(f"{'='*90}")
    print("*** = DD < 30% AND passes kill gates (CAGR>=12%, Sharpe>=1.0)")
    print(f"\nResults saved to {RESULT_FILE}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
