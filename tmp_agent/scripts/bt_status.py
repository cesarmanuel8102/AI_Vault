"""Quick status check for specific backtest."""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "dfb6114d2ac159cbf11c39af183183c3"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": BT_ID
})
data = r.json()
bt = data.get("backtest", {})
progress = bt.get("progress", 0)
error = bt.get("error", "")
stats = bt.get("runtimeStatistics", {})

print(f"Progress: {progress*100:.1f}%")
if error:
    print(f"ERROR: {error}")
    if bt.get("stacktrace"):
        print(f"STACK: {bt['stacktrace'][:500]}")
for k, v in stats.items():
    print(f"  {k}: {v}")

if progress >= 1.0:
    statistics = bt.get("statistics", {})
    if statistics:
        print("\n--- Statistics ---")
        for k, v in statistics.items():
            print(f"  {k}: {v}")
