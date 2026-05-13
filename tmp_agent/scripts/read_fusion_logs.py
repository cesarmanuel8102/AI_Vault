"""Read logs from Fusion V1 backtest — 5 pages (0-200 each)."""
import time, json, requests
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

# First check status
r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": BT_ID
})
data = r.json()
bt = data.get("backtest", {})
progress = bt.get("progress", 0)
error = bt.get("error", "")
stats = bt.get("runtimeStatistics", {})
statistics = bt.get("statistics", {})

print(f"=== FUSION V1 STATUS ===")
print(f"Progress: {progress*100:.1f}%")
if error:
    print(f"ERROR: {error}")
    if bt.get("stacktrace"):
        print(f"STACK: {bt['stacktrace'][:500]}")
print(f"\nRuntime Stats:")
for k, v in stats.items():
    print(f"  {k}: {v}")
if statistics:
    print(f"\nStatistics:")
    for k, v in statistics.items():
        print(f"  {k}: {v}")

# Now read 5 pages of logs
if progress >= 1.0:
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
            print(f"\nPage {page+1}: (empty — no more logs)")
            break
        all_logs.extend(logs)
        print(f"\nPage {page+1} ({start}-{end}): {len(logs)} entries")

    # Save all logs
    with open("C:/AI_VAULT/tmp_agent/strategies/fusion_v1/bt_logs.json", "w") as f:
        json.dump(all_logs, f, indent=2)
    print(f"\nTotal logs saved: {len(all_logs)}")

    # Print all logs
    print("\n" + "="*80)
    print("FULL LOGS")
    print("="*80)
    for i, log in enumerate(all_logs):
        if isinstance(log, dict):
            ts_val = log.get("time", log.get("timestamp", ""))
            msg = log.get("message", log.get("msg", str(log)))
            print(f"[{i+1}] {ts_val} | {msg}")
        else:
            print(f"[{i+1}] {log}")
else:
    print(f"\nBacktest still running ({progress*100:.1f}%). Logs not available yet.")
