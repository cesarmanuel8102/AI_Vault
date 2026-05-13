"""
Check QC account for any live/paper algorithms running.
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

def api(method, endpoint, payload=None):
    for attempt in range(3):
        try:
            if method == "GET":
                r = requests.get(f"{BASE}/{endpoint}", headers=auth_headers(), timeout=30)
            else:
                r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload or {}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                raise

# 1. List all projects
print("=== ALL PROJECTS ===")
resp = api("POST", "projects/read", {})
if resp.get("success"):
    projects = resp.get("projects", [])
    print(f"  Total projects: {len(projects)}")
    for p in projects:
        pid = p.get("projectId")
        name = p.get("name", "?")
        lang = p.get("language", "?")
        modified = p.get("modified", "?")
        print(f"  [{pid}] {name} ({lang}) modified={modified}")
else:
    print(f"  Failed: {resp}")

# 2. Check for live algorithms
print("\n=== LIVE ALGORITHMS ===")
resp = api("POST", "live/list", {})
if resp.get("success"):
    lives = resp.get("live", resp.get("algorithms", []))
    if not lives:
        print("  No live algorithms running")
    else:
        if isinstance(lives, list):
            for l in lives:
                print(f"  Live: {json.dumps(l, indent=2, default=str)[:300]}")
        else:
            print(f"  Live data: {json.dumps(lives, indent=2, default=str)[:500]}")
else:
    errors = resp.get("errors", [])
    print(f"  Response: success={resp.get('success')} errors={errors}")
    # Try alternate endpoint
    resp2 = api("POST", "live/read", {})
    print(f"  Alt /live/read: {json.dumps(resp2, indent=2, default=str)[:500]}")

# 3. Check account status
print("\n=== ACCOUNT STATUS ===")
resp = api("POST", "authenticate", {})
print(f"  Auth: {json.dumps(resp, indent=2, default=str)[:500]}")

# 4. Check organization
print("\n=== ORGANIZATION ===")
resp = api("POST", "organization/read", {})
if resp.get("success"):
    org = resp.get("organization", resp)
    if isinstance(org, dict):
        for k in ["id", "name", "type", "seats", "credit"]:
            if k in org:
                print(f"  {k}: {org[k]}")
        # Check live node usage
        nodes = org.get("nodes", {})
        if nodes:
            print(f"  Nodes: {json.dumps(nodes, indent=2, default=str)[:300]}")
else:
    print(f"  Failed: {json.dumps(resp, indent=2, default=str)[:300]}")

print("\nDONE")
