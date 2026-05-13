"""
v10.7-recon Runner: Upload, compile, run Full + IS + OOS backtests
SPY equity instead of NVDA -- test NVDA concentration hypothesis
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

with open(CODE_PATH, "r", encoding="utf-8") as f:
    BASE_CODE = f.read()

TESTS = [
    {"name": "v10.7-recon Full 2023-2026",  "bt_start": "(2023, 1, 1)", "bt_end": "(2026, 3, 23)"},
    {"name": "v10.7-recon IS 2023-2024",    "bt_start": "(2023, 1, 1)", "bt_end": "(2024, 12, 31)"},
    {"name": "v10.7-recon OOS 2025-2026",   "bt_start": "(2025, 1, 1)", "bt_end": "(2026, 4, 7)"},
]

def modify_dates(code, bt_start_str, bt_end_str):
    code = re.sub(r'BT_START\s*=\s*\([^)]+\)', f'BT_START = {bt_start_str}', code)
    code = re.sub(r'BT_END\s*=\s*\([^)]+\)', f'BT_END   = {bt_end_str}', code)
    return code

ALL_STAT_KEYS = [
    "Net Profit", "Compounding Annual Return", "Sharpe Ratio", "Sortino Ratio",
    "Drawdown", "Total Orders", "Win Rate", "Profit-Loss Ratio", "Expectancy",
    "Alpha", "Beta", "Treynor Ratio", "Information Ratio",
    "Annual Standard Deviation", "Annual Variance", "Tracking Error",
    "Total Fees", "Fitness Score", "Kelly Criterion Estimate",
    "Estimated Strategy Capacity", "Lowest Capacity Asset",
    "Probabilistic Sharpe Ratio", "Portfolio Turnover",
    "Return Over Maximum Drawdown", "Loss Rate", "Average Win", "Average Loss",
    "Drawdown Recovery", "End Equity", "Start Equity"
]

results = {}

for test in TESTS:
    name = test["name"]
    print(f"\n{'='*70}")
    print(f"=== {name} ===")
    print(f"{'='*70}")

    code = modify_dates(BASE_CODE, test["bt_start"], test["bt_end"])
    start_match = re.search(r'BT_START\s*=\s*(\([^)]+\))', code)
    end_match = re.search(r'BT_END\s*=\s*(\([^)]+\))', code)
    print(f"  Dates: {start_match.group(1)} to {end_match.group(1)}")

    # Upload
    print(f"  Uploading...")
    resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    if not resp.get("success"):
        print(f"  Upload FAILED: {resp}")
        results[name] = {"status": "UPLOAD_FAILED"}
        continue

    # Compile
    print(f"  Compiling...")
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
        print(f"  Response: {json.dumps(resp, indent=2)[:500]}")
        results[name] = {"status": "COMPILE_FAILED"}
        continue
    print(f"  Compile OK: {compile_id}")

    # Launch backtest
    print(f"  Launching backtest...")
    resp = api("backtests/create", {
        "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name
    })
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    if not bt_id:
        print(f"  Launch FAILED: {resp}")
        results[name] = {"status": "LAUNCH_FAILED", "error": str(resp.get("errors", ""))}
        continue
    print(f"  Backtest ID: {bt_id}")

    # Poll (90 min max for safety)
    completed = False
    for i in range(540):
        time.sleep(10)
        try:
            resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
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

    if not completed:
        print(f"  TIMEOUT after 90 min")
        results[name] = {"status": "TIMEOUT", "bt_id": bt_id}
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
    with open(f"{OUTPUT_DIR}/{safe_name}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved raw to {OUTPUT_DIR}/{safe_name}_raw.json")

# ============================================================
# COMPARISON TABLE
# ============================================================
print(f"\n{'='*120}")
print("=== V10.7-RECON (SPY) vs V10.13b (NVDA) COMPARISON ===")
print(f"{'='*120}")

header = f"{'Version':<28} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8} {'P/L':>8}"
print(header)
print("-" * 130)

# V10.13b baselines
print(f"{'v10.13b FULL (verified)':<28} {'107.0%':>10} {'24.96%':>10} {'0.822':>10} {'0.81':>10} {'18.7%':>10} {'64%':>8} {'223':>8} {'0.118':>8} {'57.5%':>8} {'2.17':>8}")
print(f"{'v10.13b IS (2023-2024)':<28} {'99.11%':>10} {'40.03%':>10} {'1.453':>10} {'1.578':>10} {'8.6%':>10} {'89%':>8} {'113':>8} {'0.25':>8} {'77.3%':>8} {'4.78':>8}")
print(f"{'v10.13b OOS (2025-2026)':<28} {'-10.1%':>10} {'-8.63%':>10} {'-0.579':>10} {'-0.61':>10} {'24.0%':>10} {'45%':>8} {'110':>8} {'-0.22':>8} {'27.0%':>8} {'0.95':>8}")
print("-" * 130)

for name, r in results.items():
    if "bt_id" in r:
        label = name
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
        print(f"{label:<28} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {alpha:>8} {psr:>8} {pl:>8}")

# IS vs OOS degradation
is_name = "v10.7-recon IS 2023-2024"
oos_name = "v10.7-recon OOS 2025-2026"
if is_name in results and oos_name in results:
    is_r = results[is_name]
    oos_r = results[oos_name]
    if "bt_id" in is_r and "bt_id" in oos_r:
        print(f"\n--- IS vs OOS DEGRADATION ANALYSIS ---")
        for k in ["Sharpe Ratio", "Compounding Annual Return", "Sortino Ratio", "Drawdown", "Win Rate", "Total Orders"]:
            is_v = is_r.get(k, "?")
            oos_v = oos_r.get(k, "?")
            print(f"  {k}: IS={is_v}  OOS={oos_v}")

print(f"\n--- KEY QUESTION: Does SPY equity hold in OOS? ---")
if oos_name in results and "bt_id" in results[oos_name]:
    oos_sharpe_raw = results[oos_name].get("Sharpe Ratio", "?")
    try:
        oos_sharpe = float(str(oos_sharpe_raw).replace("%", ""))
        if oos_sharpe > 0.5:
            print(f"  VERDICT: OOS Sharpe {oos_sharpe:.3f} > 0.5 --> SPY HOLDS, NVDA was the problem!")
        elif oos_sharpe > 0:
            print(f"  VERDICT: OOS Sharpe {oos_sharpe:.3f} > 0 (positive but weak) --> Partial improvement")
        else:
            print(f"  VERDICT: OOS Sharpe {oos_sharpe:.3f} <= 0 --> SPY also collapses, problem is deeper")
    except:
        print(f"  Cannot parse OOS Sharpe: {oos_sharpe_raw}")

# Save all results
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(f"{OUTPUT_DIR}/v10_7_recon_all_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/v10_7_recon_all_results.json")
