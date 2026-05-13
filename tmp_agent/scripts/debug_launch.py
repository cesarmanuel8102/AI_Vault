"""Quick test: try to launch a single backtest and see the full error."""
import json, time, hashlib, base64, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680

def get_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}

BASE = "https://www.quantconnect.com/api/v2"

# First compile
print("Compiling...")
resp = requests.post(f"{BASE}/compile/create", headers=get_auth(), json={"projectId": PROJECT_ID})
data = resp.json()
print(f"Compile response: {json.dumps(data, indent=2)[:500]}")

cid = data.get("compileId", "")
state = data.get("state", "")

# Wait for compile
waited = 0
while state not in ("BuildSuccess", "BuildError") and waited < 60:
    time.sleep(3)
    waited += 3
    resp = requests.post(f"{BASE}/compile/read", headers=get_auth(), json={
        "projectId": PROJECT_ID, "compileId": cid
    })
    data = resp.json()
    state = data.get("state", "")

print(f"Compile state: {state}, ID: {cid}")

if state == "BuildSuccess":
    # Try launch backtest
    print("\nLaunching backtest...")
    resp = requests.post(f"{BASE}/backtests/create", headers=get_auth(), json={
        "projectId": PROJECT_ID,
        "compileId": cid,
        "backtestName": "Debug Test Launch"
    })
    data = resp.json()
    print(f"Launch response:")
    print(json.dumps(data, indent=2)[:2000])
