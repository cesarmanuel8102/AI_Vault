"""
Read live algo logs with correct API format.
algorithmId = deployId, max 250 lines per request.
Also extract runtime statistics from the status response.
"""
import json, time, hashlib, base64, requests

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

# 1. Get runtime statistics
print("=" * 60)
print("LIVE ALGO RUNTIME STATISTICS")
print("=" * 60)
resp = requests.post(f"{BASE}/live/read", headers=get_auth(), json={
    "projectId": PROJECT_ID,
    "deployId": DEPLOY_ID
})
data = resp.json()
if data.get("success"):
    print(f"Status: {data.get('status')}")
    print(f"Launched: {data.get('launched')}")
    print(f"Brokerage: {data.get('brokerage')}")
    print(f"Project: {data.get('projectName')}")
    rt = data.get("runtimeStatistics", {})
    print(f"\nRuntime Statistics:")
    for k, v in sorted(rt.items()):
        print(f"  {k}: {v}")
    
    # Save full status
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/live_status.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    # Check files to see what code is actually running
    files = data.get("files", [])
    if files:
        print(f"\nFiles in live deployment:")
        for f in files:
            if isinstance(f, dict):
                print(f"  {f.get('name', 'N/A')} - {f.get('modified', 'N/A')}")
            else:
                print(f"  {f}")

# 2. Read logs with correct format
print("\n" + "=" * 60)
print("LIVE ALGO LOGS")
print("=" * 60)

all_logs = []
start = 0
page_size = 250
page = 1
max_pages = 25  # Safety limit

while page <= max_pages:
    print(f"\nFetching logs page {page} (lines {start}-{start + page_size})...")
    resp = requests.post(f"{BASE}/live/read/log", headers=get_auth(), json={
        "projectId": PROJECT_ID,
        "algorithmId": DEPLOY_ID,
        "startLine": start,
        "endLine": start + page_size
    })
    data = resp.json()
    
    if not data.get("success"):
        print(f"Error: {data}")
        break
    
    logs = data.get("LiveLogs", data.get("liveLogs", data.get("logs", [])))
    
    if isinstance(logs, list):
        print(f"Got {len(logs)} log entries")
        all_logs.extend(logs)
        if len(logs) < page_size:
            print("(Last page - fewer entries than page size)")
            break
        start += page_size
        page += 1
    else:
        print(f"Unexpected format: {type(logs)}")
        print(f"Response keys: {list(data.keys())}")
        print(str(data)[:500])
        break

print(f"\n{'=' * 60}")
print(f"TOTAL LOG ENTRIES: {len(all_logs)}")
print(f"{'=' * 60}")

# Save all logs
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/live_logs.json", "w") as f:
    json.dump(all_logs, f, indent=2, default=str)

# Print ALL logs for review
print(f"\n{'=' * 60}")
print("ALL LOG ENTRIES")
print(f"{'=' * 60}")
for i, entry in enumerate(all_logs):
    if isinstance(entry, dict):
        ts = entry.get("time", entry.get("Time", ""))
        msg = entry.get("message", entry.get("Message", str(entry)))
        print(f"[{i}][{ts}] {msg}")
    else:
        print(f"[{i}] {str(entry)[:300]}")
