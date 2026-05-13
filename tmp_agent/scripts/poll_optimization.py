"""
Poll optimization status for V2.0b param stability study.
Optimization ID: O-c9eca3743f4933140d42879a0d38825e
"""
import json, time, hashlib, base64, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
OPT_ID = "O-c9eca3743f4933140d42879a0d38825e"

def get_auth():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}

BASE = "https://www.quantconnect.com/api/v2"

print(f"Polling optimization: {OPT_ID}")
resp = requests.post(f"{BASE}/optimizations/read", headers=get_auth(), json={
    "optimizationId": OPT_ID
})
data = resp.json()

print(f"Success: {data.get('success')}")

if data.get("success"):
    opt = data.get("optimization", data)
    # Top level info
    print(f"\nStatus: {opt.get('status', 'N/A')}")
    print(f"Name: {opt.get('name', 'N/A')}")
    print(f"Created: {opt.get('created', 'N/A')}")
    print(f"Node: {opt.get('nodeType', 'N/A')}")
    
    # Progress
    backtests = opt.get("backtests", {})
    if isinstance(backtests, dict):
        print(f"\nBacktests completed: {len(backtests)}/45")
        
        # Parse results
        results = []
        for bt_id, bt_data in backtests.items():
            if isinstance(bt_data, dict):
                params = bt_data.get("parameterSet", {})
                stats = bt_data.get("statistics", bt_data.get("Statistics", {}))
                sharpe = stats.get("Sharpe Ratio", stats.get("SharpeRatio", "N/A"))
                ret = stats.get("Total Return", stats.get("TotalNetProfit", "N/A"))
                results.append({
                    "bt_id": bt_id,
                    "pt": params.get("profit_target_pct", "?"),
                    "sl": params.get("stop_loss_pct", "?"),
                    "risk": params.get("risk_per_trade", "?"),
                    "sharpe": sharpe,
                    "return": ret
                })
        
        if results:
            print(f"\nResults so far:")
            print(f"{'PT':>6} {'SL':>7} {'Risk':>6} {'Sharpe':>8} {'Return':>10}")
            print("-" * 45)
            for r in sorted(results, key=lambda x: float(x['sharpe']) if x['sharpe'] != 'N/A' else -999, reverse=True):
                print(f"{r['pt']:>6} {r['sl']:>7} {r['risk']:>6} {r['sharpe']:>8} {r['return']:>10}")
    elif isinstance(backtests, list):
        print(f"\nBacktests: {len(backtests)} entries")
    
    # Best result
    best = opt.get("criterion", {})
    print(f"\nBest Sharpe so far: {opt.get('sharpeRatio', 'N/A')}")
    print(f"Best PSR: {opt.get('psr', 'N/A')}")
    print(f"Best trades: {opt.get('trades', 'N/A')}")
    
    # Print full response keys for debugging
    print(f"\nTop-level response keys: {list(data.keys())}")
    if 'optimization' in data:
        print(f"Optimization keys: {list(data['optimization'].keys())}")
    
    # Save full response
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/optimization_status.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
else:
    print(f"ERROR: {data}")
    print(json.dumps(data, indent=2)[:2000])
