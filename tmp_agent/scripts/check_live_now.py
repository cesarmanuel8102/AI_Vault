"""Poll V10.13b live status using proper QC hash authentication."""
import requests, json, sys
from base64 import b64encode
from hashlib import sha256
from time import time as time_func

USER_ID = "384945"
API_TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE_URL = "https://www.quantconnect.com/api/v2"

def get_headers():
    timestamp = str(int(time_func()))
    time_stamped_token = f"{API_TOKEN}:{timestamp}".encode("utf-8")
    hashed_token = sha256(time_stamped_token).hexdigest()
    authentication = f"{USER_ID}:{hashed_token}".encode("utf-8")
    authentication = b64encode(authentication).decode("ascii")
    return {
        "Authorization": f"Basic {authentication}",
        "Timestamp": timestamp
    }

# 1. Read live algorithm statistics
print("=== V10.13b LIVE STATUS ===")
payload = {"projectId": PROJECT_ID}
resp = requests.post(f"{BASE_URL}/live/read", headers=get_headers(), json=payload)
data = resp.json()

if data.get("success"):
    print(f"Deploy ID: {data.get('deployId', '?')}")
    print(f"Status: {data.get('status', '?')}")
    print(f"Launched: {data.get('launched', '?')}")
    print(f"Stopped: {data.get('stopped', '?')}")
    print(f"Brokerage: {data.get('brokerage', '?')}")
    
    rt = data.get("runtimeStatistics", {})
    if rt:
        print("\nRuntime Statistics:")
        for k, v in rt.items():
            print(f"  {k}: {v}")
    
    charts = data.get("charts", {})
    if charts:
        print(f"\nCharts: {list(charts.keys()) if isinstance(charts, dict) else charts}")
    
    print(f"\nProject: {data.get('projectName', '?')}")
else:
    print(f"Error: {data.get('errors')}")
    print(f"All keys: {list(data.keys())}")

# 2. List all live algorithms
print("\n=== ALL LIVE ALGORITHMS ===")
list_payload = {
    "status": "Running",
    "start": 1743000000,  # ~March 26, 2026
    "end": int(time_func())
}
resp2 = requests.post(f"{BASE_URL}/live/list", headers=get_headers(), json=list_payload)
data2 = resp2.json()

if data2.get("success"):
    algos = data2.get("algorithms", [])
    print(f"Found {len(algos)} running algorithm(s)")
    for a in algos:
        print(f"\n  Deploy: {a.get('deployId', '?')}")
        print(f"  Project: {a.get('projectId', '?')} - {a.get('projectName', '?')}")
        print(f"  Status: {a.get('status', '?')}")
        print(f"  Launched: {a.get('launched', '?')}")
        rt2 = a.get("runtimeStatistics", {})
        if rt2:
            for k, v in rt2.items():
                print(f"    {k}: {v}")
else:
    print(f"Error: {data2.get('errors')}")

# 3. Read portfolio state
print("\n=== PORTFOLIO STATE ===")
resp3 = requests.post(f"{BASE_URL}/live/read/portfolio", headers=get_headers(), json={"projectId": PROJECT_ID})
data3 = resp3.json()
if data3.get("success"):
    portfolio = data3.get("portfolio", data3)
    for k in data3.keys():
        if k not in ("success", "errors"):
            val = data3[k]
            if isinstance(val, dict) and len(val) < 20:
                print(f"  {k}:")
                for k2, v2 in val.items():
                    if isinstance(v2, dict):
                        qty = v2.get("Quantity", v2.get("quantity", 0))
                        if qty != 0:
                            print(f"    {k2[:50]}: qty={qty}")
                    else:
                        print(f"    {k2}: {v2}")
            elif isinstance(val, (str, int, float, bool)):
                print(f"  {k}: {val}")
            else:
                print(f"  {k}: {type(val).__name__} len={len(val) if hasattr(val, '__len__') else '?'}")
else:
    print(f"Portfolio endpoint: {data3.get('errors', 'unknown error')}")

# 4. Read recent orders
print("\n=== RECENT ORDERS ===")
resp4 = requests.post(f"{BASE_URL}/live/read/orders", headers=get_headers(), json={
    "projectId": PROJECT_ID,
    "start": 0,
    "end": 100
})
data4 = resp4.json()
if data4.get("success"):
    orders = data4.get("orders", [])
    print(f"Found {len(orders)} order(s)")
    for o in orders[-10:]:
        sym = o.get("symbol", {})
        sym_val = sym.get("value", sym.get("Value", "?")) if isinstance(sym, dict) else sym
        print(f"  {o.get('time', o.get('Time', ''))} | {sym_val} | qty={o.get('quantity', o.get('Quantity', 0))} | status={o.get('status', o.get('Status', ''))}")
else:
    print(f"Orders endpoint: {data4.get('errors', 'unknown error')}")
