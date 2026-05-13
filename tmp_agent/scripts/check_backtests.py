"""Check if any backtests are running on QC compute node."""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# List all projects, then check for running backtests
r = requests.post(f"{BASE}/projects/read", headers=headers(), json={})
projects = r.json().get("projects", [])
print(f"Total projects: {len(projects)}")

# Check backtests for each project (look for running ones)
running = []
for p in projects:
    pid = p["projectId"]
    name = p.get("name", "?")
    r2 = requests.post(f"{BASE}/backtests/read", headers=headers(), json={"projectId": pid})
    data = r2.json()
    if data.get("success"):
        bt = data.get("backtest", {})
        if bt and bt.get("progress", 1.0) < 1.0:
            running.append({"project": name, "projectId": pid, "backtest": bt.get("name"), "progress": bt.get("progress")})

if running:
    print(f"\n[!] RUNNING BACKTESTS FOUND:")
    for b in running:
        print(f"  - {b['project']} ({b['projectId']}): {b['backtest']} @ {b['progress']*100:.0f}%")
else:
    print("\n[OK] No running backtests -- compute node is free.")
