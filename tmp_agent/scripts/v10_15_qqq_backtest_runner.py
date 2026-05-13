"""
Runner for v10.15 QQQ – uploads the QQQ algorithm, runs IS, OOS y Full backtests y guarda todas las métricas.
"""

import hashlib, base64, time, json, requests, sys

# ==========================================================================
# CONFIG
# ==========================================================================
PROJECT_ID = 29490680
USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"

# AUTH helper

def auth_headers():
    ts = str(int(time.time()))
    token_hash = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_hash}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

# API wrapper

def api(endpoint, payload, method="POST"):
    for attempt in range(3):
        try:
            url = f"{BASE}/{endpoint}"
            if method == "POST":
                r = requests.post(url, headers=auth_headers(), json=payload, timeout=120)
            else:
                r = requests.get(url, headers=auth_headers(), params=payload, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2**attempt)
            else:
                raise

# SUBMIT ALGORITHM

def upload_algorithm():
    # This file now contains the full algorithm
    with open("C:/AI_VAULT/tmp_agent/strategies/v10_15_qqq.py", "r", encoding="utf-8") as f:
        code = f.read()
    resp = api("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    if not resp.get("success"):
        print("Upload failed", resp)
        sys.exit(1)
    print("Algorithm uploaded (main.py)")

# BACKTEST

def launch_backtest(start_year, end_year, name_suffix):
    # set params
    param_list = [
        {"key": "start_year", "value": str(start_year)},
        {"key": "end_year", "value": str(end_year)},
        {"key": "end_month", "value": "12"},
    ]
    api("projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    # compile
    comp = api("compile/create", {"projectId": PROJECT_ID})
    compile_id = comp.get("compileId")
    # wait for build
    for _ in range(60):
        state = api("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id}).get("state")
        if state == "BuildSuccess":
            break
        time.sleep(5)
    if state != "BuildSuccess":
        print("Compile failed", comp)
        return None
    # launch
    resp = api("backtests/create", {
        "projectId": PROJECT_ID,
        "compileId": compile_id,
        "backtestName": f"v10_15_{name_suffix}",
    })
    bt = resp.get("backtest")
    bt_id = bt.get("backtestId")
    print(f"Backtest {name_suffix} launched: {bt_id}")
    return bt_id

# POLL

def wait_backtest(bt_id):
    for _ in range(120):
        time.sleep(10)
        resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = resp.get("backtest")
        if bt.get("completed"):
            return bt
    print("Timeout waiting for backtest")
    return None

# CISIONES

def extract_metrics(bt):
    stats = {}
    if isinstance(bt, dict):
        if "statistics" in bt:
            stats = bt["statistics"]
        elif "output" in bt and isinstance(bt["output"], dict) and "statistics" in bt["output"]:
            stats = bt["output"]["statistics"]
    keys = [
        "Sharpe Ratio", "Compounding Annual Return", "Drawdown", "Net Profit",
        "Total Orders", "Win Rate", "Profit-Loss Ratio", "End Equity",
        "Alpha", "Beta", "Annual Standard Deviation", "Information Ratio",
        "Tracking Error", "Sortino Ratio", "Capacity", "Fees", "Turnover",
        "Omega", "Calmar Ratio", "Kappa 3", "Kappa 4", "Kappa 5",
        "Skew", "Kurtosis", "Mean Absolute Deviation",
        "Average Trade Duration", "Average Holding Period",
        "Average Trade Net Profit"
    ]
    out = {k: stats.get(k, "?") for k in keys}
    return out

# MAIN

def main():
    upload_algorithm()
    results = {}
    # IS
    is_id = launch_backtest(2023, 2024, "IS")
    if is_id:
        bt = wait_backtest(is_id)
        if bt:
            results["IS"] = extract_metrics(bt)
    # OOS
    oos_id = launch_backtest(2025, 2026, "OOS")
    if oos_id:
        bt = wait_backtest(oos_id)
        if bt:
            results["OOS"] = extract_metrics(bt)
    # FULL
    full_id = launch_backtest(2023, 2026, "FULL")
    if full_id:
        bt = wait_backtest(full_id)
        if bt:
            results["FULL"] = extract_metrics(bt)
    # Save
    out_path = "C:/AI_VAULT/tmp_agent/strategies/v10_15_qqq_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"All results saved to {out_path}")

if __name__ == "__main__":
    main()
