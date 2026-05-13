"""
Upload main.py to existing project, compile, and launch backtest.
Project already created: 29652652
"""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# ── Step 1: Update main.py (already exists in new projects) ──
print("=== Step 1: Updating main.py ===")
with open("C:/AI_VAULT/tmp_agent/strategies/forex_v1/main.py", "r", encoding="utf-8") as f:
    code = f.read()

r = requests.post(f"{BASE}/files/update", headers=headers(), json={
    "projectId": PROJECT_ID,
    "name": "main.py",
    "content": code
})
data = r.json()
print(f"Update response: success={data.get('success')}")
if not data.get("success"):
    print(f"[ERROR] {data}")
    exit(1)
print("[OK] main.py updated")

# ── Step 2: Compile ──
print("\n=== Step 2: Compiling ===")
r = requests.post(f"{BASE}/compile/create", headers=headers(), json={
    "projectId": PROJECT_ID
})
data = r.json()
compile_id = data.get("compileId", "")
state = data.get("state", "")
print(f"Compile state: {state} | compileId: {compile_id}")

max_wait = 90
waited = 0
while state not in ["BuildSuccess", "BuildError"] and waited < max_wait:
    time.sleep(3)
    waited += 3
    r = requests.post(f"{BASE}/compile/read", headers=headers(), json={
        "projectId": PROJECT_ID,
        "compileId": compile_id
    })
    data = r.json()
    state = data.get("state", "")
    print(f"  ... compile state: {state} ({waited}s)")

if state != "BuildSuccess":
    print(f"\n[ERROR] Compilation failed!")
    print(f"Full response: {json.dumps(data, indent=2)}")
    exit(1)

print(f"[OK] Compilation successful! compileId={compile_id}")

# ── Step 3: Launch backtest ──
print("\n=== Step 3: Launching backtest ===")
r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
    "projectId": PROJECT_ID,
    "compileId": compile_id,
    "backtestName": "Forex V1.0 Baseline"
})
data = r.json()
print(f"Backtest response: success={data.get('success')}")

if not data.get("success"):
    print(f"[ERROR] Backtest launch failed: {json.dumps(data, indent=2)}")
    exit(1)

bt = data.get("backtest", {})
bt_id = bt.get("backtestId", "")
print(f"[OK] Backtest launched!")
print(f"  Name: {bt.get('name')}")
print(f"  ID: {bt_id}")
print(f"  Project: {PROJECT_ID}")

info = {
    "project_id": PROJECT_ID,
    "compile_id": compile_id,
    "backtest_id": bt_id,
    "backtest_name": "Forex V1.0 Baseline",
    "launched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
}
with open("C:/AI_VAULT/tmp_agent/strategies/forex_v1/backtest_info.json", "w") as f:
    json.dump(info, f, indent=2)
print(f"\n[SAVED] {json.dumps(info, indent=2)}")
