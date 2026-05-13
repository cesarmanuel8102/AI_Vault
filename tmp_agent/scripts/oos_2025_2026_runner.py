"""
FASE 1: OOS puro 2025-2026 for V4-B vs V5a
Runs 2 backtests sequentially:
  1. V4-B baseline (no fixes) = V5 code with all fixes OFF
  2. V5a (FIX3-only) = V5 code with enable_fix3=1
Period: 2025-01 to 2026-04
"""
import hashlib, base64, time, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api(endpoint, payload):
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                raise

# V5 code is already uploaded on the project from ablation tests.
# We just need to set params and run.

TESTS = [
    {
        "name": "V4-B OOS 2025-2026",
        "params": {
            "enable_fix2": "0", "enable_fix3": "0", "enable_fix4": "0",
            "trail_act": "0.20", "trail_pct": "0.50",
            "profit_target_pct": "0.35",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.04",
            "dte_min": "14",
            "dte_max": "30",
            "start_year": "2025",
            "end_year": "2026",
            "end_month": "4",
        }
    },
    {
        "name": "V5a OOS 2025-2026",
        "params": {
            "enable_fix2": "0", "enable_fix3": "1", "enable_fix4": "0",
            "trail_act": "0.20", "trail_pct": "0.50",
            "profit_target_pct": "0.35",
            "stop_loss_pct": "-0.20",
            "risk_per_trade": "0.04",
            "dte_min": "14",
            "dte_max": "30",
            "start_year": "2025",
            "end_year": "2026",
            "end_month": "4",
        }
    },
]

def run_backtest(test):
    name = test["name"]
    print(f"\n{'='*60}")
    print(f"=== {name} ===")
    print(f"{'='*60}")

    # Set params
    param_list = [{"key": k, "value": v} for k, v in test["params"].items()]
    resp = api("projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    print(f"  Params set: success={resp.get('success')}")

    # Verify
    resp = api("projects/read", {"projectId": PROJECT_ID})
    if resp.get("success"):
        proj = resp["projects"][0] if isinstance(resp["projects"], list) else resp["projects"]
        p = {x["key"]: x["value"] for x in proj.get("parameters", [])}
        print(f"  Verified: fix2={p.get('enable_fix2')}, fix3={p.get('enable_fix3')}, fix4={p.get('enable_fix4')}")
        print(f"  start_year={p.get('start_year')}, end_year={p.get('end_year')}, end_month={p.get('end_month')}")

    # Compile
    resp = api("compile/create", {"projectId": PROJECT_ID})
    compile_id = resp.get("compileId")
    state = resp.get("state")
    print(f"  Compile: id={compile_id} state={state}")

    for i in range(20):
        if state == "BuildSuccess":
            break
        time.sleep(3)
        resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
        state = resp.get("state")

    if state != "BuildSuccess":
        print(f"  COMPILE FAILED: {state}")
        return None

    # Launch backtest
    resp = api("backtests/create", {
        "projectId": PROJECT_ID,
        "compileId": compile_id,
        "backtestName": name,
    })
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    print(f"  Backtest launched: {bt_id}")

    if not bt_id:
        print(f"  FAILED to launch: {resp}")
        return None

    # Poll
    for i in range(120):
        time.sleep(10)
        resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = resp.get("backtest", resp)
        progress = bt.get("progress", 0)
        completed = bt.get("completed", False)
        prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 6 == 0:
            print(f"  Poll {i+1}: {prog_str}")
        if completed:
            break

    if not completed:
        print(f"  WARNING: {name} did not complete in time")
        return {"status": "TIMEOUT", "bt_id": bt_id}

    stats = bt.get("statistics", {})
    print(f"\n  --- {name} RESULTS ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Save raw
    safe_name = name.replace(' ', '_').lower()
    with open(f"C:/AI_VAULT/tmp_agent/strategies/yoel_options/{safe_name}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)

    return {"bt_id": bt_id, "stats": stats}

def main():
    results = {}
    for test in TESTS:
        result = run_backtest(test)
        results[test["name"]] = result

    # Print comparison
    print(f"\n{'='*60}")
    print("=== OOS 2025-2026 COMPARISON ===")
    print(f"{'='*60}")

    # All QC metrics
    metrics = [
        "Total Orders", "Average Win", "Average Loss",
        "Compounding Annual Return", "Drawdown", "Expectancy",
        "Start Equity", "End Equity", "Net Profit",
        "Sharpe Ratio", "Sortino Ratio", "Probabilistic Sharpe Ratio",
        "Loss Rate", "Win Rate", "Profit-Loss Ratio",
        "Alpha", "Beta", "Annual Standard Deviation", "Annual Variance",
        "Information Ratio", "Tracking Error", "Treynor Ratio",
        "Total Fees", "Estimated Strategy Capacity",
        "Lowest Capacity Asset", "Portfolio Turnover", "Drawdown Recovery",
    ]

    header = f"{'Metric':<30}"
    for name in results:
        header += f" {name:>22}"
    print(header)
    print("-" * len(header))

    for m in metrics:
        row = f"{m:<30}"
        for name, r in results.items():
            if r and "stats" in r:
                val = r["stats"].get(m, "N/A")
            else:
                val = "FAILED"
            row += f" {str(val):>22}"
        print(row)

    # Save results
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/oos_2025_2026_comparison.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n=== DONE ===")

if __name__ == "__main__":
    main()
