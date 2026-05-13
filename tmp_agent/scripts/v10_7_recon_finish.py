"""
Recover IS backtest results and launch + monitor OOS backtest for v10.7-recon.
IS backtest was already launched (BT ID: 40fbea41cd346c3de4b53b04cd973990) but runner died.
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

def api(endpoint, payload, retries=5):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"    Waiting {wait}s before retry...")
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

results = {}

# ============================================================
# PHASE 1: Recover IS backtest (already launched)
# ============================================================
IS_BT_ID = "40fbea41cd346c3de4b53b04cd973990"
print("=" * 70)
print("=== PHASE 1: Recover IS backtest ===")
print("=" * 70)
print(f"  BT ID: {IS_BT_ID}")

resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": IS_BT_ID})
bt = resp.get("backtest", resp)
completed = bt.get("completed", False)
progress = bt.get("progress", 0)
prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
print(f"  Status: completed={completed}, progress={prog_str}")

if not completed:
    print("  IS backtest NOT completed yet. Polling...")
    for i in range(540):
        time.sleep(10)
        try:
            resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": IS_BT_ID})
        except Exception as e:
            print(f"    Poll error: {e}")
            continue
        bt = resp.get("backtest", resp)
        progress = bt.get("progress", 0)
        completed = bt.get("completed", False)
        prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 6 == 0:
            print(f"    [{time.strftime('%H:%M:%S')}] Poll {i+1}: {prog_str}")
        if completed:
            break

if completed:
    stats = bt.get("statistics", {})
    result = {"bt_id": IS_BT_ID}
    for k in ALL_STAT_KEYS:
        result[k] = stats.get(k, "?")
    results["v10.7-recon IS 2023-2024"] = result
    print(f"\n  --- v10.7-recon IS 2023-2024 RESULTS ---")
    for k in ALL_STAT_KEYS:
        val = result.get(k, "?")
        if val != "?":
            print(f"  {k}: {val}")
    # Save raw
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(f"{OUTPUT_DIR}/v10_7_recon_is_2023_2024_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved raw to {OUTPUT_DIR}/v10_7_recon_is_2023_2024_raw.json")
else:
    print("  ERROR: IS backtest still not completed after extended polling!")
    results["v10.7-recon IS 2023-2024"] = {"status": "INCOMPLETE", "bt_id": IS_BT_ID}

# ============================================================
# PHASE 2: Launch OOS backtest
# ============================================================
print(f"\n{'=' * 70}")
print("=== PHASE 2: Launch OOS backtest (2025-2026) ===")
print("=" * 70)

with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

code = re.sub(r'BT_START\s*=\s*\([^)]+\)', 'BT_START = (2025, 1, 1)', code)
code = re.sub(r'BT_END\s*=\s*\([^)]+\)', 'BT_END   = (2026, 4, 7)', code)

# Verify dates
start_match = re.search(r'BT_START\s*=\s*(\([^)]+\))', code)
end_match = re.search(r'BT_END\s*=\s*(\([^)]+\))', code)
print(f"  Dates: {start_match.group(1)} to {end_match.group(1)}")

# Upload
print("  Uploading...")
resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
if not resp.get("success"):
    print(f"  Upload FAILED: {resp}")
    sys.exit(1)

# Compile
print("  Compiling...")
resp = api("compile/create", {"projectId": PROJECT_ID})
compile_id = resp.get("compileId")
state = resp.get("state")
for i in range(20):
    if state == "BuildSuccess":
        break
    time.sleep(3)
    resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
    state = resp.get("state")
if state != "BuildSuccess":
    print(f"  Compile FAILED: {state}")
    sys.exit(1)
print(f"  Compile OK: {compile_id}")

# Launch
print("  Launching backtest...")
resp = api("backtests/create", {
    "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": "v10.7-recon OOS 2025-2026"
})
bt = resp.get("backtest", resp)
oos_bt_id = bt.get("backtestId")
if not oos_bt_id:
    print(f"  Launch FAILED: {resp}")
    sys.exit(1)
print(f"  Backtest ID: {oos_bt_id}")

# Poll
completed = False
for i in range(540):
    time.sleep(10)
    try:
        resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": oos_bt_id})
    except Exception as e:
        print(f"    Poll error: {e}")
        continue
    bt = resp.get("backtest", resp)
    progress = bt.get("progress", 0)
    completed = bt.get("completed", False)
    prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
    if i % 6 == 0:
        print(f"    [{time.strftime('%H:%M:%S')}] Poll {i+1}: {prog_str}")
    if completed:
        break

if completed:
    stats = bt.get("statistics", {})
    result = {"bt_id": oos_bt_id}
    for k in ALL_STAT_KEYS:
        result[k] = stats.get(k, "?")
    results["v10.7-recon OOS 2025-2026"] = result
    print(f"\n  --- v10.7-recon OOS 2025-2026 RESULTS ---")
    for k in ALL_STAT_KEYS:
        val = result.get(k, "?")
        if val != "?":
            print(f"  {k}: {val}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(f"{OUTPUT_DIR}/v10_7_recon_oos_2025_2026_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved raw to {OUTPUT_DIR}/v10_7_recon_oos_2025_2026_raw.json")
else:
    print("  ERROR: OOS backtest did not complete!")
    results["v10.7-recon OOS 2025-2026"] = {"status": "INCOMPLETE", "bt_id": oos_bt_id}

# ============================================================
# COMPARISON TABLE
# ============================================================
print(f"\n{'=' * 120}")
print("=== V10.7-RECON IS/OOS COMPARISON ===")
print("=" * 120)

# Add Full results from previous run
results["v10.7-recon Full 2023-2026"] = {
    "bt_id": "ac54f3dd04be4f7afc72991f351be336",
    "Net Profit": "20.089%", "Compounding Annual Return": "5.836%",
    "Sharpe Ratio": "-0.162", "Sortino Ratio": "-0.18",
    "Drawdown": "11.800%", "Total Orders": "167", "Win Rate": "63%",
    "Profit-Loss Ratio": "1.10", "Alpha": "-0.036", "Beta": "0.278",
    "Probabilistic Sharpe Ratio": "16.435%", "Portfolio Turnover": "0.74%",
}

header = f"{'Version':<32} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8} {'P/L':>8}"
print(header)
print("-" * 140)

# v10.13b baselines
print(f"{'v10.13b FULL (verified)':<32} {'107.0%':>10} {'24.96%':>10} {'0.822':>10} {'0.81':>10} {'18.7%':>10} {'64%':>8} {'223':>8} {'0.118':>8} {'57.5%':>8} {'2.01':>8}")
print(f"{'v10.13b IS (2023-2024)':<32} {'96.3%':>10} {'40.03%':>10} {'1.453':>10} {'1.501':>10} {'8.6%':>10} {'89%':>8} {'117':>8} {'0.166':>8} {'87.4%':>8} {'N/A':>8}")
print(f"{'v10.13b OOS (2025-2026)':<32} {'-10.8%':>10} {'-8.63%':>10} {'-0.579':>10} {'-0.606':>10} {'24.0%':>10} {'45%':>8} {'46':>8} {'-0.122':>8} {'6.15%':>8} {'N/A':>8}")
print("-" * 140)

for name in ["v10.7-recon Full 2023-2026", "v10.7-recon IS 2023-2024", "v10.7-recon OOS 2025-2026"]:
    r = results.get(name, {})
    if "bt_id" in r:
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
        print(f"{name:<32} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {alpha:>8} {psr:>8} {pl:>8}")

# Final verdict
print(f"\n--- KEY FINDINGS ---")
is_r = results.get("v10.7-recon IS 2023-2024", {})
oos_r = results.get("v10.7-recon OOS 2025-2026", {})
if "bt_id" in is_r and "bt_id" in oos_r:
    try:
        is_sharpe = float(str(is_r.get("Sharpe Ratio", "0")).replace("%", ""))
        oos_sharpe = float(str(oos_r.get("Sharpe Ratio", "0")).replace("%", ""))
        delta = oos_sharpe - is_sharpe
        print(f"  v10.7-recon IS Sharpe: {is_sharpe:.3f}")
        print(f"  v10.7-recon OOS Sharpe: {oos_sharpe:.3f}")
        print(f"  Degradation: {delta:.3f}")
        
        v13b_delta = -0.579 - 1.453
        print(f"  v10.13b degradation: {v13b_delta:.3f}")
        
        if abs(delta) < abs(v13b_delta) * 0.5:
            print(f"  VERDICT: SPY equity significantly reduces IS/OOS gap vs NVDA")
        elif oos_sharpe > 0:
            print(f"  VERDICT: SPY OOS positive -- partial improvement over NVDA")
        else:
            print(f"  VERDICT: SPY also collapses OOS -- problem is structural, not NVDA-specific")
    except Exception as e:
        print(f"  Could not compute verdict: {e}")

# Save all
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(f"{OUTPUT_DIR}/v10_7_recon_is_oos_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/v10_7_recon_is_oos_results.json")
print("\nDONE.")
