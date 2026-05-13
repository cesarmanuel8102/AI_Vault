"""
Deploy V2.0b-v2 to QC and run backtest.
Uses same project (29490680), uploads v20b_v2.py as main.py, 
sets BASELINE params, compiles, and launches.
"""
import sys
import time
import json
import requests
from hashlib import sha256
from base64 import b64encode

sys.stdout.reconfigure(encoding='ascii', errors='replace')

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

SOURCE_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v2.py"

# BASELINE params for V2.0b-v2
PARAMS = {
    "profit_target_pct": "0.35",
    "stop_loss_pct": "-0.20",
    "risk_per_trade": "0.05",
    "dte_min": "14",
    "dte_max": "30",
    "start_year": "2023",
    "end_year": "2024",
    "end_month": "12",
}


def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}{endpoint}", headers=headers(), json=payload, timeout=timeout)
            return r.json()
        except Exception as e:
            print(f"  API error ({attempt+1}/{retries}): {str(e)[:80]}")
            time.sleep(5)
    return {"success": False, "errors": ["max retries"]}


def main():
    print("=" * 60)
    print("DEPLOYING V2.0b-v2 (DD Reduction Build)")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Upload code
    print("\n[1] Uploading v20b_v2.py as main.py...")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        code = f.read()
    data = api_post("/files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    if not data.get("success"):
        data = api_post("/files/create", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    print(f"  Upload: {'OK' if data.get('success') else 'FAILED'}")
    if not data.get("success"):
        print(f"  Error: {data}")
        return

    # 2. Set parameters
    print("\n[2] Setting BASELINE parameters...")
    param_list = [{"key": k, "value": v} for k, v in PARAMS.items()]
    data = api_post("/projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    print(f"  Params: {'OK' if data.get('success') else 'FAILED'}")

    # 3. Compile
    print("\n[3] Compiling...")
    data = api_post("/compile/create", {"projectId": PROJECT_ID})
    cid = data.get("compileId", "")
    state = data.get("state", "")
    waited = 0
    while state not in ("BuildSuccess", "BuildError") and waited < 120:
        time.sleep(3)
        waited += 3
        data = api_post("/compile/read", {"projectId": PROJECT_ID, "compileId": cid})
        state = data.get("state", "")
    
    if state != "BuildSuccess":
        print(f"  COMPILE FAILED: {state}")
        print(f"  Details: {json.dumps(data, indent=2)[:500]}")
        return
    print(f"  Compiled: {cid}")

    # 4. Launch backtest
    print("\n[4] Launching backtest...")
    bt_name = "V2.0b-v2 DD_REDUCTION PT=0.35 SL=-0.20 R=0.05"
    
    for attempt in range(30):
        data = api_post("/backtests/create", {
            "projectId": PROJECT_ID, "compileId": cid, "backtestName": bt_name
        })
        if data.get("success"):
            bt = data.get("backtest", {})
            bt_id = bt.get("backtestId", "")
            print(f"  BT ID: {bt_id}")
            break
        errors = " ".join(data.get("errors", []))
        if "no spare nodes" in errors.lower():
            print(f"  Node busy, waiting 30s... ({attempt+1}/30)")
            time.sleep(30)
        else:
            print(f"  Launch error: {errors[:200]}")
            return
    else:
        print("  Max retries exhausted")
        return

    # 5. Poll for completion
    print("\n[5] Waiting for completion...")
    for i in range(120):  # max 20 min
        time.sleep(10)
        data = api_post("/backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = data.get("backtest", {})
        status = bt.get("status", "")
        progress = bt.get("progress", 0)
        
        elapsed = (i + 1) * 10
        if elapsed % 30 == 0:
            pstr = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
            print(f"  [{elapsed}s] status={status} progress={pstr}")
        
        if status in ("Completed.", "Completed"):
            break
        if "Error" in str(status) or "Runtime" in str(status):
            print(f"  BACKTEST ERROR: {status}")
            return
    else:
        print("  TIMEOUT after 20 min")
        return

    # 6. Read results
    stats = bt.get("statistics", {}) or {}
    print("\n" + "=" * 60)
    print("V2.0b-v2 BACKTEST RESULTS")
    print("=" * 60)
    
    metrics = [
        ("Net Profit", stats.get("Net Profit", "N/A")),
        ("CAGR", stats.get("Compounding Annual Return", "N/A")),
        ("Sharpe", stats.get("Sharpe Ratio", "N/A")),
        ("Sortino", stats.get("Sortino Ratio", "N/A")),
        ("Max DD", stats.get("Drawdown", "N/A")),
        ("Total Orders", stats.get("Total Orders", "N/A")),
        ("Win Rate", stats.get("Win Rate", "N/A")),
        ("P/L Ratio", stats.get("Profit-Loss Ratio", "N/A")),
        ("Annual Vol", stats.get("Annual Standard Deviation", "N/A")),
        ("PSR", stats.get("Probabilistic Sharpe Ratio", "N/A")),
    ]
    
    for name, val in metrics:
        print(f"  {name:20s}: {val}")

    # 7. Read logs for V2-specific stats
    print("\n[7] Reading logs...")
    all_logs = []
    for page in range(5):
        start = page * 200
        data = api_post("/backtests/read/log", {
            "projectId": PROJECT_ID, "backtestId": bt_id,
            "start": start, "end": start + 200, "query": " "
        })
        logs = data.get("logs", [])
        if not logs:
            break
        all_logs.extend(logs)
        if len(logs) < 200:
            break
    
    print(f"  Got {len(all_logs)} log entries")
    
    # Find V2-specific log lines
    for log in all_logs:
        msg = log if isinstance(log, str) else str(log)
        if any(kw in msg for kw in ["DD_CIRCUIT", "TRAIL_ON", "V2.0b-v2", "dd_halts", "FINAL REPORT"]):
            print(f"  LOG: {msg[:200]}")

    # Save result
    result_file = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v2_result.json"
    with open(result_file, "w") as f:
        json.dump({"bt_id": bt_id, "statistics": stats, "log_count": len(all_logs)}, f, indent=2)
    print(f"\n  Result saved to {result_file}")
    print(f"  BT ID: {bt_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
