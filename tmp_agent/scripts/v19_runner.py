"""
V19 Equity Test Runner - Upload code to QC, run IS/OOS/Full backtests.
IS: 2022-01-01 to 2024-06-30
OOS: 2024-07-01 to 2026-03-31
Full: 2022-01-01 to 2026-03-31
"""
import hashlib, base64, time, json, requests, os, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/strategies/v19_equity_test.py"
OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies"

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

# No strategy-specific params - all hardcoded in algorithm
PARAMS = []

TESTS = [
    {"name": "V19v3 IS 2022-2024H1",  "start_year": "2022", "start_month": "1", "end_year": "2024", "end_month": "7"},
    {"name": "V19v3 OOS 2024H2-2026", "start_year": "2024", "start_month": "7", "end_year": "2026", "end_month": "4"},
    {"name": "V19v3 Full 2022-2026",   "start_year": "2022", "start_month": "1", "end_year": "2026", "end_month": "4"},
]

with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

print("Uploading v19_equity_test.py as main.py...")
resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
if not resp.get("success"):
    # Try create instead of update
    print("  Update failed, trying create...")
    resp = api("files/create", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
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

    params = PARAMS + [
        {"key": "start_year", "value": test["start_year"]},
        {"key": "start_month", "value": test["start_month"]},
        {"key": "end_year", "value": test["end_year"]},
        {"key": "end_month", "value": test["end_month"]},
    ]
    resp = api("projects/update", {"projectId": PROJECT_ID, "parameters": params})
    if not resp.get("success"):
        print(f"  Params FAILED: {resp}")
        results[name] = {"status": "PARAMS_FAILED"}
        continue
    print("  Params set OK")

    print("  Compiling...")
    resp = api("compile/create", {"projectId": PROJECT_ID})
    compile_id = resp.get("compileId")
    state = resp.get("state")
    for ci in range(30):
        if state == "BuildSuccess":
            break
        time.sleep(5)
        try:
            resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id}, retries=3)
            state = resp.get("state")
        except:
            pass
    if state != "BuildSuccess":
        print(f"  Compile FAILED: {state}")
        errors = resp.get("errors", [])
        for err in errors[:15]:
            print(f"    ERROR: {err}")
        results[name] = {"status": "COMPILE_FAILED", "errors": errors[:15]}
        continue
    print(f"  Compile OK: {compile_id}")

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

    # Poll - ML training can take longer, allow up to 90 min
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
        results[name] = {"status": "INCOMPLETE", "bt_id": bt_id}
        print(f"  INCOMPLETE after polling. bt_id={bt_id}")
        continue

    # Check for runtime errors
    error = bt.get("error", "")
    stacktrace = bt.get("stacktrace", "")
    if error:
        print(f"  RUNTIME ERROR: {error}")
        if stacktrace:
            print(f"  STACKTRACE: {stacktrace[:500]}")
        results[name] = {"status": "RUNTIME_ERROR", "bt_id": bt_id, "error": error, "stacktrace": stacktrace[:500]}
        # Save raw anyway
        safe = name.replace(" ", "_").lower()
        with open(f"{OUTPUT_DIR}/v19_{safe}_raw.json", "w") as f:
            json.dump(resp, f, indent=2, default=str)
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

    safe = name.replace(" ", "_").lower()
    with open(f"{OUTPUT_DIR}/v19_{safe}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)

# ================================================================
# Comparison table
# ================================================================
print(f"\n{'=' * 180}")
print("=== V19v3 AGGRESSIVE vs V19v2 BASELINE vs G15 ===")
print("=" * 180)

hdr = f"{'Version':<40} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'PSR':>8} {'P/L':>8} {'Expect':>8}"
print(hdr)
print("-" * 180)

# V19 v2 baseline
print(f"{'V19v2 IS 2022-2024H1':<40} {'2.7%':>10} {'1.1%':>10} {'-0.644':>10} {'-0.484':>10} {'6.1%':>10} {'46%':>8} {'48':>8} {'5.9%':>8} {'1.38':>8} {'0.090':>8}")
print(f"{'V19v2 OOS 2024H2-2026':<40} {'1.0%':>10} {'0.6%':>10} {'-2.442':>10} {'-1.006':>10} {'2.2%':>10} {'58%':>8} {'24':>8} {'10.3%':>8} {'0.93':>8} {'0.123':>8}")
print(f"{'V19v2 Full 2022-2026':<40} {'12.6%':>10} {'2.8%':>10} {'-0.532':>10} {'-0.388':>10} {'6.1%':>10} {'49%':>8} {'92':>8} {'7.1%':>8} {'1.56':>8} {'0.251':>8}")
print("-" * 180)

# G15 reference
print(f"{'G15 IS 2023-2024':<40} {'243.8%':>10} {'85.9%':>10} {'1.503':>10} {'1.821':>10} {'48.8%':>10} {'48%':>8} {'318':>8} {'68.1%':>8} {'1.72':>8} {'0.306':>8}")
print(f"{'G15 OOS 2025-2026':<40} {'-10.2%':>10} {'-8.2%':>10} {'-0.177':>10} {'-0.175':>10} {'22.2%':>10} {'43%':>8} {'175':>8} {'8.6%':>8} {'1.30':>8} {'-0.008':>8}")
print(f"{'G15 Full 2023-2026':<40} {'200.8%':>10} {'40.1%':>10} {'0.790':>10} {'0.924':>10} {'48.8%':>10} {'46%':>8} {'491':>8} {'32.3%':>8} {'1.59':>8} {'0.189':>8}")
print("-" * 180)

# V19 results
for name in TESTS:
    n = name["name"]
    r = results.get(n, {})
    if "bt_id" in r and r.get("status") not in ("INCOMPLETE", "RUNTIME_ERROR"):
        net = str(r.get("Net Profit", "?"))
        cagr = str(r.get("Compounding Annual Return", "?"))
        sharpe = str(r.get("Sharpe Ratio", "?"))
        sortino = str(r.get("Sortino Ratio", "?"))
        dd = str(r.get("Drawdown", "?"))
        wr = str(r.get("Win Rate", "?"))
        orders = str(r.get("Total Orders", "?"))
        psr = str(r.get("Probabilistic Sharpe Ratio", "?"))
        pl = str(r.get("Profit-Loss Ratio", "?"))
        exp = str(r.get("Expectancy", "?"))
        print(f"{n:<40} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {psr:>8} {pl:>8} {exp:>8}")
    else:
        status = r.get("status", "NOT_RUN")
        err = r.get("error", "")[:80] if r.get("error") else ""
        print(f"{n:<40} {'--- ' + status + ' ---'} {err}")

# Verdict
print(f"\n--- V19v3 AGGRESSIVE VERDICT ---")
print("Changes vs v2: threshold 0.55->0.50, pos 0.50->0.90, horizon 10->15, PT 1.25->1.5, SMA200 filter")
for test in TESTS:
    n = test["name"]
    r = results.get(n, {})
    if "bt_id" in r and r.get("status") not in ("INCOMPLETE", "RUNTIME_ERROR"):
        try:
            s = float(str(r.get("Sharpe Ratio", "0")).replace("%", ""))
            label = "IS" if "IS" in n else "OOS" if "OOS" in n else "Full"
            print(f"  V19v3 {label} Sharpe: {s:.3f}")
        except:
            pass

# Save all
with open(f"{OUTPUT_DIR}/v19v3_is_oos_full_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/v19v3_is_oos_full_results.json")
print("\nDONE.")
