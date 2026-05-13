"""
Explore QC Live capabilities:
1. List available live nodes
2. List currently running live algorithms
3. Check if we can deploy CMR-V2.0
"""
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

# 1. Check account status
print("=== 1. Account Authentication ===")
r = requests.post(f"{BASE}/authenticate", headers=headers(), json={})
data = r.json()
print(f"Auth success: {data.get('success')}")

# 2. List live nodes
print("\n=== 2. List Live Nodes ===")
r = requests.post(f"{BASE}/live/nodes/read", headers=headers(), json={})
data = r.json()
print(f"Response: {json.dumps(data, indent=2)}")

# 3. List running live algorithms
print("\n=== 3. Running Live Algorithms ===")
r = requests.post(f"{BASE}/live/list", headers=headers(), json={
    "status": "Running",
    "start": 0,
    "end": 50
})
data = r.json()
print(f"Response: {json.dumps(data, indent=2)}")

# 4. List all live algorithms (any status)
print("\n=== 4. All Live Algorithms (any status) ===")
for status in ["Running", "Stopped", "RuntimeError", "Liquidated"]:
    r = requests.post(f"{BASE}/live/list", headers=headers(), json={
        "status": status,
        "start": 0,
        "end": 10
    })
    data = r.json()
    lives = data.get("live", [])
    if lives:
        print(f"\n  Status: {status} ({len(lives)} found)")
        for lv in lives:
            print(f"    deployId: {lv.get('deployId')} | project: {lv.get('projectId')} | launched: {lv.get('launched')}")

# 5. List all projects
print("\n=== 5. All Projects ===")
r = requests.post(f"{BASE}/projects/read", headers=headers(), json={})
data = r.json()
for p in data.get("projects", []):
    print(f"  ID: {p.get('projectId')} | Name: {p.get('name')} | Language: {p.get('language')}")

# 6. Check organization/node info
print("\n=== 6. Organization Info ===")
r = requests.post(f"{BASE}/organization/read", headers=headers(), json={})
data = r.json()
# Print relevant fields
org = data.get("organization", data)
if isinstance(org, dict):
    for key in ["id", "name", "seats", "type", "credit", "nodes"]:
        if key in org:
            val = org[key]
            if isinstance(val, (dict, list)):
                print(f"  {key}: {json.dumps(val, indent=4)}")
            else:
                print(f"  {key}: {val}")
