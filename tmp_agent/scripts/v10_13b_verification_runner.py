"""
V10.13b Champion Verification Runner
=====================================
Uploads v10.13b code to QC project 29490680, modifying dates for each period,
then compiles and runs 3 backtests sequentially:
  1. Full:  2023-01-01 to 2026-04-07
  2. IS:    2023-01-01 to 2024-12-31
  3. OOS:   2025-01-01 to 2026-04-07

Goal: Verify claimed Sharpe 0.90 and check IS/OOS degradation.
"""
import hashlib, base64, time, json, requests, sys, re

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/state/qc_backups/v10_13b_champion_reconstructed.py"
OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies/brain_v10"

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

# Load base code
with open(CODE_PATH, "r", encoding="utf-8") as f:
    BASE_CODE = f.read()

print(f"Loaded v10.13b: {len(BASE_CODE)} chars, {BASE_CODE.count(chr(10))} lines")

# Define test periods
TESTS = [
    {
        "name": "v10.13b FULL 2023-2026",
        "bt_start": "(2023, 1, 1)",
        "bt_end": "(2026, 4, 7)",
    },
    {
        "name": "v10.13b IS 2023-2024",
        "bt_start": "(2023, 1, 1)",
        "bt_end": "(2024, 12, 31)",
    },
    {
        "name": "v10.13b OOS 2025-2026",
        "bt_start": "(2025, 1, 1)",
        "bt_end": "(2026, 4, 7)",
    },
]

def modify_dates(code, bt_start_str, bt_end_str):
    """Replace BT_START and BT_END tuples in the code."""
    code = re.sub(r'BT_START\s*=\s*\([^)]+\)', f'BT_START = {bt_start_str}', code)
    code = re.sub(r'BT_END\s*=\s*\([^)]+\)', f'BT_END   = {bt_end_str}', code)
    return code

def upload_and_compile(code, label):
    """Upload code to QC and compile. Returns compile_id or None."""
    print(f"  Uploading {label}...")
    resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    if not resp.get("success"):
        print(f"  Upload failed: {resp}")
        return None

    # Clear any parameters that might interfere
    # (v10.13b doesn't use QC params but clear just in case)

    print(f"  Compiling...")
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
        if state == "BuildError":
            print(f"  COMPILE FAILED: {resp.get('errors', [])}")
            return None

    if state != "BuildSuccess":
        print(f"  Compile did not succeed: {state}")
        return None

    print(f"  Compile SUCCESS: {compile_id}")
    return compile_id

def run_backtest(compile_id, name):
    """Launch backtest and poll until complete. Returns stats dict or None."""
    print(f"  Launching backtest: {name}")
    resp = api("backtests/create", {
        "projectId": PROJECT_ID,
        "compileId": compile_id,
        "backtestName": name,
    })
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    print(f"  Backtest ID: {bt_id}")

    if not bt_id:
        print(f"  FAILED to launch: {resp}")
        return None

    # Poll - v10.13b can take a while with options data (up to 20 min)
    completed = False
    for i in range(180):  # 30 minutes max
        time.sleep(10)
        resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = resp.get("backtest", resp)
        progress = bt.get("progress", 0)
        completed = bt.get("completed", False)
        prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 6 == 0:  # Print every minute
            print(f"    [{time.strftime('%H:%M:%S')}] Poll {i+1}: {prog_str} completed={completed}")
        if completed:
            break

    if not completed:
        print(f"  WARNING: {name} did not complete in 30 minutes")
        return {"status": "TIMEOUT", "bt_id": bt_id}

    # Extract all stats
    stats = bt.get("statistics", {})
    result = {
        "bt_id": bt_id,
        "net_profit": stats.get("Net Profit", "?"),
        "cagr": stats.get("Compounding Annual Return", "?"),
        "sharpe": stats.get("Sharpe Ratio", "?"),
        "sortino": stats.get("Sortino Ratio", "?"),
        "drawdown": stats.get("Drawdown", "?"),
        "total_orders": stats.get("Total Orders", "?"),
        "win_rate": stats.get("Win Rate", "?"),
        "pl_ratio": stats.get("Profit-Loss Ratio", "?"),
        "expectancy": stats.get("Expectancy", "?"),
        "end_equity": stats.get("Equity", "?"),
        "alpha": stats.get("Alpha", "?"),
        "beta": stats.get("Beta", "?"),
        "treynor": stats.get("Treynor Ratio", "?"),
        "information": stats.get("Information Ratio", "?"),
        "annual_std": stats.get("Annual Standard Deviation", "?"),
        "annual_var": stats.get("Annual Variance", "?"),
        "tracking_error": stats.get("Tracking Error", "?"),
        "total_fees": stats.get("Total Fees", "?"),
        "fitness": stats.get("Fitness Score", "?"),
        "kelly": stats.get("Kelly Criterion Estimate", "?"),
        "capacity": stats.get("Estimated Strategy Capacity", "?"),
        "lowest_capacity": stats.get("Lowest Capacity Asset", "?"),
        "psr": stats.get("Probabilistic Sharpe Ratio", "?"),
        "portfolio_turnover": stats.get("Portfolio Turnover", "?"),
        "return_over_max_dd": stats.get("Return Over Maximum Drawdown", "?"),
        "loss_rate": stats.get("Loss Rate", "?"),
        "avg_win": stats.get("Average Win", "?"),
        "avg_loss": stats.get("Average Loss", "?"),
    }

    # Save raw response
    try:
        import os
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe_name = name.replace(" ", "_").lower()
        with open(f"{OUTPUT_DIR}/{safe_name}_raw.json", "w") as f:
            json.dump(resp, f, indent=2, default=str)
    except Exception as e:
        print(f"  Warning: Could not save raw: {e}")

    return result

def main():
    results = {}

    for test in TESTS:
        name = test["name"]
        print(f"\n{'='*70}")
        print(f"=== {name} ===")
        print(f"{'='*70}")

        # Modify dates in code
        code = modify_dates(BASE_CODE, test["bt_start"], test["bt_end"])

        # Verify dates were set
        start_match = re.search(r'BT_START\s*=\s*(\([^)]+\))', code)
        end_match = re.search(r'BT_END\s*=\s*(\([^)]+\))', code)
        print(f"  Dates: start={start_match.group(1) if start_match else '?'}, end={end_match.group(1) if end_match else '?'}")

        # Upload and compile
        compile_id = upload_and_compile(code, name)
        if not compile_id:
            results[name] = {"status": "COMPILE_FAILED"}
            continue

        # Run backtest
        result = run_backtest(compile_id, name)
        results[name] = result

        if result and "bt_id" in result:
            print(f"\n  --- {name} RESULTS ---")
            for k, v in result.items():
                if k != "bt_id":
                    print(f"  {k}: {v}")

    # Final comparison table
    print(f"\n{'='*70}")
    print("=== V10.13b VERIFICATION — COMPARISON TABLE ===")
    print(f"{'='*70}")
    print(f"{'Period':<25} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8}")
    print("-" * 107)

    # Claimed baseline
    print(f"{'CLAIMED (docstring)':<25} {'116%':>10} {'26.5%':>10} {'0.90':>10} {'0.91':>10} {'16.6%':>10} {'69%':>8} {'?':>8} {'0.124':>8} {'?':>8}")
    print("-" * 107)

    for name, r in results.items():
        if isinstance(r, dict) and "bt_id" in r:
            label = name.replace("v10.13b ", "")
            print(f"{label:<25} {str(r.get('net_profit','?')):>10} {str(r.get('cagr','?')):>10} {str(r.get('sharpe','?')):>10} {str(r.get('sortino','?')):>10} {str(r.get('drawdown','?')):>10} {str(r.get('win_rate','?')):>8} {str(r.get('total_orders','?')):>8} {str(r.get('alpha','?')):>8} {str(r.get('psr','?')):>8}")

    # Save all results
    try:
        import os
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(f"{OUTPUT_DIR}/v10_13b_verification_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {OUTPUT_DIR}/v10_13b_verification_results.json")
    except Exception as e:
        print(f"\nWarning: Could not save results: {e}")

    print(f"\n{'='*70}")
    print("ALL VERIFICATION TESTS COMPLETE")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
