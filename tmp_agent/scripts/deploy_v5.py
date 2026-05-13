"""
Deploy V5 to QC: upload code, set params, compile, launch backtest.
"""
import hashlib, base64, time, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
ORG = "6d487993ca17881264c2ac55e41ae539"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {
        "Authorization": f"Basic {b64}",
        "Timestamp": ts,
        "Content-Type": "application/json",
    }

def api(method, endpoint, payload=None):
    url = f"{BASE}/{endpoint}"
    for attempt in range(3):
        try:
            if method == "GET":
                r = requests.get(url, headers=auth_headers(), timeout=30)
            else:
                r = requests.post(url, headers=auth_headers(), json=payload or {}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise

def main():
    # 1. Read V5 code
    print("=== STEP 1: Reading V5 code ===")
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_v5.py", "r", encoding="utf-8") as f:
        code = f.read()
    print(f"  Code length: {len(code)} chars")

    # 2. Upload as main.py
    print("=== STEP 2: Uploading main.py ===")
    resp = api("POST", "files/update", {
        "projectId": PROJECT_ID,
        "name": "main.py",
        "content": code,
    })
    print(f"  Upload response: success={resp.get('success')}")
    if not resp.get("success"):
        # Try create instead
        print("  Trying files/create instead...")
        resp = api("POST", "files/create", {
            "projectId": PROJECT_ID,
            "name": "main.py",
            "content": code,
        })
        print(f"  Create response: success={resp.get('success')}")

    # 3. Set parameters
    print("=== STEP 3: Setting parameters ===")
    params = [
        {"key": "profit_target_pct", "value": "0.35"},
        {"key": "stop_loss_pct", "value": "-0.20"},
        {"key": "risk_per_trade", "value": "0.04"},
        {"key": "dte_min", "value": "14"},
        {"key": "dte_max", "value": "30"},
        {"key": "start_year", "value": "2023"},
        {"key": "end_year", "value": "2026"},
        {"key": "end_month", "value": "4"},
    ]
    resp = api("POST", "projects/update", {
        "projectId": PROJECT_ID,
        "parameters": params,
    })
    print(f"  Params set: success={resp.get('success')}")

    # 3b. Verify params
    print("=== STEP 3b: Verifying parameters ===")
    resp = api("POST", "projects/read", {"projectId": PROJECT_ID})
    if resp.get("success") and "projects" in resp:
        proj = resp["projects"][0] if isinstance(resp["projects"], list) else resp["projects"]
        proj_params = proj.get("parameters", [])
        print(f"  Project params: {json.dumps(proj_params, indent=2)}")
    else:
        print(f"  Read response: {json.dumps(resp, indent=2)[:500]}")

    # 4. Compile
    print("=== STEP 4: Compiling ===")
    resp = api("POST", "compile/create", {"projectId": PROJECT_ID})
    print(f"  Compile response: success={resp.get('success')}")
    compile_id = resp.get("compileId")
    state = resp.get("state")
    print(f"  compileId={compile_id} state={state}")

    if not compile_id:
        print("FATAL: No compile ID returned")
        print(json.dumps(resp, indent=2)[:1000])
        sys.exit(1)

    # Wait for compile
    for i in range(20):
        if state == "BuildSuccess":
            break
        time.sleep(3)
        resp = api("POST", "compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
        state = resp.get("state")
        print(f"  Compile poll {i+1}: state={state}")

    if state != "BuildSuccess":
        print(f"FATAL: Compile failed with state={state}")
        errors = resp.get("errors", [])
        for e in errors:
            print(f"  ERROR: {e}")
        logs = resp.get("logs", [])
        for l in logs:
            print(f"  LOG: {l}")
        sys.exit(1)

    print("  Compile SUCCESS!")

    # 5. Launch backtest
    print("=== STEP 5: Launching backtest 'V5 FULL 2023-2026' ===")
    resp = api("POST", "backtests/create", {
        "projectId": PROJECT_ID,
        "compileId": compile_id,
        "backtestName": "V5 FULL 2023-2026",
    })
    print(f"  Backtest create: success={resp.get('success')}")
    bt = resp.get("backtest", resp)
    bt_id = bt.get("backtestId")
    print(f"  backtestId={bt_id}")

    if not bt_id:
        print(f"FATAL: No backtest ID")
        print(json.dumps(resp, indent=2)[:1000])
        sys.exit(1)

    # 6. Poll backtest
    print("=== STEP 6: Polling backtest ===")
    for i in range(120):
        time.sleep(10)
        resp = api("POST", "backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = resp.get("backtest", resp)
        progress = bt.get("progress", 0)
        completed = bt.get("completed", False)

        if isinstance(progress, float):
            prog_str = f"{progress:.0%}"
        else:
            prog_str = str(progress)

        print(f"  Poll {i+1}: progress={prog_str} completed={completed}")

        if completed:
            break

    if not completed:
        print("WARNING: Backtest did not complete in time (20 min). Check manually.")
        print(f"  backtestId={bt_id}")
        sys.exit(0)

    # 7. Extract results
    print("=" * 60)
    print("=== BACKTEST RESULTS ===")
    print("=" * 60)

    # Save raw response
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_full_2023_2026_raw.json", "w") as f:
        json.dump(resp, f, indent=2, default=str)
    print("  Raw data saved to v5_full_2023_2026_raw.json")

    result = bt.get("result", {})
    stats = result.get("Statistics", {}) or bt.get("statistics", {})

    print(f"  backtestId: {bt_id}")
    for key in ["Total Return", "CAGR", "Sharpe Ratio", "Maximum Drawdown",
                 "Total Trades", "Win Rate", "Profit-Loss Ratio", "Net Profit",
                 "Average Win", "Average Loss", "Compounding Annual Return",
                 "Drawdown", "Total Net Profit"]:
        if key in stats:
            print(f"  {key}: {stats[key]}")

    # Print all stats
    print("--- ALL STATISTICS ---")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    print("=" * 60)
    print("DONE")

if __name__ == "__main__":
    main()
