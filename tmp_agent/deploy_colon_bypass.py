"""
Try to bypass the QC colon-stripping bug with various encoding tricks.
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
    brok = dict(BASE_BROKERAGE)
    brok["ib-weekly-restart-utc-time"] = time_val
    p = dict(BASE_PAYLOAD)
    p["brokerage"] = brok
    
    if raw_body:
        # Send raw body with manual JSON
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

# Test 1: URL-encoded colons %3A
attempt("URL-encoded %3A", "22%3A00%3A00")

# Test 2: Unicode full-width colon
attempt("Unicode fullwidth colon", "22\uff1a00\uff1a00")

# Test 3: Try with raw body where we literally have the JSON but use \\u003a 
raw = json.dumps(BASE_PAYLOAD)
# Manually construct JSON with unicode escape for colon in the time field
brok_json = json.dumps(BASE_BROKERAGE)
brok_json_esc = brok_json  # base without time
p_full = dict(BASE_PAYLOAD)
brok_full = dict(BASE_BROKERAGE)
brok_full["ib-weekly-restart-utc-time"] = "PLACEHOLDER"
p_full["brokerage"] = brok_full
raw_json = json.dumps(p_full)
# Replace the placeholder with unicode-escaped colons
raw_json = raw_json.replace("PLACEHOLDER", "22\\u003a00\\u003a00")
print(f"\nRaw JSON time portion: ...{raw_json[raw_json.find('restart'):raw_json.find('restart')+70]}...")
attempt("Unicode escape \\u003a in raw body", "dummy", raw_body=raw_json)

# Test 4: TimeSpan format "0.22:00:00" (days.hours:min:sec)
attempt("TimeSpan 0.22:00:00", "0.22:00:00")

# Test 5: HTML entity &#58;
attempt("HTML entity &#58;", "22&#58;00&#58;00")

# Test 6: Just the default 21:00:00 from the module config
attempt("Default 21:00:00", "21:00:00")
