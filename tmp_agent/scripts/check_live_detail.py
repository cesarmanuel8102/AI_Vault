"""
Get details on the RUNNING live algo on project 29490680.
"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
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
                time.sleep(2)
            else:
                raise

# The running live algo
DEPLOY_ID = "L-f8a6181a1157273d680206e87a806435"
PROJECT_ID = 29490680

# 1. Read live algo details
print("=== RUNNING LIVE ALGO DETAILS ===")
resp = api("live/read", {
    "projectId": PROJECT_ID,
    "deployId": DEPLOY_ID,
})

if resp.get("success"):
    live = resp.get("live", resp)
    if isinstance(live, dict):
        # Print key fields
        for k in ["projectId", "deployId", "status", "launched", "stopped",
                   "brokerage", "note", "error", "stacktrace"]:
            if k in live:
                print(f"  {k}: {live[k]}")

        # Statistics
        stats = live.get("statistics", live.get("runtimeStatistics", {}))
        if stats:
            print("\n  --- STATISTICS ---")
            if isinstance(stats, dict):
                for k, v in stats.items():
                    print(f"  {k}: {v}")

        # Charts / equity
        charts = live.get("charts", {})
        if charts:
            print(f"\n  Charts available: {list(charts.keys())[:5]}")
else:
    print(f"  Failed: {json.dumps(resp, indent=2, default=str)[:500]}")

# 2. Also check recent live deployments on this project
print("\n=== ALL DEPLOYS ON PROJECT 29490680 ===")
resp = api("live/list", {"projectId": PROJECT_ID})
if resp.get("success"):
    lives = resp.get("live", [])
    if isinstance(lives, list):
        for l in lives:
            status = l.get("status", "?")
            launched = l.get("launched", "?")
            deploy_id = l.get("deployId", "?")
            error = l.get("error", "")
            err_preview = str(error)[:80] if error else ""
            print(f"  [{status}] {deploy_id} launched={launched} {err_preview}")
    else:
        print(f"  Data: {json.dumps(lives, indent=2, default=str)[:500]}")

# 3. Check the OTHER running project (29721803 - MTF Trend Pullback)
print("\n=== PROJECT 29721803 (MTF Trend Pullback) ===")
resp = api("live/list", {"projectId": 29721803})
if resp.get("success"):
    lives = resp.get("live", [])
    if isinstance(lives, list):
        for l in lives:
            status = l.get("status", "?")
            launched = l.get("launched", "?")
            deploy_id = l.get("deployId", "?")
            print(f"  [{status}] {deploy_id} launched={launched}")
    else:
        print(f"  No live algos")

print("\nDONE")
