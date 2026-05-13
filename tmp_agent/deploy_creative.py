"""
More creative attempts to get colons through QC's parser.
Key insight: "0.22:00:00" survived, meaning colons don't get stripped universally.
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

def attempt(name, time_val, raw_body=None):
    ts, token_bytes = make_auth()
    print(f"\n=== {name} ===")
    print(f"  Value: repr={repr(time_val)}")
    brok = dict(BASE_BROKERAGE)
    brok["ib-weekly-restart-utc-time"] = time_val
    p = dict(BASE_PAYLOAD)
    p["brokerage"] = brok
    
    if raw_body:
        resp = requests.post(
            URL,
            auth=(USER_ID, token_bytes),
            headers={"Timestamp": ts, "Content-Type": "application/json"},
            data=raw_body.encode("utf-8"),
            timeout=60
        )
    else:
        resp = requests.post(
            URL,
            auth=(USER_ID, token_bytes),
            headers={"Timestamp": ts},
            json=p,
            timeout=60
        )
    
    print(f"  Status: {resp.status_code}")
    try:
        data = resp.json()
        if data.get("success"):
            print(f"  *** DEPLOY OK! ***")
            print(f"  {json.dumps(data, indent=2)}")
            return True
        else:
            errs = data.get("errors", [])
            for e in errs:
                print(f"  Error: {e}")
    except:
        print(f"  Body: {resp.text[:500]}")
    return False

# 1. Space before: " 22:00:00"
attempt("Leading space", " 22:00:00")

# 2. Space after: "22:00:00 "
attempt("Trailing space", "22:00:00 ")

# 3. Zero-width space before: "\u200b22:00:00"
attempt("Zero-width space before", "\u200b22:00:00")

# 4. Raw body with literal colon but different JSON library (orjson)
# Actually let's try raw body with manually crafted JSON 
# where the value is explicitly "22:00:00"
raw = '{"projectId":29490680,"compileId":"91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0","nodeId":"LN-64d4787830461ee45574254f643f69b3","brokerage":{"id":"InteractiveBrokersBrokerage","ib-agent-description":"Individual","ib-trading-mode":"paper","ib-user-name":"cesarmanuel81","ib-account":"DUM891854","ib-password":"Casiopea8102*","ib-weekly-restart-utc-time":"22:00:00","live-mode-brokerage":"QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"},"dataProviders":{"InteractiveBrokersBrokerage":{"id":"InteractiveBrokersBrokerage"}},"automaticRedeploy":true,"versionId":-1}'
# Verify our JSON is valid
parsed = json.loads(raw)
assert parsed["brokerage"]["ib-weekly-restart-utc-time"] == "22:00:00"
attempt("Hand-crafted raw JSON", "dummy", raw_body=raw)

# 5. Try with HTTPS basic auth directly in URL (bypassing requests auth)
ts5, token5 = make_auth()
brok5 = dict(BASE_BROKERAGE)
brok5["ib-weekly-restart-utc-time"] = "22:00:00"
p5 = dict(BASE_PAYLOAD)
p5["brokerage"] = brok5
print(f"\n=== Auth in URL directly ===")
import base64
auth_str = base64.b64encode(f"{USER_ID}:{token5}".encode()).decode()
resp5 = requests.post(
    URL,
    headers={
        "Timestamp": ts5,
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json; charset=utf-8"
    },
    data=json.dumps(p5).encode("utf-8"),
    timeout=60
)
print(f"  Status: {resp5.status_code}")
try:
    d5 = resp5.json()
    if d5.get("success"):
        print(f"  *** DEPLOY OK! ***")
    else:
        for e in d5.get("errors", []):
            print(f"  Error: {e}")
except:
    print(f"  Body: {resp5.text[:500]}")

# 6. Time with T prefix: "T22:00:00"
attempt("T-prefix T22:00:00", "T22:00:00")

# 7. Check if QC Community/forums have this issue
# 8. Try the LEAN CLI directly via subprocess
print("\n\n=== LEAN CLI CONFIG + DEPLOY (subprocess) ===")
import subprocess

# First, configure lean with our QC creds
result = subprocess.run(
    ["lean", "login", "--user-id", USER_ID, "--api-token", "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"],
    capture_output=True, text=True, timeout=30
)
print(f"lean login: {result.stdout.strip()} {result.stderr.strip()}")
