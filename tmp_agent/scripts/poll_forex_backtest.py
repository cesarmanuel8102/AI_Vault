"""Poll backtest progress until complete, then show results."""
import time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
BACKTEST_ID = "99205ada98ccb28960d77f9cff6f7d89"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

print(f"Monitoring backtest {BACKTEST_ID}...")
print(f"Project: {PROJECT_ID}")
print("-" * 60)

max_wait = 600  # 10 min max
waited = 0
interval = 10

while waited < max_wait:
    r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
        "projectId": PROJECT_ID,
        "backtestId": BACKTEST_ID
    })
    data = r.json()
    bt = data.get("backtest", {})
    progress = bt.get("progress", 0)
    error = bt.get("error", "")
    stack = bt.get("stacktrace", "")

    print(f"[{waited:>3}s] Progress: {progress*100:.1f}%", end="")

    if error:
        print(f"\n\n[ERROR] Backtest failed!")
        print(f"Error: {error}")
        if stack:
            print(f"Stack: {stack}")
        break

    if progress >= 1.0:
        print(" -- COMPLETE!")
        # Extract results
        stats = bt.get("runtimeStatistics", {})
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS: Forex V1.0 Baseline")
        print(f"{'='*60}")
        for k, v in stats.items():
            print(f"  {k:.<30} {v}")

        # Also get statistics
        statistics = bt.get("statistics", {})
        if statistics:
            print(f"\n--- Detailed Statistics ---")
            for k, v in statistics.items():
                print(f"  {k:.<40} {v}")

        # Save full results
        with open("C:/AI_VAULT/tmp_agent/strategies/forex_v1/backtest_results.json", "w") as f:
            json.dump(bt, f, indent=2, default=str)
        print(f"\n[SAVED] Full results -> forex_v1/backtest_results.json")
        break

    print("")
    time.sleep(interval)
    waited += interval

if waited >= max_wait:
    print(f"\n[TIMEOUT] Backtest still running after {max_wait}s. Check QC manually.")
