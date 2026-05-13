"""
G16 Runner: V2.0b-G16 = G15 + 4 Structural Fixes
PT=0.35, SL=-0.20, Risk=0.06, DTE=14-30
FIX1: Anti-same-day SL | FIX2: Soft trail | FIX3: QQQ filter | FIX4: Streak reduction
Run IS (2023-2024) + OOS (2025-2026) + Full (2023-2026)
"""
import hashlib, base64, time, json, requests, os, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_g16.py"
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

# G16 params = same as G15
G16_PARAMS = [
    {"key": "profit_target_pct", "value": "0.35"},
    {"key": "stop_loss_pct", "value": "-0.20"},
    {"key": "risk_per_trade", "value": "0.06"},
    {"key": "dte_min", "value": "14"},
    {"key": "dte_max", "value": "30"},
]

TESTS = [
    {"name": "G16 IS 2023-2024",   "start_year": "2023", "end_year": "2024", "end_month": "12"},
    {"name": "G16 OOS 2025-2026",  "start_year": "2025", "end_year": "2026", "end_month": "4"},
    {"name": "G16 Full 2023-2026", "start_year": "2023", "end_year": "2026", "end_month": "4"},
]

# Upload G16 code
with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

print("Uploading v20b_g16.py as main.py...")
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
    params = G16_PARAMS + [
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
        # Print errors if any
        errors = resp.get("errors", [])
        for err in errors[:10]:
            print(f"    ERROR: {err}")
        results[name] = {"status": "COMPILE_FAILED", "errors": errors[:10]}
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
    with open(f"{OUTPUT_DIR}/g16_{safe}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print(f"  Saved: {OUTPUT_DIR}/g16_{safe}_raw.json")

# ============================================================
# COMPARISON TABLE: G16 vs G15
# ============================================================
print(f"\n{'=' * 160}")
print("=== G16 (4 fixes) vs G15 (baseline) vs V4-B vs v10.13b ===")
print("=" * 160)

hdr = f"{'Version':<36} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'Alpha':>8} {'PSR':>8} {'P/L':>8} {'Expect':>8}"
print(hdr)
print("-" * 160)

# G15 baselines
print(f"{'G15 IS 2023-2024':<36} {'243.8%':>10} {'85.9%':>10} {'1.503':>10} {'1.821':>10} {'48.8%':>10} {'48%':>8} {'318':>8} {'0.445':>8} {'68.1%':>8} {'1.72':>8} {'0.306':>8}")
print(f"{'G15 OOS 2025-2026':<36} {'-10.2%':>10} {'-8.2%':>10} {'-0.177':>10} {'-0.175':>10} {'22.2%':>10} {'43%':>8} {'175':>8} {'-0.097':>8} {'8.6%':>8} {'1.30':>8} {'-0.008':>8}")
print(f"{'G15 Full 2023-2026':<36} {'200.8%':>10} {'40.1%':>10} {'0.790':>10} {'0.924':>10} {'48.8%':>10} {'46%':>8} {'491':>8} {'0.162':>8} {'32.3%':>8} {'1.59':>8} {'0.189':>8}")
print("-" * 160)

# G16 results
for name in ["G16 IS 2023-2024", "G16 OOS 2025-2026", "G16 Full 2023-2026"]:
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
        exp = str(r.get("Expectancy", "?"))
        print(f"{name:<36} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {alpha:>8} {psr:>8} {pl:>8} {exp:>8}")
    else:
        status = r.get("status", "NOT_RUN")
        print(f"{name:<36} {'--- ' + status + ' ---'}")

print("-" * 160)

# Other baselines
print(f"{'v10.13b IS (2023-2024)':<36} {'96.3%':>10} {'40.03%':>10} {'1.453':>10} {'1.501':>10} {'8.6%':>10} {'89%':>8} {'117':>8} {'0.166':>8} {'87.4%':>8} {'N/A':>8} {'N/A':>8}")
print(f"{'v10.13b OOS (2025-2026)':<36} {'-10.8%':>10} {'-8.63%':>10} {'-0.579':>10} {'-0.606':>10} {'24.0%':>10} {'45%':>8} {'46':>8} {'-0.122':>8} {'6.15%':>8} {'N/A':>8} {'N/A':>8}")

# Verdict
print(f"\n--- G16 vs G15 VERDICT ---")
is_r = results.get("G16 IS 2023-2024", {})
oos_r = results.get("G16 OOS 2025-2026", {})
full_r = results.get("G16 Full 2023-2026", {})

for label, r, g15_val in [("IS", is_r, 1.503), ("OOS", oos_r, -0.177), ("Full", full_r, 0.790)]:
    if "bt_id" in r and r.get("status") != "INCOMPLETE":
        try:
            s = float(str(r.get("Sharpe Ratio", "0")).replace("%", ""))
            delta = s - g15_val
            print(f"  G16 {label} Sharpe: {s:.3f} (G15: {g15_val:.3f}, delta: {delta:+.3f})")
        except:
            print(f"  G16 {label}: parse error")

if "bt_id" in oos_r and oos_r.get("status") != "INCOMPLETE":
    try:
        oos_s = float(str(oos_r.get("Sharpe Ratio", "0")).replace("%", ""))
        if oos_s > 0.6:
            print(f"  *** G16 OOS PASSES DEPLOY GATE (Sharpe >= 0.6) ***")
        elif oos_s > 0:
            print(f"  G16 OOS positive but below deploy gate (need >= 0.6)")
        else:
            print(f"  G16 OOS still negative -- fixes insufficient alone")
    except:
        pass

# Save all
with open(f"{OUTPUT_DIR}/g16_is_oos_full_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/g16_is_oos_full_results.json")
print("\nDONE.")
