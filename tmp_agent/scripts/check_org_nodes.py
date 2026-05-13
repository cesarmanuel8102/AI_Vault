"""
List QC live nodes using organization ID.
"""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
ORG_ID = "6d487993ca17881264c2ac55e41ae539"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# Try organization read with org ID
print("=== Organization Read ===")
r = requests.post(f"{BASE}/organization/read", headers=headers(), json={"organizationId": ORG_ID})
try:
    data = r.json()
    if data.get("success"):
        org = data.get("organization", data)
        # Print all keys
        print(f"Keys: {list(org.keys()) if isinstance(org, dict) else 'not a dict'}")
        # Look for nodes/live info
        for key in sorted(org.keys()) if isinstance(org, dict) else []:
            val = org[key]
            if isinstance(val, (dict, list)):
                print(f"\n  {key}: {json.dumps(val, indent=4)[:1000]}")
            else:
                print(f"  {key}: {val}")
    else:
        print(f"Failed: {data}")
except Exception as e:
    print(f"Error: {e}")
    print(f"Raw: {r.text[:500]}")
