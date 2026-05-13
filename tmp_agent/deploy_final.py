"""
Deploy V10.13b to QC Live using multipart/form-data (bypasses colon bug).
Fresh compile first, then deploy.
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

# Step 1: Check status
ts, tb = make_auth()
print("=== Checking live status ===")
resp = requests.post(f"{BASE_URL}/live/read", auth=(USER_ID, tb), headers={"Timestamp": ts},
                     json={"projectId": 29490680}, timeout=60)
data = resp.json()
status = data.get("status", "none")
print(f"Current status: {status}")

if status in ["Running", "LoggingIn", "Initializing"]:
    print("Still running, stopping first...")
    ts, tb = make_auth()
    resp = requests.post(f"{BASE_URL}/live/update/stop", auth=(USER_ID, tb), headers={"Timestamp": ts},
                         json={"projectId": 29490680}, timeout=60)
    print(f"Stop: {resp.json()}")
    print("Waiting 90 seconds...")
    time.sleep(90)

# Step 2: Fresh compile
ts, tb = make_auth()
print("\n=== Fresh compile ===")
resp = requests.post(f"{BASE_URL}/compile/create", auth=(USER_ID, tb), headers={"Timestamp": ts},
                     json={"projectId": 29490680}, timeout=120)
compile_data = resp.json()
print(f"Compile success: {compile_data.get('success')}")
compile_id = compile_data.get("compileId", "")
compile_state = compile_data.get("state", "")
print(f"Compile ID: {compile_id}")
print(f"State: {compile_state}")

if compile_state != "BuildSuccess":
    print("Compile not yet done, waiting...")
    for _ in range(10):
        time.sleep(5)
        ts, tb = make_auth()
        resp = requests.post(f"{BASE_URL}/compile/read", auth=(USER_ID, tb), headers={"Timestamp": ts},
                             json={"projectId": 29490680, "compileId": compile_id}, timeout=60)
        cd = resp.json()
        compile_state = cd.get("state", "")
        print(f"  State: {compile_state}")
        if compile_state == "BuildSuccess":
            break

if compile_state != "BuildSuccess":
    print("ERROR: Compile failed!")
    exit(1)

print(f"\nUsing compile ID: {compile_id}")

# Step 3: Deploy with multipart/form-data
ts, tb = make_auth()
print("\n=== Deploy with multipart/form-data ===")

files_data = {
    'projectId': (None, '29490680'),
    'compileId': (None, compile_id),
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
    f"{BASE_URL}/live/create",
    auth=(USER_ID, tb),
    headers={"Timestamp": ts},
    files=files_data,
    timeout=120
)

print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if data.get("success"):
        print(f"\n*** V10.13b LIVE DEPLOY SUCCESSFUL! ***")
        print(f"Deploy ID: {data.get('deployId', 'N/A')}")
        print(f"Status: {data.get('status', 'N/A')}")
        print(json.dumps(data, indent=2))
    else:
        print(f"Errors: {data.get('errors')}")
        print(f"Full: {json.dumps(data, indent=2)}")
except Exception as e:
    print(f"Body: {resp.text[:500]}")
    print(f"Error: {e}")

# Step 4: Verify deployment
time.sleep(10)
ts, tb = make_auth()
print("\n=== Verify deployment ===")
resp = requests.post(f"{BASE_URL}/live/read", auth=(USER_ID, tb), headers={"Timestamp": ts},
                     json={"projectId": 29490680}, timeout=60)
data = resp.json()
print(f"Status: {data.get('status')}")
print(f"Deploy ID: {data.get('deployId')}")
print(f"Launched: {data.get('launched')}")
