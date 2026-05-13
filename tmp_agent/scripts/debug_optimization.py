"""
Try optimization with minimal settings - maybe free tier.
Also try without constraint to rule that out as the issue.
"""
import json, time, hashlib, base64, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
COMPILE_ID = "68cdbef3d5f948b2076d7a53b1e6e680-f3934dfa75881cd50c352c5abb73d2b6"

def get_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}

BASE = "https://www.quantconnect.com/api/v2"

# First, check account/organization status for QCC balance
print("=" * 60)
print("CHECKING ACCOUNT STATUS")
print("=" * 60)

# Check organization
resp = requests.post(f"{BASE}/account/read", headers=get_auth())
data = resp.json()
print(f"Account info: {json.dumps(data, indent=2)[:1500]}")

# List available node types
print("\n" + "=" * 60)
print("CHECKING AVAILABLE NODES")
print("=" * 60)
resp = requests.post(f"{BASE}/organizations/read", headers=get_auth(), json={
    "organizationId": "6d487993ca17881264c2ac55e41ae539"
})
data = resp.json()
if data.get("success"):
    org = data.get("organization", data)
    print(f"Org name: {org.get('name', 'N/A')}")
    print(f"Org type: {org.get('type', 'N/A')}")
    # Look for credit/balance info
    credit = org.get("credit", org.get("balance", "N/A"))
    print(f"Credit/Balance: {credit}")
    
    # Save full org response to check available resources
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/org_info.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    # Print keys to explore structure
    if isinstance(org, dict):
        for k, v in org.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                print(f"  {k}: {v}")
else:
    print(f"Org read error: {data}")

# Try optimization with smallest possible settings
print("\n" + "=" * 60)
print("LAUNCHING MINIMAL OPTIMIZATION (2 params, fewer combos)")
print("=" * 60)

payload = {
    "projectId": PROJECT_ID,
    "name": "V2.0b Mini Test - 2 params",
    "target": "TotalPerformance.PortfolioStatistics.SharpeRatio",
    "targetTo": "max",
    "strategy": "QuantConnect.Optimizer.Strategies.GridSearchOptimizationStrategy",
    "compileId": COMPILE_ID,
    "parameters": [
        {
            "key": "profit_target_pct",
            "min": "0.30",
            "max": "0.40",
            "step": "0.10",
            "min-step": "0.01"
        },
        {
            "key": "stop_loss_pct",
            "min": "-0.25",
            "max": "-0.15",
            "step": "0.10",
            "min-step": "0.01"
        }
    ],
    "constraints": [],
    "estimatedCost": 0,
    "nodeType": "O2-8",
    "parallelNodes": 2
}

print(f"Expected combos: 2 x 2 = 4 backtests")
resp = requests.post(f"{BASE}/optimizations/create", headers=get_auth(), json=payload)
data = resp.json()
print(f"Success: {data.get('success')}")

if data.get("success"):
    opts = data.get("optimizations", [data.get("optimization", {})])
    for opt in opts:
        opt_id = opt.get("optimizationId", "N/A")
        status = opt.get("status", "N/A")
        print(f"Opt ID: {opt_id}, Status: {status}")
    
    # Save and immediately poll
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/optimization_mini.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    # Wait a bit and poll
    print("\nWaiting 15 seconds...")
    time.sleep(15)
    
    mini_id = opts[0].get("optimizationId") if opts else None
    if mini_id:
        resp2 = requests.post(f"{BASE}/optimizations/read", headers=get_auth(), json={
            "optimizationId": mini_id
        })
        d2 = resp2.json()
        if d2.get("success"):
            o2 = d2.get("optimization", d2)
            print(f"\nAfter 15s: Status={o2.get('status')}")
            rt = o2.get("runtimeStatistics", {})
            for k, v in rt.items():
                print(f"  {k}: {v}")
else:
    print(f"ERROR: {data.get('errors', data)}")
    print(json.dumps(data, indent=2)[:2000])
