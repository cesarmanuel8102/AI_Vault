"""
Final debug: test if the password with * is corrupting the JSON parse,
and try URL-encoded colons and other escaping strategies.
"""
import json, time, hashlib, requests

with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]

URL = "https://www.quantconnect.com/api/v2/live/create"

def make_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    return ts, token_bytes

def attempt(name, payload):
    ts, token_bytes = make_auth()
    print(f"\n=== {name} ===")
    resp = requests.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts},
        json=payload,
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(f"Success: {data.get('success')}")
        if data.get("success"):
            print(f"*** DEPLOY OK! ***")
            print(json.dumps(data, indent=2))
            return True
        else:
            errs = data.get("errors", [])
            print(f"Errors: {errs}")
    except:
        print(f"Body: {resp.text[:500]}")
    return False

BASE_BROKERAGE = {
    "id": "InteractiveBrokersBrokerage",
    "ib-agent-description": "Individual",
    "ib-trading-mode": "paper",
    "ib-user-name": "cesarmanuel81",
    "ib-account": "DUM891854",
    "ib-password": "Casiopea8102*",
    "live-mode-brokerage": "QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"
}

BASE_PAYLOAD = {
    "projectId": 29490680,
    "compileId": "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0",
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "dataProviders": {
        "InteractiveBrokersBrokerage": {
            "id": "InteractiveBrokersBrokerage"
        }
    },
    "automaticRedeploy": True,
    "versionId": -1
}

# Attempt 1: Try with a dummy password (no special chars)
brok = dict(BASE_BROKERAGE)
brok["ib-password"] = "TestPassword123"
brok["ib-weekly-restart-utc-time"] = "22:00:00"
p = dict(BASE_PAYLOAD)
p["brokerage"] = brok
attempt("Dummy password (no special chars) + 22:00:00", p)

# Attempt 2: Put ib-weekly-restart-utc-time BEFORE ib-password
from collections import OrderedDict
brok2 = OrderedDict([
    ("id", "InteractiveBrokersBrokerage"),
    ("ib-agent-description", "Individual"),
    ("ib-trading-mode", "paper"),
    ("ib-user-name", "cesarmanuel81"),
    ("ib-account", "DUM891854"),
    ("ib-weekly-restart-utc-time", "22:00:00"),
    ("ib-password", "Casiopea8102*"),
    ("live-mode-brokerage", "QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage")
])
p2 = dict(BASE_PAYLOAD)
p2["brokerage"] = dict(brok2)
attempt("restart-time BEFORE password", p2)

# Attempt 3: Integer time like 220000
brok3 = dict(BASE_BROKERAGE)
brok3["ib-weekly-restart-utc-time"] = 220000
p3 = dict(BASE_PAYLOAD)
p3["brokerage"] = brok3
attempt("Time as integer 220000", p3)

# Attempt 4: Time as "22.00.00" (dots instead of colons)
brok4 = dict(BASE_BROKERAGE)
brok4["ib-weekly-restart-utc-time"] = "22.00.00"
p4 = dict(BASE_PAYLOAD)
p4["brokerage"] = brok4
attempt("Time with dots 22.00.00", p4)

# Attempt 5: Time just "22" 
brok5 = dict(BASE_BROKERAGE)
brok5["ib-weekly-restart-utc-time"] = "22"
p5 = dict(BASE_PAYLOAD)
p5["brokerage"] = brok5
attempt("Time as just '22'", p5)

# Attempt 6: Different URL format — maybe /live/create/? or /live/create
# Actually, let's try sending the body as form data rather than JSON
import time as t
ts6 = str(int(t.time()))
token6 = hashlib.sha256(f"{TOKEN}:{ts6}".encode()).hexdigest()
brok6 = dict(BASE_BROKERAGE)
brok6["ib-weekly-restart-utc-time"] = "22:00:00"
p6 = dict(BASE_PAYLOAD)
p6["brokerage"] = brok6
print(f"\n=== form-encoded (not JSON) ===")
# Convert nested dict to form-data style
form_data = {}
for k, v in p6.items():
    if isinstance(v, dict):
        if k == "brokerage":
            for bk, bv in v.items():
                form_data[f"brokerage[{bk}]"] = str(bv)
        elif k == "dataProviders":
            for dk, dv in v.items():
                for dk2, dv2 in dv.items():
                    form_data[f"dataProviders[{dk}][{dk2}]"] = str(dv2)
    else:
        form_data[k] = str(v)

resp6 = requests.post(
    URL,
    auth=(USER_ID, token6),
    headers={"Timestamp": ts6},
    data=form_data,
    timeout=60
)
print(f"Status: {resp6.status_code}")
try:
    d6 = resp6.json()
    print(f"Success: {d6.get('success')}")
    if d6.get("success"):
        print(f"*** DEPLOY OK! ***")
        print(json.dumps(d6, indent=2))
    else:
        print(f"Errors: {d6.get('errors')}")
except:
    print(f"Body: {resp6.text[:500]}")
