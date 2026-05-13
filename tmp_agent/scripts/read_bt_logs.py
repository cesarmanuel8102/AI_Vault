"""Read logs from a running/completed backtest."""
import time, json, requests, sys
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

# Read logs with query
query = sys.argv[1] if len(sys.argv) > 1 else " "
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 200

print(f"Reading logs: query='{query}' range=[{start}-{end}]")
r = requests.post(f"{BASE}/backtests/read/log", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": BT_ID,
    "start": start, "end": end, "query": query
})
data = r.json()
logs = data.get("logs", [])
total = data.get("length", 0)
print(f"Total matching: {total}, returned: {len(logs)}\n")

for i, log in enumerate(logs):
    print(f"[{start+i}] {log}")
