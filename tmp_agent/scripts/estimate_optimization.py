"""
Estimate optimization cost for V2.0b parameter stability study.
3 params: profit_target_pct, stop_loss_pct, risk_per_trade
45 combinations total.
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

# Optimization estimate request
payload = {
    "projectId": PROJECT_ID,
    "name": "V2.0b Param Stability - 3 params 45 combos",
    "target": "TotalPerformance.PortfolioStatistics.SharpeRatio",
    "targetTo": "max",
    "strategy": "QuantConnect.Optimizer.Strategies.GridSearchOptimizationStrategy",
    "compileId": COMPILE_ID,
    "parameters": [
        {
            "key": "profit_target_pct",
            "min": "0.30",
            "max": "0.50",
            "step": "0.05",
            "min-step": "0.01"
        },
        {
            "key": "stop_loss_pct",
            "min": "-0.25",
            "max": "-0.15",
            "step": "0.05",
            "min-step": "0.01"
        },
        {
            "key": "risk_per_trade",
            "min": "0.04",
            "max": "0.06",
            "step": "0.01",
            "min-step": "0.005"
        }
    ],
    "constraints": [
        {
            "target": "TotalPerformance.PortfolioStatistics.SharpeRatio",
            "operator": "GreaterOrEqual",
            "targetValue": "1.0"
        }
    ],
    "nodeType": "O2-8",
    "parallelNodes": 6
}

print("Sending optimization ESTIMATE request...")
print(f"Payload parameters: {json.dumps(payload['parameters'], indent=2)}")
print(f"Total expected combos: 5 x 3 x 3 = 45")
print()

resp = requests.post(f"{BASE}/optimizations/estimate", headers=get_auth(), json=payload)
data = resp.json()

print(f"Response status: {resp.status_code}")
print(f"Success: {data.get('success')}")
print(json.dumps(data, indent=2))

# Save the response
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/optimization_estimate.json", "w") as f:
    json.dump(data, f, indent=2)

if data.get("success"):
    est = data
    print(f"\n{'='*60}")
    print(f"OPTIMIZATION COST ESTIMATE")
    print(f"{'='*60}")
    print(f"Estimated cost: {est.get('estimatedCost', 'N/A')} QCC")
    print(f"Estimated time: {est.get('estimatedTime', 'N/A')}")
    print(f"Number of backtests: {est.get('numberOfBacktests', 'N/A')}")
else:
    print(f"\nERROR: {data.get('errors', data.get('messages', 'Unknown error'))}")
