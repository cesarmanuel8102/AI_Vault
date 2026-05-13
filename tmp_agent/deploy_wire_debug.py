"""
Intercept the exact HTTP request being sent to see the raw bytes on the wire.
Then try with urllib3 directly (lower level than requests).
"""
import json, time, hashlib, sys
import http.client

# Enable HTTP debug logging to see exact request/response
http.client.HTTPConnection.debuglevel = 1

import logging
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

import requests

with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]
ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()

URL = "https://www.quantconnect.com/api/v2/live/create"

# Build a minimal payload to test
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

# Let's check what json.dumps produces
body = json.dumps(payload)
# Find the restart-utc-time portion
idx = body.find("restart-utc-time")
print(f"\n=== JSON body around restart-utc-time ===")
print(body[idx-5:idx+50])
print(f"\nRaw bytes around that area:")
segment = body[idx-5:idx+50].encode("utf-8")
print(segment)
print(f"Hex: {segment.hex()}")

# Check if "22:00:00" in the serialized JSON
assert '"22:00:00"' in body, "COLON IS MISSING FROM JSON SERIALIZATION!"
print("\nCOLON present in serialized JSON body: YES")

# Now send with full debug
print("\n=== SENDING REQUEST ===")
resp = requests.post(
    URL,
    auth=(USER_ID, token_bytes),
    headers={"Timestamp": ts},
    json=payload,
    timeout=60
)
print(f"\nStatus: {resp.status_code}")
print(f"Response: {resp.text[:500]}")

# Now let's also check: does the auth token computation use colons?
# The hash is TOKEN:TIMESTAMP — if the hash computation or auth header
# somehow interacts with the body parsing...
print(f"\n=== AUTH DEBUG ===")
print(f"User-ID: {USER_ID}")
print(f"Timestamp: {ts}")
print(f"Token hash: {token_bytes[:20]}...")

# What does the Basic auth header look like?
import base64
auth_b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
print(f"Authorization header would be: Basic {auth_b64[:30]}...")

# The Auth header contains a colon too (user:hash). 
# Could the server be splitting on ALL colons in the request?
# That's the auth mechanism (Basic auth)... the colons in Basic auth
# are handled differently (Base64 encoded).
# But what if their custom parsing is doing something wrong?
