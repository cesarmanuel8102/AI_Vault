"""Fetch V5a OOS stats directly"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BT_ID = "cad6ffbf6a0720036d952a7b5af1dd5b"
BASE = "https://www.quantconnect.com/api/v2"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

r = requests.post(f"{BASE}/backtests/read", headers=auth_headers(),
                   json={"projectId": PROJECT_ID, "backtestId": BT_ID}, timeout=30)
data = r.json()
bt = data.get("backtest", data)

print(f"Name: {bt.get('name')}")
print(f"Completed: {bt.get('completed')}")
print(f"Error: {bt.get('error')}")

stats = bt.get("statistics", {})
if stats:
    print(f"\n--- ALL STATISTICS ({len(stats)} metrics) ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
else:
    print("NO STATS FOUND")
    print(f"Keys in backtest: {list(bt.keys())}")
