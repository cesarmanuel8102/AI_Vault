"""
V19 Diagnosis v2 - Try different QC API endpoints to get logs and orders.
"""
import hashlib, base64, time, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
BT_FULL = "8bc94fc761b3321ed31697a2731073b1"

def auth_headers():
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api_post(endpoint, payload, retries=3, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=timeout)
            print(f"  POST {endpoint}: status={r.status_code}")
            return r.json()
        except Exception as e:
            print(f"  POST {endpoint} attempt {attempt+1}: {e}")
            if attempt < retries - 1:
                time.sleep(10)
    return {}

def api_get(endpoint, params=None, retries=3, timeout=45):
    for attempt in range(retries):
        try:
            url = f"{BASE}/{endpoint}"
            r = requests.get(url, headers=auth_headers(), params=params or {}, timeout=timeout)
            print(f"  GET {endpoint}: status={r.status_code}")
            return r.json()
        except Exception as e:
            print(f"  GET {endpoint} attempt {attempt+1}: {e}")
            if attempt < retries - 1:
                time.sleep(10)
    return {}

print("=== 1. Try backtests/read with log data ===")
resp = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": BT_FULL})
bt = resp.get("backtest", resp)
# Check for any log-like keys
for k in sorted(bt.keys()):
    v = bt[k]
    tp = type(v).__name__
    if isinstance(v, str):
        print(f"  {k} ({tp}): {v[:200]}")
    elif isinstance(v, (int, float, bool)):
        print(f"  {k} ({tp}): {v}")
    elif isinstance(v, dict):
        print(f"  {k} ({tp}): {len(v)} keys => {list(v.keys())[:10]}")
    elif isinstance(v, list):
        print(f"  {k} ({tp}): {len(v)} items")
    else:
        print(f"  {k} ({tp})")

print("\n=== 2. Try backtests/orders/read ===")
resp2 = api_post("backtests/orders/read", {"projectId": PROJECT_ID, "backtestId": BT_FULL, "start": 0, "end": 200})
print(f"  Keys: {list(resp2.keys())}")
print(f"  Success: {resp2.get('success')}")
orders = resp2.get("orders", [])
print(f"  Orders count: {len(orders)}")
if orders:
    for o in orders[:5]:
        if isinstance(o, dict):
            print(f"    Order: {json.dumps({k: str(v)[:80] for k, v in o.items()}, indent=2)}")
        else:
            print(f"    Order: {o}")

print("\n=== 3. Try backtests/read/log ===")
resp3 = api_post("backtests/read/log", {"projectId": PROJECT_ID, "backtestId": BT_FULL})
print(f"  Keys: {list(resp3.keys())}")
print(f"  Success: {resp3.get('success')}")
logs = resp3.get("logs", resp3.get("log", []))
print(f"  Logs count: {len(logs) if isinstance(logs, list) else 'N/A (type={})'.format(type(logs).__name__)}")
if isinstance(logs, list):
    for l in logs[:30]:
        print(f"    {l}")
elif isinstance(logs, str):
    print(f"    {logs[:2000]}")

print("\n=== 4. Try GET backtests/{bt}/log ===")
resp4 = api_get(f"backtests/read/log", {"projectId": PROJECT_ID, "backtestId": BT_FULL})
print(f"  Keys: {list(resp4.keys())}")
for k, v in resp4.items():
    if isinstance(v, str):
        print(f"  {k}: {v[:500]}")
    elif isinstance(v, list):
        print(f"  {k}: {len(v)} items")
        for item in (v[:20] if isinstance(v, list) else []):
            print(f"    {item}")
    else:
        print(f"  {k}: {v}")

print("\n=== 5. Check totalPerformance for trade details ===")
tp = bt.get("totalPerformance", {})
if tp:
    print(f"  totalPerformance keys: {list(tp.keys())}")
    for k, v in tp.items():
        if isinstance(v, dict):
            print(f"  {k}: {list(v.keys())[:15]}")
            for k2, v2 in list(v.items())[:10]:
                if isinstance(v2, dict):
                    print(f"    {k2}: {list(v2.keys())[:10]}")
                else:
                    print(f"    {k2}: {v2}")
        elif isinstance(v, list):
            print(f"  {k}: {len(v)} items")
            for item in v[:5]:
                print(f"    {item}")
        else:
            print(f"  {k}: {v}")

print("\nDONE.")
