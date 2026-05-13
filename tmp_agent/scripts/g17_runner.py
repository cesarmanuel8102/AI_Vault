"""
G17 Runner: V2.0b-G17 = G15 + FIX 1 ONLY (anti-same-day SL)
PT=0.35, SL=-0.20, Risk=0.06, DTE=14-30
Isolation test: does FIX 1 alone improve OOS?
"""
import hashlib, base64, time, json, requests, os, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_g17.py"
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

PARAMS = [
    {"key": "profit_target_pct", "value": "0.35"},
    {"key": "stop_loss_pct", "value": "-0.20"},
    {"key": "risk_per_trade", "value": "0.06"},
    {"key": "dte_min", "value": "14"},
    {"key": "dte_max", "value": "30"},
]

TESTS = [
    {"name": "G17 IS 2023-2024",   "start_year": "2023", "end_year": "2024", "end_month": "12"},
    {"name": "G17 OOS 2025-2026",  "start_year": "2025", "end_year": "2026", "end_month": "4"},
    {"name": "G17 Full 2023-2026", "start_year": "2023", "end_year": "2026", "end_month": "4"},
]

with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

print("Uploading v20b_g17.py as main.py...")
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

    params = PARAMS + [
        {"key": "start_year", "value": test["start_year"]},
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
        errors = resp.get("errors", [])
        for err in errors[:10]:
            print(f"    ERROR: {err}")
        results[name] = {"status": "COMPILE_FAILED", "errors": errors[:10]}
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
    with open(f"{OUTPUT_DIR}/g17_{safe}_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)

# Comparison
print(f"\n{'=' * 160}")
print("=== G17 (FIX1 only) vs G16 (all 4) vs G15 (baseline) ===")
print("=" * 160)

hdr = f"{'Version':<36} {'Net':>10} {'CAGR':>10} {'Sharpe':>10} {'Sortino':>10} {'DD':>10} {'WR':>8} {'Orders':>8} {'PSR':>8} {'P/L':>8} {'Expect':>8}"
print(hdr)
print("-" * 160)

print(f"{'G15 IS 2023-2024':<36} {'243.8%':>10} {'85.9%':>10} {'1.503':>10} {'1.821':>10} {'48.8%':>10} {'48%':>8} {'318':>8} {'68.1%':>8} {'1.72':>8} {'0.306':>8}")
print(f"{'G15 OOS 2025-2026':<36} {'-10.2%':>10} {'-8.2%':>10} {'-0.177':>10} {'-0.175':>10} {'22.2%':>10} {'43%':>8} {'175':>8} {'8.6%':>8} {'1.30':>8} {'-0.008':>8}")
print(f"{'G15 Full 2023-2026':<36} {'200.8%':>10} {'40.1%':>10} {'0.790':>10} {'0.924':>10} {'48.8%':>10} {'46%':>8} {'491':>8} {'32.3%':>8} {'1.59':>8} {'0.189':>8}")
print("-" * 160)

print(f"{'G16 IS 2023-2024':<36} {'89.7%':>10} {'37.9%':>10} {'0.810':>10} {'0.840':>10} {'44.5%':>10} {'48%':>8} {'267':>8} {'39.5%':>8} {'1.62':>8} {'0.259':>8}")
print(f"{'G16 OOS 2025-2026':<36} {'-18.0%':>10} {'-14.5%':>10} {'-0.413':>10} {'-0.346':>10} {'32.1%':>10} {'52%':>8} {'158':>8} {'5.0%':>8} {'0.83':>8} {'-0.054':>8}")
print(f"{'G16 Full 2023-2026':<36} {'49.7%':>10} {'13.2%':>10} {'0.278':>10} {'0.272':>10} {'44.5%':>10} {'48%':>8} {'435':>8} {'10.6%':>8} {'1.32':>8} {'0.112':>8}")
print("-" * 160)

for name in ["G17 IS 2023-2024", "G17 OOS 2025-2026", "G17 Full 2023-2026"]:
    r = results.get(name, {})
    if "bt_id" in r and r.get("status") != "INCOMPLETE":
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
        print(f"{name:<36} {net:>10} {cagr:>10} {sharpe:>10} {sortino:>10} {dd:>10} {wr:>8} {orders:>8} {psr:>8} {pl:>8} {exp:>8}")
    else:
        status = r.get("status", "NOT_RUN")
        print(f"{name:<36} {'--- ' + status + ' ---'}")

# Verdict
print(f"\n--- FIX 1 ISOLATION VERDICT ---")
for label, g15_val in [("IS", 1.503), ("OOS", -0.177), ("Full", 0.790)]:
    r = results.get(f"G17 {label} {'2023-2024' if label == 'IS' else '2025-2026' if label == 'OOS' else '2023-2026'}", {})
    if "bt_id" in r and r.get("status") != "INCOMPLETE":
        try:
            s = float(str(r.get("Sharpe Ratio", "0")).replace("%", ""))
            print(f"  G17 {label} Sharpe: {s:.3f} (G15: {g15_val:.3f}, delta: {s - g15_val:+.3f})")
        except:
            pass

with open(f"{OUTPUT_DIR}/g17_is_oos_full_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nAll results saved to {OUTPUT_DIR}/g17_is_oos_full_results.json")
print("\nDONE.")
