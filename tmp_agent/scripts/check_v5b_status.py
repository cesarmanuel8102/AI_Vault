"""Quick check on V5b backtest status"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BT_ID = "c0fac48a599f1f0bdf3b798343e3c646"
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

progress = bt.get("progress", "?")
completed = bt.get("completed", False)
prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)

print(f"Backtest: {bt.get('name','?')}")
print(f"Progress: {prog_str}")
print(f"Completed: {completed}")

if completed:
    stats = bt.get("statistics", {})
    print("\n--- STATISTICS ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
