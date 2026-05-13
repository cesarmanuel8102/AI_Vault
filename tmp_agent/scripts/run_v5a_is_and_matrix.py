"""Run V5a IS 2023-2024 backtest to complete the degradation matrix"""
import hashlib, base64, time, json, requests

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
            if attempt < 2:
                time.sleep(5)
            else:
                raise

# Set V5a IS params
params = {
    "enable_fix2": "0", "enable_fix3": "1", "enable_fix4": "0",
    "trail_act": "0.20", "trail_pct": "0.50",
    "profit_target_pct": "0.35",
    "stop_loss_pct": "-0.20",
    "risk_per_trade": "0.04",
    "dte_min": "14", "dte_max": "30",
    "start_year": "2023", "end_year": "2024", "end_month": "12",
}

param_list = [{"key": k, "value": v} for k, v in params.items()]
resp = api("projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
print(f"Params set: success={resp.get('success')}")

# Verify
resp = api("projects/read", {"projectId": PROJECT_ID})
proj = resp["projects"][0] if isinstance(resp["projects"], list) else resp["projects"]
p = {x["key"]: x["value"] for x in proj.get("parameters", [])}
print(f"Verified: fix3={p.get('enable_fix3')}, start={p.get('start_year')}, end={p.get('end_year')}, month={p.get('end_month')}")

# Compile
resp = api("compile/create", {"projectId": PROJECT_ID})
compile_id = resp.get("compileId")
state = resp.get("state")
print(f"Compile: {compile_id} state={state}")

for i in range(20):
    if state == "BuildSuccess":
        break
    time.sleep(3)
    resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
    state = resp.get("state")

if state != "BuildSuccess":
    print(f"COMPILE FAILED: {state}")
    exit(1)

# Launch
resp = api("backtests/create", {
    "projectId": PROJECT_ID, "compileId": compile_id,
    "backtestName": "V5a IS 2023-2024",
})
bt = resp.get("backtest", resp)
bt_id = bt.get("backtestId")
print(f"Backtest launched: {bt_id}")

# Poll
for i in range(120):
    time.sleep(10)
    resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
    bt = resp.get("backtest", resp)
    progress = bt.get("progress", 0)
    completed = bt.get("completed", False)
    prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
    if i % 6 == 0:
        print(f"Poll {i+1}: {prog_str}")
    if completed:
        break

if not completed:
    print("TIMEOUT")
    exit(1)

stats = bt.get("statistics", {})
print(f"\n--- V5a IS 2023-2024 RESULTS ({len(stats)} metrics) ---")
for k, v in stats.items():
    print(f"  {k}: {v}")

# Save
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5a_is_2023_2024_raw.json", "w") as f:
    json.dump(resp, f, indent=2, default=str)

# Now load all data and build the 6-cell matrix
print(f"\n{'='*80}")
print("=== COMPLETE DEGRADATION MATRIX: V4-B vs V5a across IS/OOS/Full ===")
print(f"{'='*80}")

# Load saved data
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/complete_comparison_data.json", "r") as f:
    saved = json.load(f)

saved["V5a IS 2023-2024"] = stats

# Save updated
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/complete_comparison_data.json", "w") as f:
    json.dump(saved, f, indent=2)

# Print full table
order = [
    "V4-B IS 2023-2024", "V5a IS 2023-2024",
    "V4-B OOS 2025-2026", "V5a OOS 2025-2026",
    "V4-B Full 2023-2026", "V5a Full 2023-2026",
]

metrics = [
    "Total Orders", "Average Win", "Average Loss",
    "Compounding Annual Return", "Drawdown", "Expectancy",
    "Start Equity", "End Equity", "Net Profit",
    "Sharpe Ratio", "Sortino Ratio", "Probabilistic Sharpe Ratio",
    "Loss Rate", "Win Rate", "Profit-Loss Ratio",
    "Annual Standard Deviation", "Annual Variance",
    "Information Ratio", "Tracking Error",
    "Total Fees", "Estimated Strategy Capacity",
    "Portfolio Turnover", "Drawdown Recovery",
]

# Print header
print(f"\n{'Metric':<28}", end="")
for name in order:
    short = name.replace("2023-2024","IS").replace("2025-2026","OOS").replace("2023-2026","FULL")
    print(f" {short:>18}", end="")
print()
print("-" * 140)

for m in metrics:
    print(f"{m:<28}", end="")
    for name in order:
        val = saved.get(name, {}).get(m, "N/A")
        print(f" {str(val):>18}", end="")
    print()

print(f"\n=== DONE ===")
