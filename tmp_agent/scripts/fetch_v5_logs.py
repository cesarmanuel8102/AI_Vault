"""
Fetch V5 backtest logs to diagnose why performance collapsed.
"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BT_ID = "f12e677ce3f29adfea593b48a2343b2b"
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
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise

# Fetch logs
print("=== Fetching V5 backtest logs ===")
resp = api("backtests/read", {
    "projectId": PROJECT_ID,
    "backtestId": BT_ID,
})

bt = resp.get("backtest", resp)
result = bt.get("result", {})

# Get algorithm logs
logs = result.get("AlgorithmLogs", [])
if not logs:
    logs = result.get("Logs", [])
if not logs:
    # Try log endpoint
    print("  No logs in backtest result, trying log endpoint...")
    resp2 = api("backtests/read/log", {
        "projectId": PROJECT_ID,
        "backtestId": BT_ID,
        "query": "",
    })
    logs = resp2.get("logs", [])

# Save all logs
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_logs.txt", "w", encoding="utf-8") as f:
    if isinstance(logs, list):
        for line in logs:
            if isinstance(line, str):
                f.write(line + "\n")
            elif isinstance(line, dict):
                f.write(json.dumps(line) + "\n")
    elif isinstance(logs, str):
        f.write(logs)

print(f"  Saved {len(logs) if isinstance(logs, list) else 'unknown'} log lines")

# Also check the raw result for order/trade data
orders = result.get("Orders", {})
print(f"  Orders in result: {len(orders) if isinstance(orders, dict) else 'unknown'}")

# Extract closed trade data from orders
trades_data = []
if isinstance(orders, dict):
    for oid, order in orders.items():
        trades_data.append({
            "id": order.get("Id"),
            "symbol": str(order.get("Symbol", {}).get("Value", "")),
            "type": order.get("Type"),
            "status": order.get("Status"),
            "quantity": order.get("Quantity"),
            "price": order.get("Price"),
            "time": str(order.get("Time", "")),
            "tag": order.get("Tag", ""),
        })

with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_orders.json", "w") as f:
    json.dump(trades_data, f, indent=2, default=str)
print(f"  Saved {len(trades_data)} orders to v5_orders.json")

# Print key log lines (INIT, FIX counters, FINAL REPORT)
print("\n=== KEY LOG LINES ===")
if isinstance(logs, list):
    for line in logs:
        line_str = str(line)
        if any(kw in line_str for kw in ["INIT", "FIX", "FINAL", "TRAIL", "cutoff", "regime", "mfe_mult", "capture", "CONF_DIST", "BY TICKER", "BY EXIT", "CLOSE", "OPEN"]):
            # Limit to avoid flooding
            if len(line_str) > 200:
                line_str = line_str[:200]
            print(f"  {line_str}")
elif isinstance(logs, str):
    for line in logs.split("\n"):
        if any(kw in line for kw in ["INIT", "FIX", "FINAL", "TRAIL", "cutoff", "regime", "mfe_mult", "capture", "CONF_DIST", "BY TICKER", "BY EXIT"]):
            print(f"  {line[:200]}")

print("\nDONE")
