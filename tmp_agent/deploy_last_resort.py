"""
Last resort: Try QC API v2 with different approach:
1. Maybe there's a project-level setting we can set first, then deploy without the time
2. Try v1 of the API
3. Try different Content-Type 
"""
import json, time, hashlib, requests

with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]

def make_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    return ts, token_bytes

URL = "https://www.quantconnect.com/api/v2/live/create"

# Attempt: multipart/form-data with the brokerage values flattened
ts, token_bytes = make_auth()
print("=== multipart/form-data with nested keys ===")

# Build multipart data
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
    URL,
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
        print(f"DEPLOY OK! {json.dumps(data, indent=2)}")
    else:
        print(f"Errors: {data.get('errors')}")
except:
    print(f"Body: {resp.text[:500]}")

# Attempt: Send as application/x-www-form-urlencoded with PHP-style nested keys
ts, token_bytes = make_auth()
print("\n=== application/x-www-form-urlencoded PHP-style ===")

form_data = [
    ('projectId', '29490680'),
    ('compileId', '91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0'),
    ('nodeId', 'LN-64d4787830461ee45574254f643f69b3'),
    ('automaticRedeploy', 'true'),
    ('versionId', '-1'),
    ('brokerage[id]', 'InteractiveBrokersBrokerage'),
    ('brokerage[ib-agent-description]', 'Individual'),
    ('brokerage[ib-trading-mode]', 'paper'),
    ('brokerage[ib-user-name]', 'cesarmanuel81'),
    ('brokerage[ib-account]', 'DUM891854'),
    ('brokerage[ib-password]', 'Casiopea8102*'),
    ('brokerage[ib-weekly-restart-utc-time]', '22:00:00'),
    ('brokerage[live-mode-brokerage]', 'QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage'),
    ('dataProviders[InteractiveBrokersBrokerage][id]', 'InteractiveBrokersBrokerage'),
]

resp = requests.post(
    URL,
    auth=(USER_ID, token_bytes),
    headers={"Timestamp": ts},
    data=form_data,
    timeout=60
)
print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if data.get("success"):
        print(f"DEPLOY OK! {json.dumps(data, indent=2)}")
    else:
        print(f"Errors: {data.get('errors')}")
except:
    print(f"Body: {resp.text[:500]}")

# Attempt: QC Web UI endpoint (maybe different from API endpoint)
# The web UI might use a different internal endpoint
ts, token_bytes = make_auth()
print("\n=== Try /live/create with session cookie style ===")
# First get the QC website to see if there's a different deploy endpoint
session = requests.Session()
session.auth = (USER_ID, token_bytes)
session.headers.update({"Timestamp": ts})

# Check if there's a /live/deploy endpoint instead of /live/create
alt_url = "https://www.quantconnect.com/api/v2/live/deploy"
payload = {
    "projectId": 29490680,
    "compileId": "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0",
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": {
        "id": "InteractiveBrokersBrokerage",
        "ib-agent-description": "Individual",
        "ib-trading-mode": "paper",
        "ib-user-name": "cesarmanuel81",
        "ib-account": "DUM891854",
        "ib-password": "Casiopea8102*",
        "ib-weekly-restart-utc-time": "22:00:00",
        "live-mode-brokerage": "QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"
    },
    "dataProviders": {
        "InteractiveBrokersBrokerage": {
            "id": "InteractiveBrokersBrokerage"
        }
    },
    "automaticRedeploy": True,
    "versionId": -1
}

resp = session.post(alt_url, json=payload, timeout=60)
print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if data.get("success"):
        print(f"DEPLOY OK! {json.dumps(data, indent=2)}")
    else:
        print(f"Errors: {data.get('errors')}")
except:
    print(f"Body: {resp.text[:300]}")
