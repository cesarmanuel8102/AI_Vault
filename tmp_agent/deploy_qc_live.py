"""Deploy V10.13b — try raw JSON string to avoid colon parsing issues."""
import json
import hashlib
import time
from base64 import b64encode
import requests

USER_ID = "384945"
API_TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE_URL = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
COMPILE_ID = "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0"

def get_headers():
    timestamp = f"{int(time.time())}"
    time_stamped_token = f"{API_TOKEN}:{timestamp}".encode("utf-8")
    hashed_token = hashlib.sha256(time_stamped_token).hexdigest()
    authentication = f"{USER_ID}:{hashed_token}".encode("utf-8")
    authentication = b64encode(authentication).decode("ascii")
    return {
        "Authorization": f"Basic {authentication}",
        "Timestamp": timestamp,
        "Content-Type": "application/json",
    }

payload = {
    "versionId": "-1",
    "projectId": PROJECT_ID,
    "compileId": COMPILE_ID,
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": {
        "id": "InteractiveBrokersBrokerage",
        "ib-user-name": "cesarmanuel81",
        "ib-account": "DUM891854",
        "ib-password": "Casiopea8102*",
        "ib-weekly-restart-utc-time": "22:00:00"
    },
    "dataProviders": {
        "InteractiveBrokersBrokerage": {
            "id": "InteractiveBrokersBrokerage"
        }
    }
}

# Try 1: raw JSON string with explicit Content-Type
print("=== Try 1: data=json.dumps() with Content-Type: application/json ===")
body_str = json.dumps(payload)
print(f"Body includes weekly-restart: {'22:00:00' in body_str}")
resp = requests.post(
    f"{BASE_URL}/live/create",
    headers=get_headers(),
    data=body_str,
    timeout=60
)
data = resp.json()
print(f"Success: {data.get('success')}")
print(f"Errors: {data.get('errors')}")

if not data.get("success"):
    # Try 2: use form-urlencoded with flat params
    print("\n=== Try 2: Flat brokerage params at top level ===")
    flat_payload = {
        "versionId": "-1",
        "projectId": PROJECT_ID,
        "compileId": COMPILE_ID,
        "nodeId": "LN-64d4787830461ee45574254f643f69b3",
        "brokerage[id]": "InteractiveBrokersBrokerage",
        "brokerage[ib-user-name]": "cesarmanuel81",
        "brokerage[ib-account]": "DUM891854",
        "brokerage[ib-password]": "Casiopea8102*",
        "brokerage[ib-weekly-restart-utc-time]": "22:00:00",
        "dataProviders[InteractiveBrokersBrokerage][id]": "InteractiveBrokersBrokerage",
    }
    h2 = get_headers()
    del h2["Content-Type"]  # let requests set it
    resp2 = requests.post(
        f"{BASE_URL}/live/create",
        headers=h2,
        data=flat_payload,
        timeout=60
    )
    data2 = resp2.json()
    print(f"Success: {data2.get('success')}")
    print(f"Errors: {data2.get('errors')}")
    if data2.get("success"):
        print(f"deployId: {data2.get('deployId')}")
    else:
        print(json.dumps(data2, indent=2))

if not data.get("success"):
    # Try 3: encode time with unicode escape
    print("\n=== Try 3: Time with escaped colons ===")
    payload3 = dict(payload)
    payload3["brokerage"] = dict(payload["brokerage"])
    payload3["brokerage"]["ib-weekly-restart-utc-time"] = "22\u003a00\u003a00"
    resp3 = requests.post(
        f"{BASE_URL}/live/create",
        headers=get_headers(),
        json=payload3,
        timeout=60
    )
    data3 = resp3.json()
    print(f"Success: {data3.get('success')}")
    print(f"Errors: {data3.get('errors')}")
