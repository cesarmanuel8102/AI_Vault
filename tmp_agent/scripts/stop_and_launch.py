"""Stop a running backtest and launch V1.5."""
import time, json, requests
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

# Stop the stuck backtest
stuck_bt = "084f5bbf8d9cb7353b998901f917a95d"
print(f"Stopping backtest: {stuck_bt}")
r = requests.post(f"{BASE}/backtests/delete", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": stuck_bt
})
print(f"Delete result: {r.json()}")

time.sleep(5)

# Now launch V1.5
compile_id = "d791f0820b00e46d2101a6295ca3af1d-a1fc0d769c895ecef125eb485864ba06"
bt_name = "Yoel Options V1.5 PM_BOUNCE 2023-2024"

print(f"\nLaunching V1.5...")
r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
    "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": bt_name
})
data = r.json()
bt = data.get("backtest", {})
bt_id = bt.get("backtestId", "")
print(f"Result: success={data.get('success')}")
print(f"BT ID: {bt_id}")
print(f"BT Name: {bt_name}")

if data.get("errors"):
    print(f"ERRORS: {data['errors']}")

# Save bt_id
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/current_bt.json", "w") as f:
    json.dump({"bt_id": bt_id, "bt_name": bt_name, "project_id": PROJECT_ID}, f)
print(f"Saved bt_id to current_bt.json")
