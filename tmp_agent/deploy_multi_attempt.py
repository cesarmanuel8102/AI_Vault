"""
Deploy V10.13b — trying multiple HTTP clients and encoding strategies
to work around the QC API bug with colons in ib-weekly-restart-utc-time.
"""
import json, time, hashlib, sys

# Credentials
with open("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json") as f:
    qc = json.load(f)
USER_ID = qc["user_id"]
TOKEN   = qc["token"]
ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()

PAYLOAD = {
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

URL = "https://www.quantconnect.com/api/v2/live/create"

def try_httpx():
    """Try with httpx library"""
    try:
        import httpx
    except ImportError:
        print("httpx not installed, installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
        import httpx
    
    print("=== ATTEMPT: httpx with json= ===")
    client = httpx.Client()
    resp = client.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts},
        json=PAYLOAD,
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if not data.get("success"):
        print(f"Errors: {data.get('errors')}")
    else:
        print(f"DEPLOY OK! {data}")
    return data.get("success", False)

def try_requests_manual_body():
    """Try with requests but manually serialized body and explicit content-type"""
    import requests
    
    print("\n=== ATTEMPT: requests with data=json.dumps (manual serialize) ===")
    body = json.dumps(PAYLOAD, separators=(',', ':'))  # compact JSON, no spaces
    print(f"Body excerpt: ...restart-utc-time{body[body.find('restart-utc-time'):][:80]}...")
    
    resp = requests.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts, "Content-Type": "application/json"},
        data=body.encode("utf-8"),
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if not data.get("success"):
        print(f"Errors: {data.get('errors')}")
    else:
        print(f"DEPLOY OK! {data}")
    return data.get("success", False)

def try_requests_double_encoded():
    """Try with brokerage as a JSON string (double-encoded)"""
    import requests
    
    print("\n=== ATTEMPT: brokerage as JSON string (double-encoded) ===")
    payload_alt = dict(PAYLOAD)
    payload_alt["brokerage"] = json.dumps(PAYLOAD["brokerage"])
    payload_alt["dataProviders"] = json.dumps(PAYLOAD["dataProviders"])
    
    resp = requests.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts},
        json=payload_alt,
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if not data.get("success"):
        print(f"Errors: {data.get('errors')}")
    else:
        print(f"DEPLOY OK! {data}")
    return data.get("success", False)

def try_flat_params():
    """Try flattening brokerage keys to top-level with brokerage. prefix"""
    import requests
    
    print("\n=== ATTEMPT: flat brokerage keys at top level ===")
    payload_flat = {
        "projectId": PAYLOAD["projectId"],
        "compileId": PAYLOAD["compileId"],
        "nodeId": PAYLOAD["nodeId"],
        "automaticRedeploy": True,
        "versionId": -1,
    }
    for k, v in PAYLOAD["brokerage"].items():
        payload_flat[f"brokerage[{k}]"] = v
    for k, v in PAYLOAD["dataProviders"]["InteractiveBrokersBrokerage"].items():
        payload_flat[f"dataProviders[InteractiveBrokersBrokerage][{k}]"] = v
    
    resp = requests.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts},
        json=payload_flat,
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if not data.get("success"):
        print(f"Errors: {data.get('errors')}")
    else:
        print(f"DEPLOY OK! {data}")
    return data.get("success", False)

def try_without_restart_time():
    """Try WITHOUT ib-weekly-restart-utc-time — maybe the API has a default?"""
    import requests
    
    print("\n=== ATTEMPT: WITHOUT ib-weekly-restart-utc-time (let server default) ===")
    payload_no_restart = dict(PAYLOAD)
    brokerage_no_restart = dict(PAYLOAD["brokerage"])
    del brokerage_no_restart["ib-weekly-restart-utc-time"]
    payload_no_restart["brokerage"] = brokerage_no_restart
    
    resp = requests.post(
        URL,
        auth=(USER_ID, token_bytes),
        headers={"Timestamp": ts},
        json=payload_no_restart,
        timeout=60
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if not data.get("success"):
        print(f"Errors: {data.get('errors')}")
    else:
        print(f"DEPLOY OK! {data}")
    return data.get("success", False)


# ── Run all attempts ─────────────────────────────────────────
if try_httpx():
    print("\n*** httpx worked! ***")
    sys.exit(0)

# Fresh timestamp for each attempt
ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
if try_requests_manual_body():
    print("\n*** manual body worked! ***")
    sys.exit(0)

ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
if try_without_restart_time():
    print("\n*** omitting restart time worked! ***")
    sys.exit(0)

ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
if try_requests_double_encoded():
    print("\n*** double-encoded worked! ***")
    sys.exit(0)

ts = str(int(time.time()))
token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
if try_flat_params():
    print("\n*** flat params worked! ***")
    sys.exit(0)

print("\n--- All attempts failed ---")
