"""
Check QC account node availability for live deployment.
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

# Try different node endpoints
endpoints = [
    ("POST", "/live/nodes/read", {}),
    ("GET", "/live/nodes/read", None),
    ("POST", "/nodes/read", {}),
    ("GET", "/nodes/read", None),
    ("POST", "/account/read", {}),
    ("GET", "/account/read", None),
]

for method, path, body in endpoints:
    url = f"{BASE}{path}"
    print(f"\n--- {method} {path} ---")
    try:
        if method == "POST":
            r = requests.post(url, headers=headers(), json=body)
        else:
            r = requests.get(url, headers=headers())
        print(f"  Status: {r.status_code}")
        try:
            data = r.json()
            print(f"  Response: {json.dumps(data, indent=2)[:500]}")
        except:
            print(f"  Raw: {r.text[:300]}")
    except Exception as e:
        print(f"  Error: {e}")

# Check the running live deploy details
print("\n\n=== Current Running Live Deploy ===")
r = requests.post(f"{BASE}/live/read", headers=headers(), json={
    "projectId": 29490680,
    "deployId": "L-a3345a35af69b18cf58724bf7a88e596"
})
data = r.json()
# Extract node info
if data.get("success"):
    live = data.get("LiveResults") or data.get("live") or {}
    results = live.get("Results") or live.get("results") or {}
    print(f"  Success: True")
    print(f"  Keys: {list(data.keys())}")
    # Look for node ID
    for key in data:
        if "node" in key.lower():
            print(f"  {key}: {data[key]}")
    # Print selected info
    if "nodeId" in data:
        print(f"  nodeId: {data['nodeId']}")
    if "LiveResults" in data:
        lr = data["LiveResults"]
        if isinstance(lr, dict):
            for k in lr:
                if "node" in k.lower():
                    print(f"  LiveResults.{k}: {lr[k]}")
    # Check RuntimeStatistics
    rs = results.get("RuntimeStatistics") or {}
    if rs:
        print(f"  Runtime Stats: {json.dumps(rs, indent=2)[:500]}")
else:
    print(f"  Failed: {data}")
