"""
Finish remaining param loop combos (G39-G45).
Checks G39 status first, then runs missing combos.
"""
import sys
import time
import json
import os
import requests
from hashlib import sha256
from base64 import b64encode

# Force ASCII stdout for Windows
sys.stdout.reconfigure(encoding='ascii', errors='replace')

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

SOURCE_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_param_loop.py"

FIXED_PARAMS = {
    "start_year": "2023",
    "end_year": "2024",
    "end_month": "12",
    "dte_min": "14",
    "dte_max": "30",
}

# Full 45-combo grid to know labels
PT_VALUES = [0.30, 0.35, 0.40, 0.45, 0.50]
SL_VALUES = [-0.25, -0.20, -0.15]
RISK_VALUES = [0.04, 0.05, 0.06]

PARAM_GRID = []
idx = 0
for pt in PT_VALUES:
    for sl in SL_VALUES:
        for risk in RISK_VALUES:
            idx += 1
            is_baseline = (pt == 0.35 and sl == -0.20 and risk == 0.05)
            label = "BASELINE" if is_baseline else f"G{idx:02d}"
            PARAM_GRID.append({
                "profit_target_pct": f"{pt:.2f}",
                "stop_loss_pct": f"{sl:.2f}",
                "risk_per_trade": f"{risk:.2f}",
                "label": label,
            })


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


def get_completed_labels():
    """Get labels of all completed ParamLoop backtests."""
    data = api_post("/backtests/list", {"projectId": PROJECT_ID})
    completed = {}
    for bt in data.get("backtests", []):
        name = bt.get("name", "")
        status = bt.get("status", "")
        if "ParamLoop" in name and status in ("Completed.", "Completed"):
            # Extract label: "V2.0b ParamLoop G39 PT=..." -> "G39"
            parts = name.split()
            for p in parts:
                if p.startswith("G") or p == "BASELINE":
                    completed[p] = bt.get("backtestId", "")
                    break
    return completed


def check_g39_status():
    """Check if G39 is still running or completed."""
    bt_id = "0dd93f92bcf33a2b2cc4196c622423b9"
    data = api_post("/backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
    bt = data.get("backtest", {})
    status = bt.get("status", "")
    progress = bt.get("progress", 0)
    print(f"G39 status: {status}, progress: {progress}")
    return status, bt


def wait_for_g39():
    """Wait for G39 to complete if it's still running."""
    status, bt = check_g39_status()
    if status in ("Completed.", "Completed"):
        print("G39 already completed!")
        return True
    if "Error" in str(status) or "Runtime" in str(status):
        print(f"G39 errored: {status}")
        return False

    # Wait up to 10 minutes
    for i in range(60):
        time.sleep(10)
        status, bt = check_g39_status()
        if status in ("Completed.", "Completed"):
            print(f"G39 completed after {(i+1)*10}s wait")
            return True
        if "Error" in str(status) or "Runtime" in str(status):
            print(f"G39 errored: {status}")
            return False
    print("G39 timed out after 10 min, will need to relaunch")
    return False


def set_parameters(params_dict):
    param_list = [{"key": k, "value": v} for k, v in params_dict.items()]
    data = api_post("/projects/update", {"projectId": PROJECT_ID, "parameters": param_list})
    return data.get("success", False)


def compile_project():
    data = api_post("/compile/create", {"projectId": PROJECT_ID})
    cid = data.get("compileId", "")
    state = data.get("state", "")
    waited = 0
    while state not in ("BuildSuccess", "BuildError") and waited < 120:
        time.sleep(3)
        waited += 3
        data = api_post("/compile/read", {"projectId": PROJECT_ID, "compileId": cid})
        state = data.get("state", "")
    if state == "BuildSuccess":
        return True, cid
    print(f"  COMPILE FAILED: {state}")
    return False, cid


def launch_backtest(compile_id, bt_name, max_retries=30, retry_delay=30):
    for attempt in range(max_retries):
        data = api_post("/backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": bt_name})
        if data.get("success"):
            bt = data.get("backtest", {})
            return True, bt.get("backtestId", "")
        errors = " ".join(data.get("errors", []))
        if "no spare nodes" in errors.lower() or "nodes available" in errors.lower():
            print(f"  Node busy, waiting {retry_delay}s... ({attempt+1}/{max_retries})")
            time.sleep(retry_delay)
            continue
        print(f"  Launch error: {errors[:200]}")
        return False, ""
    return False, ""


def poll_backtest(bt_id, max_wait=600):
    waited = 0
    while waited < max_wait:
        time.sleep(10)
        waited += 10
        data = api_post("/backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt = data.get("backtest", {})
        status = bt.get("status", "")
        progress = bt.get("progress", 0)
        if waited % 30 == 0:
            pstr = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
            print(f"  [{waited}s] status={status} progress={pstr}")
        if status in ("Completed.", "Completed"):
            return bt
        if "Error" in str(status) or "Runtime" in str(status):
            print(f"  BACKTEST ERROR: {status}")
            return bt
    print(f"  TIMEOUT after {max_wait}s")
    return {}


def read_logs(bt_id, max_pages=5):
    all_logs = []
    for page in range(max_pages):
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
    return all_logs


def extract_metrics(bt_result, logs):
    stats = bt_result.get("statistics", {}) or {}

    def safe_float(s, default=0.0):
        try:
            return float(str(s).replace("%", "").replace(",", ""))
        except:
            return default

    def safe_int(s, default=0):
        try:
            return int(str(s).replace(",", ""))
        except:
            return default

    net_profit = safe_float(stats.get("Net Profit", "0"))
    sharpe = safe_float(stats.get("Sharpe Ratio", "0"))
    sortino = safe_float(stats.get("Sortino Ratio", "0"))
    max_dd = safe_float(stats.get("Drawdown", "0"))
    cagr = safe_float(stats.get("Compounding Annual Return", "0"))
    total_trades = safe_int(stats.get("Total Orders", "0"))
    win_rate = safe_float(stats.get("Win Rate", "0"))
    pf = safe_float(stats.get("Profit-Loss Ratio", "0"))
    annual_vol = safe_float(stats.get("Annual Standard Deviation", "0"))
    psr = safe_float(stats.get("Probabilistic Sharpe Ratio", "0"))

    # DD recovery from logs
    dd_recovery_days = 0
    for entry in logs:
        msg = entry if isinstance(entry, str) else str(entry)
        if "DD_RECOVERY_DAYS" in msg:
            try:
                dd_recovery_days = int(msg.split("DD_RECOVERY_DAYS=")[1].split()[0])
            except:
                pass

    # Kill gates
    passes_gates = (cagr >= 12.0) and (sharpe >= 1.0)

    return {
        "net_profit": net_profit,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "cagr": cagr,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": pf,
        "annual_vol": annual_vol,
        "psr": psr,
        "dd_recovery_days": dd_recovery_days,
        "passes_gates": passes_gates,
    }


def run_combo(combo):
    label = combo["label"]
    params = {k: v for k, v in combo.items() if k != "label"}
    all_params = {**params, **FIXED_PARAMS}

    print(f"\n{'='*60}")
    print(f"[{label}] PT={combo['profit_target_pct']} SL={combo['stop_loss_pct']} R={combo['risk_per_trade']}")
    print(f"  Time: {time.strftime('%H:%M:%S')}")

    print("  Setting parameters...")
    if not set_parameters(all_params):
        print("  FAILED to set params")
        return None

    print("  Compiling...")
    ok, cid = compile_project()
    if not ok:
        return None
    print(f"  Compiled: {cid}")

    bt_name = f"V2.0b ParamLoop {label} PT={combo['profit_target_pct']} SL={combo['stop_loss_pct']} R={combo['risk_per_trade']}"
    print(f"  Launching: {bt_name}")
    ok, bt_id = launch_backtest(cid, bt_name)
    if not ok:
        return None
    print(f"  BT ID: {bt_id}")

    print("  Waiting for completion...")
    bt_result = poll_backtest(bt_id)
    if not bt_result:
        return None

    print("  Reading logs...")
    logs = read_logs(bt_id)
    print(f"  Got {len(logs)} log entries")

    metrics = extract_metrics(bt_result, logs)
    gate = "PASS" if metrics["passes_gates"] else "FAIL"

    print(f"  ----------------------------------")
    print(f"  Return: {metrics['net_profit']:+.2f}% | CAGR: {metrics['cagr']:.1f}%")
    print(f"  Sharpe: {metrics['sharpe']:.3f} | Sortino: {metrics['sortino']:.3f}")
    print(f"  Max DD: {metrics['max_dd']:.1f}% | Trades: {metrics['total_trades']}")
    print(f"  WR: {metrics['win_rate']:.0f}% | PF: {metrics['profit_factor']:.2f}")
    print(f"  Gates: {gate}")
    print(f"  ----------------------------------")

    return {
        "label": label,
        "bt_id": bt_id,
        **combo,
        **metrics,
    }


def main():
    print("=" * 60)
    print("FINISHING PARAM LOOP (remaining combos)")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check which are already completed
    completed = get_completed_labels()
    print(f"\nAlready completed: {len(completed)} combos")
    print(f"Labels: {sorted(completed.keys())}")

    # First handle G39 if not completed
    if "G39" not in completed:
        print("\nG39 not completed, checking status...")
        g39_done = wait_for_g39()
        if g39_done:
            completed = get_completed_labels()  # refresh
        else:
            print("G39 failed/timed out, will relaunch it")

    # Find remaining combos
    remaining = []
    for combo in PARAM_GRID:
        if combo["label"] not in completed:
            remaining.append(combo)

    if not remaining:
        print("\nAll 45 combos completed!")
        return

    print(f"\nRemaining combos: {[c['label'] for c in remaining]}")

    # Upload code once
    print("\nUploading code...")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        code = f.read()
    data = api_post("/files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    if not data.get("success"):
        data = api_post("/files/create", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)
    print(f"  Upload: {'OK' if data.get('success') else 'FAILED'}")

    # Run each remaining combo
    results = []
    for combo in remaining:
        result = run_combo(combo)
        if result:
            results.append(result)

    print(f"\n{'='*60}")
    print(f"DONE. Ran {len(results)} combos.")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for r in results:
        gate = "PASS" if r["passes_gates"] else "FAIL"
        print(f"  {r['label']}: Return={r['net_profit']:+.1f}% Sharpe={r['sharpe']:.3f} [{gate}]")


if __name__ == "__main__":
    main()
