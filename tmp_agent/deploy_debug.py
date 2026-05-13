"""Test if password * causes parsing issue."""
import json
import hashlib
import time
from base64 import b64encode
import requests

USER_ID = "384945"
API_TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE_URL = "https://www.quantconnect.com/api/v2"

def get_headers():
    timestamp = f"{int(time.time())}"
    hashed_token = hashlib.sha256(f"{API_TOKEN}:{timestamp}".encode()).hexdigest()
    auth_b64 = b64encode(f"{USER_ID}:{hashed_token}".encode()).decode("ascii")
    return {"Authorization": f"Basic {auth_b64}", "Timestamp": timestamp}

COMPILE_ID = "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0"

# Test 1: password WITHOUT * to see if the error changes
print("=== Test 1: password without * ===")
payload1 = {
    "versionId": "-1", "projectId": 29490680, "compileId": COMPILE_ID,
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": {
        "id": "InteractiveBrokersBrokerage",
        "ib-user-name": "cesarmanuel81",
        "ib-account": "DUM891854",
        "ib-password": "TestPass123",
        "ib-weekly-restart-utc-time": "22:00:00"
    },
    "dataProviders": {"InteractiveBrokersBrokerage": {"id": "InteractiveBrokersBrokerage"}}
}
r1 = requests.post(f"{BASE_URL}/live/create", headers=get_headers(), json=payload1, timeout=60)
print(json.dumps(r1.json(), indent=2))

# Test 2: move restart time BEFORE password
print("\n=== Test 2: restart time before password in dict ===")
from collections import OrderedDict
brokerage2 = OrderedDict([
    ("id", "InteractiveBrokersBrokerage"),
    ("ib-user-name", "cesarmanuel81"),
    ("ib-account", "DUM891854"),
    ("ib-weekly-restart-utc-time", "22:00:00"),
    ("ib-password", "Casiopea8102*"),
])
payload2 = {
    "versionId": "-1", "projectId": 29490680, "compileId": COMPILE_ID,
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": dict(brokerage2),
    "dataProviders": {"InteractiveBrokersBrokerage": {"id": "InteractiveBrokersBrokerage"}}
}
r2 = requests.post(f"{BASE_URL}/live/create", headers=get_headers(), json=payload2, timeout=60)
print(json.dumps(r2.json(), indent=2))

# Test 3: different key name (try ib-restart-utc-time, ibWeeklyRestartUtcTime)
print("\n=== Test 3: Try camelCase key name ===")
payload3 = {
    "versionId": "-1", "projectId": 29490680, "compileId": COMPILE_ID,
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": {
        "id": "InteractiveBrokersBrokerage",
        "ib-user-name": "cesarmanuel81",
        "ib-account": "DUM891854",
        "ib-password": "Casiopea8102*",
        "ib-weekly-restart-utc-time": "22:00:00",
        "ibWeeklyRestartUtcTime": "22:00:00",
        "weeklyRestartUtcTime": "22:00:00",
    },
    "dataProviders": {"InteractiveBrokersBrokerage": {"id": "InteractiveBrokersBrokerage"}}
}
r3 = requests.post(f"{BASE_URL}/live/create", headers=get_headers(), json=payload3, timeout=60)
print(json.dumps(r3.json(), indent=2))
