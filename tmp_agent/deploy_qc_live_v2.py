"""
Deploy V10.13b to QC Live — matching LEAN CLI payload exactly.
Previous attempts failed because brokerage dict was missing:
  - ib-agent-description
  - ib-trading-mode 
  - live-mode-brokerage
"""
import json, time, hashlib, requests, sys

# ── Credentials ──────────────────────────────────────────────
with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]

# ── QC Auth ──────────────────────────────────────────────────
ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()

headers = {
    "Timestamp": ts,
    "Content-Type": "application/json",
}

# ── Deploy payload (matching LEAN CLI exactly) ───────────────
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

print("=== PAYLOAD ===")
print(json.dumps(payload, indent=2))
print()

# ── Send request ─────────────────────────────────────────────
url = "https://www.quantconnect.com/api/v2/live/create"
resp = requests.post(
    url,
    auth=(USER_ID, token_bytes),
    headers=headers,
    json=payload,
    timeout=60
)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:2000]}")

data = resp.json()
if data.get("success"):
    print("\n✅ DEPLOY SUCCESSFUL!")
    print(f"   Deploy ID: {data.get('deployId', 'N/A')}")
    print(f"   Project ID: {data.get('projectId', 29490680)}")
    print(f"   Status: {data.get('status', 'N/A')}")
else:
    print(f"\n❌ DEPLOY FAILED")
    print(f"   Errors: {data.get('errors', [])}")
    print(f"   Messages: {data.get('messages', [])}")
