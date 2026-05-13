"""
V5 Isolated Fix A/B Test Runner
Uploads V5-parametrized code once, then runs 3 backtests sequentially
with different fix combinations enabled.

Tests:
  V5a: FIX3 only (QQQ regime filter)
  V5b: FIX2 only (trailing, looser: activation=0.25, trail=0.40)
  V5c: FIX2 + FIX3 (no FIX4)
"""
import hashlib, base64, time, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
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
            print(f"  API attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise

# Define test configs
TESTS = [
    {
        "name": "V5a FIX3-only",
        "params": {
            "enable_fix2": "0", "enable_fix3": "1", "enable_fix4": "0",
            "trail_act": "0.20", "trail_pct": "0.50",
        }
    },
    {
        "name": "V5b FIX2-only-loose",
        "params": {
            "enable_fix2": "1", "enable_fix3": "0", "enable_fix4": "0",
            "trail_act": "0.25", "trail_pct": "0.40",
        }
    },
    {
        "name": "V5c FIX2+FIX3",
        "params": {
            "enable_fix2": "1", "enable_fix3": "1", "enable_fix4": "0",
            "trail_act": "0.25", "trail_pct": "0.40",
        }
    },
]

# Base params (same as V4-B)
BASE_PARAMS = {
    "profit_target_pct": "0.35",
    "stop_loss_pct": "-0.20",
    "risk_per_trade": "0.04",
    "dte_min": "14",
    "dte_max": "30",
    "start_year": "2023",
    "end_year": "2026",
    "end_month": "4",
}

def main():
    # Step 1: Upload code (once)
    print("=== UPLOADING V5-PARAM CODE ===")
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v5.py", "r", encoding="utf-8") as f:
        code = f.read()
    resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    print(f"  Upload: success={resp.get('success')}")
    if not resp.get("success"):
        print("FATAL: Upload failed")
        sys.exit(1)

    results = {}

    for test in TESTS:
        name = test["name"]
        print(f"\n{'='*60}")
        print(f"=== TEST: {name} ===")
        print(f"{'='*60}")

        # Set params
        all_params = {**BASE_PARAMS, **test["params"]}
        param_list = [{"key": k, "value": v} for k, v in all_params.items()]
        resp = api("projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
        print(f"  Params set: success={resp.get('success')}")

        # Verify
        resp = api("projects/read", {"projectId": PROJECT_ID})
        if resp.get("success"):
            proj = resp["projects"][0] if isinstance(resp["projects"], list) else resp["projects"]
            p = {x["key"]: x["value"] for x in proj.get("parameters", [])}
            print(f"  Verified: fix2={p.get('enable_fix2')}, fix3={p.get('enable_fix3')}, fix4={p.get('enable_fix4')}")
            print(f"  trail_act={p.get('trail_act')}, trail_pct={p.get('trail_pct')}")

        # Compile
        resp = api("compile/create", {"projectId": PROJECT_ID})
        compile_id = resp.get("compileId")
        state = resp.get("state")
        print(f"  Compile: id={compile_id} state={state}")

        for i in range(20):
            if state == "BuildSuccess":
                break
            time.sleep(3)
            resp = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
            state = resp.get("state")

        if state != "BuildSuccess":
            print(f"  COMPILE FAILED: {state}")
            errors = resp.get("errors", [])
            for e in errors:
                print(f"  ERR: {e}")
            continue

        # Launch backtest
        resp = api("backtests/create", {
            "projectId": PROJECT_ID,
            "compileId": compile_id,
            "backtestName": name,
        })
        bt = resp.get("backtest", resp)
        bt_id = bt.get("backtestId")
        print(f"  Backtest launched: {bt_id}")

        if not bt_id:
            print(f"  FAILED to launch: {resp}")
            continue

        # Poll
        completed = False
        for i in range(120):
            time.sleep(10)
            resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
            bt = resp.get("backtest", resp)
            progress = bt.get("progress", 0)
            completed = bt.get("completed", False)
            prog_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
            if i % 6 == 0:  # Print every minute
                print(f"  Poll {i+1}: {prog_str}")
            if completed:
                break

        if not completed:
            print(f"  WARNING: {name} did not complete in time")
            results[name] = {"status": "TIMEOUT", "bt_id": bt_id}
            continue

        # Extract results
        stats = bt.get("statistics", {})
        result = {
            "bt_id": bt_id,
            "return": stats.get("Net Profit", "?"),
            "cagr": stats.get("Compounding Annual Return", "?"),
            "sharpe": stats.get("Sharpe Ratio", "?"),
            "dd": stats.get("Drawdown", "?"),
            "trades": stats.get("Total Orders", "?"),
            "wr": stats.get("Win Rate", "?"),
            "pf": stats.get("Profit-Loss Ratio", "?"),
            "end_equity": stats.get("End Equity", "?"),
        }
        results[name] = result

        print(f"\n  --- {name} RESULTS ---")
        for k, v in result.items():
            print(f"  {k}: {v}")

        # Save raw
        with open(f"C:/AI_VAULT/tmp_agent/strategies/yoel_options/{name.replace(' ','_').lower()}_raw.json", "w") as f:
            json.dump(resp, f, indent=2, default=str)

    # Final comparison table
    print(f"\n{'='*60}")
    print("=== COMPARISON TABLE ===")
    print(f"{'='*60}")
    print(f"{'Config':<25} {'Return':>10} {'CAGR':>10} {'Sharpe':>10} {'DD':>10} {'WR':>8} {'Trades':>8}")
    print("-" * 81)

    # V4-B baseline for reference
    print(f"{'V4-B FULL (baseline)':<25} {'91.5%':>10} {'22.1%':>10} {'0.53':>10} {'37.7%':>10} {'~53%':>8} {'~370':>8}")
    print(f"{'V5 ALL FIXES (failed)':<25} {'8.8%':>10} {'2.6%':>10} {'-0.21':>10} {'20.0%':>10} {'53%':>8} {'336':>8}")

    for name, r in results.items():
        if isinstance(r, dict) and "bt_id" in r:
            print(f"{name:<25} {str(r.get('return','?')):>10} {str(r.get('cagr','?')):>10} {str(r.get('sharpe','?')):>10} {str(r.get('dd','?')):>10} {str(r.get('wr','?')):>8} {str(r.get('trades','?')):>8}")

    # Save results
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_ablation_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print("ALL TESTS COMPLETE")

if __name__ == "__main__":
    main()
