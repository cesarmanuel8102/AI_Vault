"""
Deploy V2.0b-v3 (THROTTLE) and run TWO backtests:
  1. BASELINE params (PT=0.35, SL=-0.20, R=0.05)
  2. G22 params (PT=0.40, SL=-0.20, R=0.04)
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

SOURCE_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v3.py"
RESULT_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v3_results.json"

RUNS = [
    {
        "name": "V3 BASELINE (PT=0.35 SL=-0.20 R=0.05)",
        "params": {
            "profit_target_pct": "0.35",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.05",
        },
    },
    {
        "name": "V3 G22 (PT=0.40 SL=-0.20 R=0.04)",
        "params": {
            "profit_target_pct": "0.40",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.04",
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

    # Set params
    print("  Setting parameters...")
    param_list = [{"key": k, "value": v} for k, v in params.items()]
    data = api_post("/projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    if not data.get("success"):
        print(f"  FAILED to set params: {data}")
        return None

    # Compile
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

    # Launch
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

    # Poll
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

    # Read logs
    print("  Reading logs...")
    all_logs = []
    for page in range(5):
        start = page * 200
        data = api_post("/backtests/read/log", {
            "projectId": PROJECT_ID, "backtestId": bt_id,
            "start": start, "end": start + 200, "query": " "
        })
        logs = data.get("logs", [])
        if not logs:
            break
        all_logs.extend(logs)
        if len(logs) < 200:
            break
    print(f"  Got {len(all_logs)} log entries")

    # Extract stats
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

    # V3-specific log lines
    v3_lines = []
    for log in all_logs:
        msg = log if isinstance(log, str) else str(log)
        if any(kw in msg for kw in ["TRAIL_ON", "TRAIL_SL", "THROTTLE", "trailing_activations",
                                     "FINAL REPORT", "V2.0b-v3", "risk_skips", "CONFIDENCE",
                                     "CONF_DIST", "health="]):
            v3_lines.append(msg[:300])
    result["v3_log_lines"] = v3_lines

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

    for line in v3_lines[-15:]:
        print(f"  V3: {line[:200]}")

    return result


def main():
    print("=" * 60)
    print("V2.0b-v3 THROTTLE DUAL BACKTEST")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Upload code once
    print("\nUploading v20b_v3.py as main.py...")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        code = f.read()
    data = api_post("/files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    if not data.get("success"):
        data = api_post("/files/create", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    print(f"  Upload: {'OK' if data.get('success') else 'FAILED'}")
    if not data.get("success"):
        return

    results = []
    for run in RUNS:
        r = run_backtest(run)
        if r:
            results.append(r)

    # Save all results
    with open(RESULT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    # Final comparison
    print(f"\n\n{'='*70}")
    print("FINAL COMPARISON: V3 THROTTLE vs Original Champions")
    print(f"{'='*70}")
    print(f"{'Config':<40} {'Return':>8} {'CAGR':>7} {'Sharpe':>7} {'DD':>7} {'Trades':>7} {'WR':>5} {'Gate':>5}")
    print("-" * 82)
    # Original references
    print(f"{'ORIG BASELINE (PT35/SL20/R05)':<40} {'175.7%':>8} {'66.4%':>7} {'1.337':>7} {'44.3%':>7} {'318':>7} {'48%':>5} {'PASS':>5}")
    print(f"{'ORIG G22 (PT40/SL20/R04)':<40} {'130.6%':>8} {'52.1%':>7} {'1.165':>7} {'31.0%':>7} {'310':>7} {'46%':>5} {'PASS':>5}")
    print("-" * 82)
    # V2 references (FAILED)
    print(f"{'V2 BASELINE (HALT) — FAILED':<40} {'-29.7%':>8} {'---':>7} {'-0.898':>7} {'34.9%':>7} {'110':>7} {'---':>5} {'FAIL':>5}")
    print(f"{'V2 G22 (HALT) — FAILED':<40} {'0.0%':>8} {'---':>7} {'0.000':>7} {'0.0%':>7} {'0':>7} {'---':>5} {'FAIL':>5}")
    print("-" * 82)
    for r in results:
        short = r["name"]
        print(f"{short:<40} {r['net_profit']:>+7.1f}% {r['cagr']:>6.1f}% {r['sharpe']:>7.3f} {r['max_dd']:>6.1f}% {r['total_trades']:>7} {r['win_rate']:>4.0f}% {r['gate']:>5}")
    print(f"{'='*82}")
    print(f"\nResults saved to {RESULT_FILE}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
