"""Try to read backtest algorithm logs from QC API."""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
BACKTEST_ID = "b4f63cef2b64763c7b30b68e0b6a3281"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# Try /backtests/read/log
print("=== Trying /backtests/read/log ===")
r = requests.post(f"{BASE}/backtests/read/log", headers=headers(), json={
    "projectId": PROJECT_ID,
    "backtestId": BACKTEST_ID
})
data = r.json()
print(f"Success: {data.get('success')}")

logs = data.get("logs", data.get("log", []))
if isinstance(logs, list):
    print(f"Log entries: {len(logs)}")
    for line in logs[:100]:
        print(line)
elif isinstance(logs, str):
    print(f"Log length: {len(logs)}")
    print(logs[:8000])
else:
    print(f"Full response keys: {list(data.keys())}")
    print(json.dumps(data, indent=2)[:5000])
