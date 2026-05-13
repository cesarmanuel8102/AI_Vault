"""
Check live algorithm status and read its logs.
Two API calls: /live/read and /live/read/log
"""
import json, time, hashlib, base64, requests

# Credentials
USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
DEPLOY_ID = "L-68448c441f9019541d1c6681a6346ccd"

def get_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}

BASE = "https://www.quantconnect.com/api/v2"

# 1. Read live algo status
print("=" * 60)
print("LIVE ALGO STATUS")
print("=" * 60)
resp = requests.post(f"{BASE}/live/read", headers=get_auth(), json={
    "projectId": PROJECT_ID,
    "deployId": DEPLOY_ID
})
data = resp.json()
if data.get("success"):
    live = data.get("live", data)
    print(f"Status: {live.get('status', 'N/A')}")
    print(f"Deploy ID: {live.get('deployId', DEPLOY_ID)}")
    print(f"Launched: {live.get('launched', 'N/A')}")
    print(f"Stopped: {live.get('stopped', 'N/A')}")
    print(f"Brokerage: {live.get('brokerage', 'N/A')}")
    # Check if there's algo info
    if 'algorithm' in live:
        algo = live['algorithm']
        print(f"Algorithm Status: {algo.get('status', 'N/A')}")
    # Print full keys for inspection
    print(f"\nTop-level keys: {list(data.keys())}")
    if 'live' in data:
        print(f"Live object keys: {list(data['live'].keys())}")
else:
    print(f"ERROR: {data}")
    print(json.dumps(data, indent=2)[:2000])

# 2. Read live algo logs (all pages)
print("\n" + "=" * 60)
print("LIVE ALGO LOGS")
print("=" * 60)

all_logs = []
start = 0
page_size = 500
page = 1

while True:
    print(f"\nFetching logs page {page} (start={start})...")
    resp = requests.post(f"{BASE}/live/read/log", headers=get_auth(), json={
        "projectId": PROJECT_ID,
        "deployId": DEPLOY_ID,
        "start": start,
        "end": start + page_size
    })
    data = resp.json()
    if not data.get("success"):
        print(f"Log API error: {data}")
        # Try alternative format
        resp2 = requests.post(f"{BASE}/live/read/log", headers=get_auth(), json={
            "projectId": PROJECT_ID,
            "format": "json",
            "algorithmId": DEPLOY_ID,
            "startLine": start,
            "endLine": start + page_size
        })
        data = resp2.json()
        if not data.get("success"):
            print(f"Alt format also failed: {data}")
            break
    
    logs = data.get("liveLogs", data.get("logs", data.get("LiveLogs", [])))
    if isinstance(logs, list):
        print(f"Got {len(logs)} log entries")
        all_logs.extend(logs)
        if len(logs) < page_size:
            break
        start += page_size
        page += 1
    elif isinstance(logs, dict):
        # Sometimes logs come as dict with different keys
        print(f"Logs dict keys: {list(logs.keys())}")
        for k, v in logs.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} entries")
                all_logs.extend(v)
        break
    else:
        print(f"Unexpected logs format: {type(logs)}")
        print(str(logs)[:1000])
        break

print(f"\nTotal log entries collected: {len(all_logs)}")

# Save logs
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/live_logs.json", "w") as f:
    json.dump(all_logs, f, indent=2, default=str)

# Print last 50 log entries for quick review
print("\n" + "=" * 60)
print("LAST 50 LOG ENTRIES")
print("=" * 60)
for entry in all_logs[-50:]:
    if isinstance(entry, dict):
        ts = entry.get("time", entry.get("Time", ""))
        msg = entry.get("message", entry.get("Message", str(entry)))
        print(f"[{ts}] {msg}")
    else:
        print(str(entry)[:200])
