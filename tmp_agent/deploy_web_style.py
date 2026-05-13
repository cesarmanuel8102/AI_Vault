"""
Try to deploy by mimicking the QC Web UI request exactly.
The web UI uses AJAX calls with session cookies, not Basic auth.
Let's try:
1. Login via web to get session cookies
2. Send the deploy request with session cookies instead of Basic auth
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

# First, check current status
ts, tb = make_auth()
resp = requests.post(f"{BASE_URL}/live/read", auth=(USER_ID, tb), headers={"Timestamp": ts},
                     json={"projectId": 29490680}, timeout=60)
data = resp.json()
print(f"Current live status: {data.get('status', 'none')}")
print(f"Deploy ID: {data.get('deployId', 'none')}")

# Now try with session-based auth
# QC web UI might call a different internal endpoint
# Let's try the terminal API endpoint that the web UI uses
session = requests.Session()

# Try to authenticate via the API login endpoint
ts, tb = make_auth()
print("\n=== Trying web-style request with X-Requested-With header ===")

payload = {
    "projectId": 29490680,
    "compileId": "e87b3cf8b3296a662cc918e1b7923177-9f0bf8a6958660d525da37b0ed33412d",
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

# Try with typical web UI headers
resp = requests.post(
    f"{BASE_URL}/live/create",
    auth=(USER_ID, tb),
    headers={
        "Timestamp": ts,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Origin": "https://www.quantconnect.com",
        "Referer": "https://www.quantconnect.com/terminal/",
    },
    json=payload,
    timeout=60
)
print(f"Status: {resp.status_code}")
d = resp.json()
if d.get("success"):
    print(f"*** DEPLOY SUCCESSFUL! ***")
    print(json.dumps(d, indent=2))
else:
    print(f"Errors: {d.get('errors')}")

# Try with a different approach: PUT instead of POST?
print("\n=== Trying PUT method ===")
ts2, tb2 = make_auth()
resp2 = requests.put(
    f"{BASE_URL}/live/create",
    auth=(USER_ID, tb2),
    headers={"Timestamp": ts2},
    json=payload,
    timeout=60
)
print(f"Status: {resp2.status_code}")
try:
    d2 = resp2.json()
    if d2.get("success"):
        print(f"*** DEPLOY SUCCESSFUL! ***")
        print(json.dumps(d2, indent=2))
    else:
        print(f"Errors: {d2.get('errors')}")
except:
    print(f"Body: {resp2.text[:300]}")

# Try with brokerage values as a JSON-encoded string inside a form field
print("\n=== Trying: brokerage as JSON string in form field ===")
ts3, tb3 = make_auth()
brokerage_json = json.dumps({
    "id": "InteractiveBrokersBrokerage",
    "ib-agent-description": "Individual",
    "ib-trading-mode": "paper",
    "ib-user-name": "cesarmanuel81",
    "ib-account": "DUM891854",
    "ib-password": "Casiopea8102*",
    "ib-weekly-restart-utc-time": "22:00:00",
    "live-mode-brokerage": "QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"
})
dp_json = json.dumps({"InteractiveBrokersBrokerage": {"id": "InteractiveBrokersBrokerage"}})

form_data = {
    'projectId': '29490680',
    'compileId': 'e87b3cf8b3296a662cc918e1b7923177-9f0bf8a6958660d525da37b0ed33412d',
    'nodeId': 'LN-64d4787830461ee45574254f643f69b3',
    'automaticRedeploy': 'true',
    'versionId': '-1',
    'brokerage': brokerage_json,
    'dataProviders': dp_json,
}

resp3 = requests.post(
    f"{BASE_URL}/live/create",
    auth=(USER_ID, tb3),
    headers={"Timestamp": ts3},
    data=form_data,
    timeout=60
)
print(f"Status: {resp3.status_code}")
try:
    d3 = resp3.json()
    if d3.get("success"):
        print(f"*** DEPLOY SUCCESSFUL! ***")
        print(json.dumps(d3, indent=2))
    else:
        print(f"Errors: {d3.get('errors')}")
except:
    print(f"Body: {resp3.text[:300]}")
