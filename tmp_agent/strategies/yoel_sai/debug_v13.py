"""Debug: check V1.3 backtest structure."""
import requests, json, base64

creds = json.load(open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json"))
def headers():
    token = base64.b64encode(f"{creds['user_id']}:{creds['token']}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "c877eb3fdbc3a97b54b96b2b2648c842"

r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={"projectId": PROJECT_ID, "backtestId": BT_ID})
data = r.json()
bt = data.get("backtest", {})

print("Top-level keys:", list(bt.keys())[:20])
perf = bt.get("totalPerformance", {})
print("totalPerformance keys:", list(perf.keys()) if perf else "EMPTY")

if perf:
    for k, v in perf.items():
        if isinstance(v, list):
            print(f"  {k}: list of {len(v)}")
        elif isinstance(v, dict):
            print(f"  {k}: dict with keys {list(v.keys())[:5]}")
        else:
            print(f"  {k}: {type(v).__name__}")

# Check if closedTrades is nested differently
ct = perf.get("closedTrades", [])
print(f"\nclosedTrades: {type(ct).__name__}, length: {len(ct) if isinstance(ct, list) else 'N/A'}")

# Check tradeStatistics
ts = perf.get("tradeStatistics", {})
if ts:
    print(f"\ntradeStatistics keys: {list(ts.keys())[:10]}")
    print(f"  totalNumberOfTrades: {ts.get('totalNumberOfTrades', 'N/A')}")

# Check if result has statistics
stats = bt.get("statistics", {})
if stats:
    print(f"\nstatistics: {json.dumps(stats, indent=2)[:500]}")

# Maybe we need to check runtimeStatistics
rs = bt.get("runtimeStatistics", {})
if rs:
    print(f"\nruntimeStatistics: {json.dumps(rs, indent=2)[:500]}")
