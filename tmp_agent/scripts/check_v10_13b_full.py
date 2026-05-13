"""Check v10.13b Full backtest status and extract all stats"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
BT_ID = "4bacc76ad9694ce6b4236d3649e043b9"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

r = requests.post(f"{BASE}/backtests/read", headers=auth_headers(),
                   json={"projectId": PROJECT_ID, "backtestId": BT_ID}, timeout=30)
data = r.json()
bt = data.get("backtest", data)
progress = bt.get("progress", 0)
completed = bt.get("completed", False)
prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
print(f"Progress: {prog_str}, Completed: {completed}")

if completed:
    stats = bt.get("statistics", {})
    print("\n=== V10.13b FULL 2023-2026 VERIFIED RESULTS ===")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    # Save raw
    with open("C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_13b_full_verified.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print("\nSaved to v10_13b_full_verified.json")
else:
    print("Still running...")
    # Check if there are errors
    if bt.get("error"):
        print(f"ERROR: {bt.get('error')}")
    if bt.get("stackTrace"):
        print(f"Stack: {bt.get('stackTrace')[:500]}")
