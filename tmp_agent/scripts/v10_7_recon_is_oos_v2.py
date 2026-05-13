"""
Launch IS + OOS backtests for v10.7-recon (fresh launches).
Previous IS BT stuck at progress=0. Starting clean.
"""
import hashlib, base64, time, json, requests, re, os, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/state/qc_backups/v10_7_recon.py"
OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies/brain_v10"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api(endpoint, payload, retries=5, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"    Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

ALL_STAT_KEYS = [
    "Net Profit", "Compounding Annual Return", "Sharpe Ratio", "Sortino Ratio",
    "Drawdown", "Total Orders", "Win Rate", "Profit-Loss Ratio", "Expectancy",
    "Alpha", "Beta", "Treynor Ratio", "Information Ratio",
    "Annual Standard Deviation", "Annual Variance", "Tracking Error",
    "Total Fees", "Estimated Strategy Capacity", "Lowest Capacity Asset",
    "Probabilistic Sharpe Ratio", "Portfolio Turnover",
    "Loss Rate", "Average Win", "Average Loss",
    "Drawdown Recovery", "End Equity", "Start Equity"
]

with open(CODE_PATH, "r", encoding="utf-8") as f:
    BASE_CODE = f.read()

TESTS = [
    {"name": "v10.7-recon IS 2023-2024",  "bt_start": "(2023, 1, 1)", "bt_end": "(2024, 12, 31)"},
    {"name": "v10.7-recon OOS 2025-2026", "bt_start": "(2025, 1, 1)", "bt_end": "(2026, 4, 7)"},
]

results = {}

for test in TESTS:
    name = test["name"]
    print(f"\n{'=' * 70}")
    print(f"=== {name} ===")
    print(f"{'=' * 70}")

    code = re.sub(r'BT_START\s*=\s*\([^)]+\)', f'BT_START = {test["bt_start"]}', BASE_CODE)
    code = re.sub(r'BT_END\s*=\s*\([^)]+\)', f'BT_END   = {test["bt_end"]}', code)

    start_m = re.search(r'BT_START\s*=\s*(\([^)]+\))', code)
    end_m = re.search(r'BT_END\s*=\s*(\([^)]+\))', code)
    print(f"  Dates: {start_m.group(1)} to {end_m.group(1)}")

    # Upload
    print("  Uploading...")
    resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    if not resp.get("success"):
        print(f"  Upload FAILED: {resp}")
        results[name] = {"status": "UPLOAD_FAILED"}
        continue

    # Compile
    print("  Compiling...")
    resp = api("compile/create", {"projectId": PROJECT_ID})
    compile_id = resp.get("compileId")
    state = resp.get("state")
    for ci in range(20):
        if state == "BuildSuccess":
            break
        time.sleep(3)
        try:
            resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id}, retries=3)
            state = resp.get("state")
        except:
            pass
    if state != "BuildSuccess":
        print(f"  Compile FAILED: {state}")
        results[name] = {"status": "COMPILE_FAILED"}
        continue
    print(f"  Compile OK: {compile_id}")

    # Launch
    print("  Launching backtest...")
    resp = api("backtests/create", {
        "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name + " v2"
    })
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    if not bt_id:
        print(f"  Launch FAILED: {resp}")
        results[name] = {"status": "LAUNCH_FAILED"}
        continue
    print(f"  Backtest ID: {bt_id}")

    # Poll with resilience (90 min max)
    completed = False
    consecutive_errors = 0
    for i in range(540):
        time.sleep(10)
        try:
            resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id}, retries=3, timeout=45)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(f"    [{time.strftime('%H:%M:%S')}] Poll error #{consecutive_errors}: {e}")
            if consecutive_errors > 20:
                print("  Too many consecutive errors, aborting poll")
                break
            continue
        bt = resp.get("backtest", resp)
        progress = bt.get("progress", 0)
        completed = bt.get("completed", False)
        prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 6 == 0:
            print(f"    [{time.strftime('%H:%M:%S')}] Poll {i+1}: {prog_str}")
        if completed:
            break

    if not completed:
        print(f"  TIMEOUT/ERROR - backtest did not complete")
        results[name] = {"status": "INCOMPLETE", "bt_id": bt_id}
        continue

    stats = bt.get("statistics", {})
    result = {"bt_id": bt_id}
    for k in ALL_STAT_KEYS:
        result[k] = stats.get(k, "?")
    results[name] = result

    print(f"\n  --- {name} RESULTS ---")
    for k in ALL_STAT_KEYS:
        val = result.get(k, "?")
        if val != "?":
            print(f"  {k}: {val}")

    # Save raw
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_name = name.replace(" ", "_").replace("-", "_").lower()
    with open(f"{OUTPUT_DIR}/{safe_name}_v2_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved raw to {OUTPUT_DIR}/{safe_name}_v2_raw.json")

# ============================================================
# COMPARISON TABLE
# ============================================================
print(f"\n{'=' * 140}")
print("=== V10.7-RECON FULL + IS + OOS COMPARISON ===")
print("=" * 140)

header = f"{'Version':<36} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8} {'P/L':>8}"
print(header)
print("-" * 150)

# v10.13b baselines
print(f"{'v10.13b FULL (verified)':<36} {'107.0%':>10} {'24.96%':>10} {'0.822':>10} {'0.81':>10} {'18.7%':>10} {'64%':>8} {'223':>8} {'0.118':>8} {'57.5%':>8} {'2.01':>8}")
print(f"{'v10.13b IS (2023-2024)':<36} {'96.3%':>10} {'40.03%':>10} {'1.453':>10} {'1.501':>10} {'8.6%':>10} {'89%':>8} {'117':>8} {'0.166':>8} {'87.4%':>8} {'N/A':>8}")
print(f"{'v10.13b OOS (2025-2026)':<36} {'-10.8%':>10} {'-8.63%':>10} {'-0.579':>10} {'-0.606':>10} {'24.0%':>10} {'45%':>8} {'46':>8} {'-0.122':>8} {'6.15%':>8} {'N/A':>8}")
print("-" * 150)

# v10.7-recon Full (hardcoded from previous run)
print(f"{'v10.7-recon FULL (2023-2026)':<36} {'20.1%':>10} {'5.84%':>10} {'-0.162':>10} {'-0.18':>10} {'11.8%':>10} {'63%':>8} {'167':>8} {'-0.036':>8} {'16.4%':>8} {'1.10':>8}")

for name in ["v10.7-recon IS 2023-2024", "v10.7-recon OOS 2025-2026"]:
    r = results.get(name, {})
    if "bt_id" in r and r.get("status") != "INCOMPLETE":
        net = str(r.get("Net Profit", "?"))
        cagr = str(r.get("Compounding Annual Return", "?"))
        sharpe = str(r.get("Sharpe Ratio", "?"))
        sortino = str(r.get("Sortino Ratio", "?"))
        dd = str(r.get("Drawdown", "?"))
        wr = str(r.get("Win Rate", "?"))
        orders = str(r.get("Total Orders", "?"))
        alpha = str(r.get("Alpha", "?"))
        psr = str(r.get("Probabilistic Sharpe Ratio", "?"))
        pl = str(r.get("Profit-Loss Ratio", "?"))
        print(f"{name:<36} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {alpha:>8} {psr:>8} {pl:>8}")
    else:
        status = r.get("status", "NOT_RUN")
        print(f"{name:<36} {'--- ' + status + ' ---'}")

# Verdict
print(f"\n--- VERDICT ---")
is_r = results.get("v10.7-recon IS 2023-2024", {})
oos_r = results.get("v10.7-recon OOS 2025-2026", {})
if "bt_id" in is_r and is_r.get("status") != "INCOMPLETE" and "bt_id" in oos_r and oos_r.get("status") != "INCOMPLETE":
    try:
        is_sharpe = float(str(is_r.get("Sharpe Ratio", "0")).replace("%", ""))
        oos_sharpe = float(str(oos_r.get("Sharpe Ratio", "0")).replace("%", ""))
        print(f"  IS Sharpe: {is_sharpe:.3f}")
        print(f"  OOS Sharpe: {oos_sharpe:.3f}")
        print(f"  Delta: {oos_sharpe - is_sharpe:.3f}")
        print(f"  v10.13b IS->OOS delta was: {-0.579 - 1.453:.3f}")
        if oos_sharpe > 0:
            print(f"  SPY partially saves OOS (positive Sharpe)")
        else:
            print(f"  SPY also negative OOS -- ENTIRE v10.x framework has structural issues")
    except Exception as e:
        print(f"  Cannot compute: {e}")
else:
    print("  Not all backtests completed. Check manually.")

# Save all
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(f"{OUTPUT_DIR}/v10_7_recon_is_oos_v2_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/v10_7_recon_is_oos_v2_results.json")
print("\nDONE.")
