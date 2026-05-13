"""Deploy Fusion V1 to QC: upload, compile, launch backtest."""
import sys, time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

source_file = "C:/AI_VAULT/tmp_agent/strategies/fusion_v1/main.py"
bt_name = "Fusion V1 Yoel+Brain 40-60 AAPL-QQQ-NVDA-SPY 2023-2024"
params = {"start_year": "2023", "end_year": "2024", "end_month": "12"}

# Step 1: Set parameters
print("=== STEP 1: Set parameters ===")
param_list = [{"key": k, "value": v} for k, v in params.items()]
r = requests.post(f"{BASE}/projects/update", headers=headers(), json={
    "projectId": PROJECT_ID, "parameters": param_list
})
print(f"Result: {r.json().get('success', False)}")

# Step 2: Upload code
print("\n=== STEP 2: Upload code ===")
with open(source_file, "r", encoding="utf-8") as f:
    code = f.read()
print(f"Code length: {len(code)} chars")
r = requests.post(f"{BASE}/files/update", headers=headers(), json={
    "projectId": PROJECT_ID, "name": "main.py", "content": code
})
resp = r.json()
print(f"Result: {resp.get('success', False)}")
if not resp.get("success"):
    print(f"Error: {resp}")
    # Try creating the file instead
    r = requests.post(f"{BASE}/files/create", headers=headers(), json={
        "projectId": PROJECT_ID, "name": "main.py", "content": code
    })
    resp = r.json()
    print(f"Create result: {resp.get('success', False)}")

# Step 3: Compile
print("\n=== STEP 3: Compile ===")
r = requests.post(f"{BASE}/compile/create", headers=headers(), json={"projectId": PROJECT_ID})
data = r.json()
cid = data.get("compileId", "")
state = data.get("state", "")
print(f"Initial state: {state}, compileId: {cid}")

waited = 0
while state not in ["BuildSuccess", "BuildError"] and waited < 90:
    time.sleep(3)
    waited += 3
    r = requests.post(f"{BASE}/compile/read", headers=headers(), json={
        "projectId": PROJECT_ID, "compileId": cid
    })
    data = r.json()
    state = data.get("state", "")
    print(f"  [{waited}s] State: {state}")

if state != "BuildSuccess":
    print(f"\nCOMPILE FAILED!")
    print(json.dumps(data, indent=2))
    sys.exit(1)

print(f"\nCompile SUCCESS: {cid}")

# Step 4: Launch backtest
print("\n=== STEP 4: Launch backtest ===")
r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
    "projectId": PROJECT_ID, "compileId": cid, "backtestName": bt_name
})
data = r.json()
bt = data.get("backtest", {})
bt_id = bt.get("backtestId", "")
print(f"Launched: {bt_id}")
print(f"Name: {bt_name}")

if not data.get("success"):
    print(f"ERROR: {json.dumps(data, indent=2)}")
    sys.exit(1)

# Save bt_id
bt_info = {"bt_id": bt_id, "bt_name": bt_name, "project_id": PROJECT_ID, "strategy": "fusion_v1"}
with open("C:/AI_VAULT/tmp_agent/strategies/fusion_v1/current_bt.json", "w") as f:
    json.dump(bt_info, f, indent=2)
print(f"\nSaved bt_id to fusion_v1/current_bt.json")
print("Backtest is running. Poll for status.")
