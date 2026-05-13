"""
1. Stop any existing live deployment
2. Deploy with multipart/form-data (which passes colon validation!)
"""
import json, time, hashlib, requests

with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]

BASE_URL = "https://www.quantconnect.com/api/v2"

def make_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    return ts, token_bytes

# ── Step 1: Check current live status ────────────────────────
ts, token_bytes = make_auth()
print("=== Step 1: Check existing live deployment ===")
resp = requests.post(
    f"{BASE_URL}/live/read",
    auth=(USER_ID, token_bytes),
    headers={"Timestamp": ts},
    json={"projectId": 29490680},
    timeout=60
)
data = resp.json()
print(f"Status: {resp.status_code}")
if data.get("success"):
    live_algo = data
    status = live_algo.get("status", "unknown")
    deploy_id = live_algo.get("deployId", "")
    print(f"Live algo status: {status}")
    print(f"Deploy ID: {deploy_id}")
    print(f"Project: {live_algo.get('projectId')}")
    
    # If there's a running/stopped deployment, stop & liquidate it
    if status in ["Running", "RuntimeError", "Stopped", "Liquidated", "LoggingIn", "Initializing", "DeployError"]:
        print(f"\nStopping existing deployment (status={status})...")
        ts2, token2 = make_auth()
        resp2 = requests.post(
            f"{BASE_URL}/live/update/stop",
            auth=(USER_ID, token2),
            headers={"Timestamp": ts2},
            json={"projectId": 29490680},
            timeout=60
        )
        d2 = resp2.json()
        print(f"Stop result: {d2}")
        
        # Wait a moment
        import time as t
        print("Waiting 5 seconds...")
        t.sleep(5)
else:
    print(f"No live deployment found or error: {data.get('errors')}")

# ── Step 2: Delete the live algo if needed ───────────────────
ts, token_bytes = make_auth()
print("\n=== Step 2: Try to delete existing live algo ===")
resp = requests.post(
    f"{BASE_URL}/live/update/liquidate",
    auth=(USER_ID, token_bytes),
    headers={"Timestamp": ts},
    json={"projectId": 29490680},
    timeout=60
)
data = resp.json()
print(f"Liquidate result: {data}")

import time as t
print("Waiting 5 seconds...")
t.sleep(5)

# ── Step 3: Deploy with multipart/form-data ──────────────────
ts, token_bytes = make_auth()
print("\n=== Step 3: Deploy with multipart/form-data ===")

files_data = {
    'projectId': (None, '29490680'),
    'compileId': (None, '91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0'),
    'nodeId': (None, 'LN-64d4787830461ee45574254f643f69b3'),
    'automaticRedeploy': (None, 'true'),
    'versionId': (None, '-1'),
    'brokerage[id]': (None, 'InteractiveBrokersBrokerage'),
    'brokerage[ib-agent-description]': (None, 'Individual'),
    'brokerage[ib-trading-mode]': (None, 'paper'),
    'brokerage[ib-user-name]': (None, 'cesarmanuel81'),
    'brokerage[ib-account]': (None, 'DUM891854'),
    'brokerage[ib-password]': (None, 'Casiopea8102*'),
    'brokerage[ib-weekly-restart-utc-time]': (None, '22:00:00'),
    'brokerage[live-mode-brokerage]': (None, 'QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage'),
    'dataProviders[InteractiveBrokersBrokerage][id]': (None, 'InteractiveBrokersBrokerage'),
}

resp = requests.post(
    f"{BASE_URL}/live/create",
    auth=(USER_ID, token_bytes),
    headers={"Timestamp": ts},
    files=files_data,
    timeout=60
)

print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if data.get("success"):
        print(f"\n*** DEPLOY SUCCESSFUL! ***")
        print(f"Deploy ID: {data.get('deployId', 'N/A')}")
        print(f"Project ID: {data.get('projectId', 'N/A')}")
        print(f"Status: {data.get('status', 'N/A')}")
        print(json.dumps(data, indent=2))
    else:
        print(f"Errors: {data.get('errors')}")
        print(f"Full response: {json.dumps(data, indent=2)}")
except Exception as e:
    print(f"Body: {resp.text[:500]}")
    print(f"Error: {e}")
