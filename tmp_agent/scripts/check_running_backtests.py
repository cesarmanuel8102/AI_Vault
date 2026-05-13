"""Check what's running on QC - list backtests and their status."""
import json, time, hashlib, base64, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680

def get_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}

BASE = "https://www.quantconnect.com/api/v2"

# List all backtests for the project
resp = requests.post(f"{BASE}/backtests/list", headers=get_auth(), json={
    "projectId": PROJECT_ID
})
data = resp.json()
print(f"Success: {data.get('success')}")

if data.get("success"):
    backtests = data.get("backtests", [])
    print(f"Total backtests: {len(backtests)}")
    print()
    
    # Show recent ones
    for bt in backtests[:15]:
        name = bt.get("name", "N/A")
        status = bt.get("status", "N/A")
        bt_id = bt.get("backtestId", "N/A")
        created = bt.get("created", "N/A")
        print(f"[{status}] {name}")
        print(f"  ID: {bt_id} | Created: {created}")
else:
    print(f"Error: {data}")

# Also check organization nodes
print("\n" + "=" * 60)
resp2 = requests.post(f"{BASE}/backtests/read", headers=get_auth(), json={
    "projectId": PROJECT_ID,
    "backtestId": backtests[0]["backtestId"] if data.get("success") and backtests else ""
})
d2 = resp2.json()
if d2.get("success"):
    bt = d2.get("backtest", {})
    print(f"Latest BT status: {bt.get('status')}")
    print(f"Progress: {bt.get('progress')}")
