"""
G15 Runner: V2.0b champion with PT=0.35, SL=-0.20, Risk=0.06
Run IS (2023-2024) + OOS (2025-2026) + Full (2023-2026)
Code: v20b_param_loop.py UNMODIFIED
"""
import hashlib, base64, time, json, requests, os, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_param_loop.py"
OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies/yoel_options"

def auth_headers():
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api(endpoint, payload, retries=5, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
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

# G15 params
G15_PARAMS = [
    {"key": "profit_target_pct", "value": "0.35"},
    {"key": "stop_loss_pct", "value": "-0.20"},
    {"key": "risk_per_trade", "value": "0.06"},
    {"key": "dte_min", "value": "14"},
    {"key": "dte_max", "value": "30"},
]

TESTS = [
    {"name": "G15 OOS 2025-2026",  "start_year": "2025", "end_year": "2026", "end_month": "4"},
    {"name": "G15 IS 2023-2024",   "start_year": "2023", "end_year": "2024", "end_month": "12"},
    {"name": "G15 Full 2023-2026", "start_year": "2023", "end_year": "2026", "end_month": "4"},
]

# Upload code once
with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

print("Uploading v20b_param_loop.py...")
resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
if not resp.get("success"):
    print(f"Upload FAILED: {resp}")
    sys.exit(1)
print("Upload OK")

results = {}

for test in TESTS:
    name = test["name"]
    print(f"\n{'=' * 70}")
    print(f"=== {name} ===")
    print(f"{'=' * 70}")

    # Set parameters
    params = G15_PARAMS + [
        {"key": "start_year", "value": test["start_year"]},
        {"key": "end_year", "value": test["end_year"]},
        {"key": "end_month", "value": test["end_month"]},
    ]
    print(f"  Params: PT=0.35 SL=-0.20 R=0.06 period={test['start_year']}-{test['end_year']}")
    resp = api("projects/update", {"projectId": PROJECT_ID, "parameters": params})
    if not resp.get("success"):
        print(f"  Params FAILED: {resp}")
        results[name] = {"status": "PARAMS_FAILED"}
        continue
    print("  Params set OK")

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
        "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name
    })
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    if not bt_id:
        print(f"  Launch FAILED: {resp}")
        results[name] = {"status": "LAUNCH_FAILED"}
        continue
    print(f"  Backtest ID: {bt_id}")

    # Poll (90 min max)
    completed = False
    consec_err = 0
    for i in range(540):
        time.sleep(10)
        try:
            resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id}, retries=3, timeout=45)
            consec_err = 0
        except Exception as e:
            consec_err += 1
            print(f"    [{time.strftime('%H:%M:%S')}] Poll error #{consec_err}: {e}")
            if consec_err > 30:
                print("  Too many errors, aborting")
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
        print(f"  TIMEOUT/ERROR")
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
    safe = name.replace(" ", "_").lower()
    with open(f"{OUTPUT_DIR}/{safe}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved: {OUTPUT_DIR}/{safe}_raw.json")

# ============================================================
# COMPARISON TABLE
# ============================================================
print(f"\n{'=' * 150}")
print("=== G15 (PT=0.35 SL=-0.20 R=0.06) vs V4-B vs v10.13b ===")
print("=" * 150)

hdr = f"{'Version':<36} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8} {'P/L':>8}"
print(hdr)
print("-" * 150)

# Baselines
print(f"{'v10.13b IS (2023-2024)':<36} {'96.3%':>10} {'40.03%':>10} {'1.453':>10} {'1.501':>10} {'8.6%':>10} {'89%':>8} {'117':>8} {'0.166':>8} {'87.4%':>8} {'N/A':>8}")
print(f"{'v10.13b OOS (2025-2026)':<36} {'-10.8%':>10} {'-8.63%':>10} {'-0.579':>10} {'-0.606':>10} {'24.0%':>10} {'45%':>8} {'46':>8} {'-0.122':>8} {'6.15%':>8} {'N/A':>8}")
print(f"{'v10.13b FULL':<36} {'107.0%':>10} {'24.96%':>10} {'0.822':>10} {'0.81':>10} {'18.7%':>10} {'64%':>8} {'223':>8} {'0.118':>8} {'57.5%':>8} {'2.01':>8}")
print("-" * 150)
print(f"{'V4-B IS (2023-2024)':<36} {'136.4%':>10} {'54.0%':>10} {'1.391':>10} {'1.447':>10} {'29.2%':>10} {'48%':>8} {'309':>8} {'N/A':>8} {'74.5%':>8} {'1.87':>8}")
print(f"{'V4-B OOS (2025-2026)':<36} {'1.1%':>10} {'1.1%':>10} {'-0.13':>10} {'N/A':>10} {'16.5%':>10} {'49%':>8} {'145':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8}")
print(f"{'V4-B FULL':<36} {'22.1%':>10} {'22.1%':>10} {'0.53':>10} {'N/A':>10} {'37.7%':>10} {'46%':>8} {'491':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8}")
print("-" * 150)

for name in ["G15 IS 2023-2024", "G15 OOS 2025-2026", "G15 Full 2023-2026"]:
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

# IS/OOS verdict
print(f"\n--- G15 IS vs OOS VERDICT ---")
is_r = results.get("G15 IS 2023-2024", {})
oos_r = results.get("G15 OOS 2025-2026", {})
if "bt_id" in is_r and is_r.get("status") != "INCOMPLETE" and "bt_id" in oos_r and oos_r.get("status") != "INCOMPLETE":
    try:
        is_s = float(str(is_r.get("Sharpe Ratio", "0")).replace("%", ""))
        oos_s = float(str(oos_r.get("Sharpe Ratio", "0")).replace("%", ""))
        print(f"  G15 IS Sharpe:  {is_s:.3f}")
        print(f"  G15 OOS Sharpe: {oos_s:.3f}")
        print(f"  Degradation:    {oos_s - is_s:.3f}")
        print(f"  V4-B delta:     {-0.13 - 1.391:.3f}")
        print(f"  v10.13b delta:  {-0.579 - 1.453:.3f}")
        if oos_s > 0.5:
            print(f"  *** G15 OOS PASSES RESEARCH GATE (>= 0.6 needed for deploy) ***")
        elif oos_s > 0:
            print(f"  G15 OOS positive but below gates")
        else:
            print(f"  G15 OOS negative -- same collapse pattern")
    except Exception as e:
        print(f"  Error: {e}")

# Save all
with open(f"{OUTPUT_DIR}/g15_is_oos_full_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/g15_is_oos_full_results.json")
print("\nDONE.")
