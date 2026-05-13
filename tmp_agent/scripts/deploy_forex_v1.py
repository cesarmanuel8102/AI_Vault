"""
Create QC Forex project, upload main.py, compile, and launch backtest.
"""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# ── Step 1: Create project ──
print("=== Step 1: Creating QC project ===")
r = requests.post(f"{BASE}/projects/create", headers=headers(), json={
    "name": "Brain V9 Forex V1",
    "language": "Py"
})
data = r.json()
print(f"Response: {json.dumps(data, indent=2)}")

if not data.get("success"):
    print(f"[ERROR] Failed to create project: {data}")
    exit(1)

project_id = data["projects"][0]["projectId"]
print(f"[OK] Project created: ID={project_id}")

# ── Step 2: Upload main.py ──
print("\n=== Step 2: Uploading main.py ===")
with open("C:/AI_VAULT/tmp_agent/strategies/forex_v1/main.py", "r", encoding="utf-8") as f:
    code = f.read()

r = requests.post(f"{BASE}/files/create", headers=headers(), json={
    "projectId": project_id,
    "name": "main.py",
    "content": code
})
data = r.json()
print(f"Upload response success: {data.get('success')}")

if not data.get("success"):
    print(f"[ERROR] Upload failed: {data}")
    exit(1)
print("[OK] main.py uploaded")

# ── Step 3: Compile ──
print("\n=== Step 3: Compiling ===")
r = requests.post(f"{BASE}/compile/create", headers=headers(), json={
    "projectId": project_id
})
data = r.json()
compile_id = data.get("compileId", "")
state = data.get("state", "")
print(f"Compile state: {state} | compileId: {compile_id}")

# Poll for compilation to finish
max_wait = 60
waited = 0
while state not in ["BuildSuccess", "BuildError"] and waited < max_wait:
    time.sleep(3)
    waited += 3
    r = requests.post(f"{BASE}/compile/read", headers=headers(), json={
        "projectId": project_id,
        "compileId": compile_id
    })
    data = r.json()
    state = data.get("state", "")
    print(f"  ... compile state: {state} ({waited}s)")

if state != "BuildSuccess":
    print(f"\n[ERROR] Compilation failed!")
    print(f"Errors: {json.dumps(data.get('errors', []), indent=2)}")
    print(f"Logs: {json.dumps(data.get('logs', []), indent=2)}")
    exit(1)

print(f"[OK] Compilation successful! compileId={compile_id}")

# ── Step 4: Launch backtest ──
print("\n=== Step 4: Launching backtest ===")
r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
    "projectId": project_id,
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
print(f"  Project: {project_id}")
print(f"  Progress: {bt.get('progress', 0)*100:.0f}%")

# Save info for later
info = {
    "project_id": project_id,
    "compile_id": compile_id,
    "backtest_id": bt_id,
    "backtest_name": "Forex V1.0 Baseline",
    "launched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
}
with open("C:/AI_VAULT/tmp_agent/strategies/forex_v1/backtest_info.json", "w") as f:
    json.dump(info, f, indent=2)
print(f"\n[SAVED] Backtest info -> forex_v1/backtest_info.json")
print(json.dumps(info, indent=2))
