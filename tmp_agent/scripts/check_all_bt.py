"""Check ALL backtests in ALL projects thoroughly."""
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

# List all projects
r = requests.post(f"{BASE}/projects/read", headers=headers(), json={})
projects = r.json().get("projects", [])
print(f"Total projects: {len(projects)}\n")

for p in projects:
    pid = p["projectId"]
    name = p.get("name", "?")
    print(f"Project: {name} (ID: {pid})")
    
    # List backtests for this project
    r2 = requests.post(f"{BASE}/backtests/read", headers=headers(), json={"projectId": pid})
    data = r2.json()
    
    if not data.get("success"):
        print(f"  Error: {data.get('errors', [])}")
        continue
    
    # The API returns either a single "backtest" or a list of "backtests"
    bt = data.get("backtest")
    bts = data.get("backtests", [])
    
    if bt:
        prog = bt.get("progress", -1)
        name_bt = bt.get("name", "?")
        bt_id = bt.get("backtestId", "?")
        error = bt.get("error", "")
        stats = bt.get("runtimeStatistics", {})
        equity = stats.get("Equity", "?")
        print(f"  Latest BT: {name_bt} | ID: {bt_id} | Progress: {prog*100:.1f}% | Equity: {equity}")
        if error:
            print(f"  ERROR: {error[:200]}")
        if prog < 1.0 and prog >= 0:
            print(f"  >>> RUNNING <<<")
    
    if bts:
        for b in bts[:3]:  # Show last 3
            prog = b.get("progress", -1)
            name_bt = b.get("name", "?")
            bt_id = b.get("backtestId", "?")
            print(f"  BT: {name_bt} | {bt_id} | {prog*100:.1f}%")
    
    print()
