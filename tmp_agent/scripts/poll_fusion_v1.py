"""Poll Fusion V1 backtest until complete, then read 5 pages of logs."""
import time, json, requests, sys
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "489b05a63caade9a004ce9e29ca2ad40"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# Poll until done
print("Polling Fusion V1 backtest...")
for i in range(120):  # max 10 min
    r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
        "projectId": PROJECT_ID, "backtestId": BT_ID
    })
    data = r.json()
    bt = data.get("backtest", {})
    progress = bt.get("progress", 0)
    error = bt.get("error", "")
    stats = bt.get("runtimeStatistics", {})
    equity = stats.get("Equity", "?")
    
    print(f"  [{i*5}s] Progress: {progress*100:.1f}% | Equity: {equity}")
    
    if error:
        print(f"  ERROR: {error[:200]}")
        break
    
    if progress >= 1.0:
        print("DONE!")
        break
    
    time.sleep(5)

# Final status
r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": BT_ID
})
data = r.json()
bt = data.get("backtest", {})
progress = bt.get("progress", 0)
error = bt.get("error", "")
stats = bt.get("runtimeStatistics", {})
statistics = bt.get("statistics", {})

print(f"\n{'='*60}")
print(f"FUSION V1 FINAL STATUS")
print(f"{'='*60}")
print(f"Progress: {progress*100:.1f}%")
if error:
    print(f"ERROR: {error[:300]}")
    if bt.get("stacktrace"):
        print(f"STACK: {bt['stacktrace'][:500]}")

print(f"\nRuntime Stats:")
for k, v in stats.items():
    print(f"  {k}: {v}")
if statistics:
    print(f"\nStatistics:")
    for k, v in statistics.items():
        print(f"  {k}: {v}")

# Read 5 pages of logs if done or errored
all_logs = []
for page in range(5):
    start = page * 200
    end = start + 200
    r = requests.post(f"{BASE}/backtests/read/log", headers=headers(), json={
        "projectId": PROJECT_ID, "backtestId": BT_ID,
        "start": start, "end": end, "query": " "
    })
    log_data = r.json()
    logs = log_data.get("backtestLogs", log_data.get("logs", []))
    if not logs:
        print(f"\nPage {page+1}: (empty)")
        break
    all_logs.extend(logs)
    print(f"\nPage {page+1} ({start}-{end}): {len(logs)} entries")

with open("C:/AI_VAULT/tmp_agent/strategies/fusion_v1/bt_logs.json", "w") as f:
    json.dump(all_logs, f, indent=2)
print(f"\nTotal logs: {len(all_logs)}")

print(f"\n{'='*80}")
print("FULL LOGS")
print(f"{'='*80}")
for i, log in enumerate(all_logs):
    if isinstance(log, dict):
        ts_val = log.get("time", log.get("timestamp", ""))
        msg = log.get("message", log.get("msg", str(log)))
        print(f"[{i+1}] {ts_val} | {msg}")
    else:
        print(f"[{i+1}] {log}")
