"""Poll V5b and V5c until all ablation tests complete, then print full comparison"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api(endpoint, payload):
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                raise

def poll_bt(bt_id, name, max_polls=120):
    for i in range(max_polls):
        data = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = data.get("backtest", data)
        completed = bt.get("completed", False)
        progress = bt.get("progress", 0)
        prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 3 == 0:
            print(f"  [{name}] Poll {i+1}: {prog_str} completed={completed}")
        if completed:
            return bt.get("statistics", {})
        time.sleep(10)
    print(f"  [{name}] TIMEOUT after {max_polls} polls")
    return None

# Check V5b
V5B_ID = "c0fac48a599f1f0bdf3b798343e3c646"
print("=== Waiting for V5b FIX2-only ===")
v5b_stats = poll_bt(V5B_ID, "V5b")

if v5b_stats:
    print(f"\nV5b completed!")
    for k, v in v5b_stats.items():
        print(f"  {k}: {v}")

# Now check the ablation log to see if V5c has launched
print("\n=== Checking ablation log for V5c ===")
with open("C:/AI_VAULT/tmp_agent/scripts/v5_ablation_out.log", "r") as f:
    log = f.read()
print(log[-500:] if len(log) > 500 else log)

# Wait for V5c if it launched
# Read log again to find V5c BT ID
import re
v5c_match = re.search(r"V5c.*?Backtest launched: ([a-f0-9]+)", log, re.DOTALL)
if v5c_match:
    V5C_ID = v5c_match.group(1)
    print(f"\n=== Waiting for V5c FIX2+FIX3, BT ID: {V5C_ID} ===")
    v5c_stats = poll_bt(V5C_ID, "V5c")
    if v5c_stats:
        print(f"\nV5c completed!")
        for k, v in v5c_stats.items():
            print(f"  {k}: {v}")
else:
    print("V5c not yet launched, will need to re-read log after V5b finishes")
    # Wait for runner to launch V5c
    for retry in range(30):
        time.sleep(10)
        with open("C:/AI_VAULT/tmp_agent/scripts/v5_ablation_out.log", "r") as f:
            log = f.read()
        v5c_match = re.search(r"V5c.*?Backtest launched: ([a-f0-9]+)", log, re.DOTALL)
        if v5c_match:
            V5C_ID = v5c_match.group(1)
            print(f"\n=== V5c launched! BT ID: {V5C_ID} ===")
            v5c_stats = poll_bt(V5C_ID, "V5c")
            if v5c_stats:
                print(f"\nV5c completed!")
                for k, v in v5c_stats.items():
                    print(f"  {k}: {v}")
            break
        if retry % 6 == 0:
            print(f"  Waiting for V5c to launch... (retry {retry+1})")

print("\n=== ALL ABLATION TESTS DONE ===")
