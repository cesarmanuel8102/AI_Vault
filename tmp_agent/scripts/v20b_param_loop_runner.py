"""
V2.0b Parameter Stability Loop Runner
======================================
Deploys v20b_param_loop.py to QC with different parameter combinations,
waits for completion, reads results, logs to CSV.

Grid: 3 params (profit_target_pct, stop_loss_pct, risk_per_trade) × variations
Kill gates: CAGR >= 12%, Sharpe >= 1.0
Score: Sharpe * 0.4 + (Return/DD) * 0.3 + Consistency * 0.2 - DD_penalty * 0.1

Sequential execution — only 1 compute node available.
"""

import sys
import time
import json
import csv
import os
import requests
from hashlib import sha256
from base64 import b64encode
from datetime import datetime

# ════════════════════════════════════════════════
# QC API CONFIG
# ════════════════════════════════════════════════
UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680

SOURCE_FILE = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_param_loop.py"
RESULTS_CSV = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/param_loop_results.csv"
RESULTS_JSON = "C:/AI_VAULT/tmp_agent/strategies/yoel_options/param_loop_results.json"

# ════════════════════════════════════════════════
# PARAMETER GRID
# ════════════════════════════════════════════════
# Baseline: PT=0.35, SL=-0.20, risk=0.05
# Variations: ±1-2 steps around baseline for each param
# Total: 12 combos (manageable, ~1-2 hours)

# Full grid: PT=[0.30,0.35,0.40,0.45,0.50] x SL=[-0.25,-0.20,-0.15] x Risk=[0.04,0.05,0.06]
# Total: 5 x 3 x 3 = 45 combinations
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

# Fixed params for all runs
FIXED_PARAMS = {
    "start_year": "2023",
    "end_year": "2024",
    "end_month": "12",
    "dte_min": "14",
    "dte_max": "30",
}

# ════════════════════════════════════════════════
# QC API HELPERS
# ════════════════════════════════════════════════

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def set_parameters(params_dict):
    """Set project parameters on QC."""
    param_list = [{"key": k, "value": v} for k, v in params_dict.items()]
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/projects/update", headers=headers(), json={
                "projectId": PROJECT_ID, "parameters": param_list
            }, timeout=30)
            return r.json().get("success", False)
        except Exception as e:
            print(f"    set_parameters error (attempt {attempt+1}): {str(e)[:60]}")
            time.sleep(5)
    return False


def upload_code():
    """Upload v20b_param_loop.py as main.py to QC project."""
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        code = f.read()
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/files/update", headers=headers(), json={
                "projectId": PROJECT_ID, "name": "main.py", "content": code
            }, timeout=60)
            resp = r.json()
            if not resp.get("success"):
                r = requests.post(f"{BASE}/files/create", headers=headers(), json={
                    "projectId": PROJECT_ID, "name": "main.py", "content": code
                }, timeout=60)
                resp = r.json()
            return resp.get("success", False)
        except Exception as e:
            print(f"    upload_code error (attempt {attempt+1}): {str(e)[:60]}")
            time.sleep(10)
    return False


def compile_project():
    """Compile and wait for result. Returns (success, compile_id)."""
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/compile/create", headers=headers(), json={"projectId": PROJECT_ID}, timeout=30)
            data = r.json()
            cid = data.get("compileId", "")
            state = data.get("state", "")
            break
        except Exception as e:
            print(f"    compile create error (attempt {attempt+1}): {str(e)[:60]}")
            time.sleep(10)
            if attempt == 2:
                return False, ""

    waited = 0
    while state not in ("BuildSuccess", "BuildError") and waited < 120:
        time.sleep(3)
        waited += 3
        try:
            r = requests.post(f"{BASE}/compile/read", headers=headers(), json={
                "projectId": PROJECT_ID, "compileId": cid
            }, timeout=30)
            data = r.json()
            state = data.get("state", "")
        except Exception as e:
            print(f"    compile poll error: {str(e)[:60]}")

    if state == "BuildSuccess":
        return True, cid
    else:
        print(f"  COMPILE FAILED: {json.dumps(data, indent=2)[:500]}")
        return False, cid


def launch_backtest(compile_id, bt_name, max_retries=30, retry_delay=30):
    """Launch backtest with retry on 'no spare nodes' and network errors. Returns (success, bt_id)."""
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
                "projectId": PROJECT_ID, "compileId": compile_id, "backtestName": bt_name
            }, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"    Launch network error (attempt {attempt+1}): {str(e)[:60]}")
            time.sleep(retry_delay)
            continue

        if data.get("success"):
            bt = data.get("backtest", {})
            bt_id = bt.get("backtestId", "")
            return True, bt_id
        
        errors = data.get("errors", [])
        error_str = " ".join(errors) if isinstance(errors, list) else str(errors)
        
        if "no spare nodes" in error_str.lower() or "nodes available" in error_str.lower():
            if attempt < max_retries - 1:
                print(f"    Node busy, waiting {retry_delay}s... (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                continue
        
        # Non-retryable error
        print(f"    Launch error: {error_str[:200]}")
        return False, ""
    
    print(f"    Max retries ({max_retries}) exhausted")
    return False, ""


def poll_backtest(bt_id, max_wait=600):
    """Poll until backtest completes. Returns final status dict."""
    waited = 0
    net_errors = 0
    while waited < max_wait:
        time.sleep(10)
        waited += 10
        try:
            r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
                "projectId": PROJECT_ID, "backtestId": bt_id
            }, timeout=30)
            data = r.json()
            bt = data.get("backtest", {})
            status = bt.get("status", "")
            progress = bt.get("progress", 0)
            net_errors = 0  # reset on success
        except Exception as e:
            net_errors += 1
            print(f"    [{waited}s] Network error ({net_errors}): {str(e)[:80]}")
            if net_errors >= 5:
                print(f"    Too many network errors, aborting poll")
                return {}
            continue

        if waited % 30 == 0:
            print(f"    [{waited}s] status={status} progress={progress:.0%}" if isinstance(progress, float) else f"    [{waited}s] status={status}")

        if status in ("Completed.", "Completed"):
            return bt
        if "Error" in str(status) or "Runtime" in str(status):
            print(f"    BACKTEST ERROR: {status}")
            return bt

    print(f"    TIMEOUT after {max_wait}s")
    return {}


def read_logs(bt_id, max_pages=5):
    """Read all logs from completed backtest."""
    all_logs = []
    for page in range(max_pages):
        start = page * 200
        for attempt in range(3):
            try:
                r = requests.post(f"{BASE}/backtests/read/log", headers=headers(), json={
                    "projectId": PROJECT_ID, "backtestId": bt_id,
                    "start": start, "end": start + 200, "query": " "
                }, timeout=30)
                data = r.json()
                logs = data.get("logs", [])
                break
            except Exception as e:
                print(f"    Log read error (attempt {attempt+1}): {str(e)[:60]}")
                if attempt == 2:
                    logs = []
                time.sleep(5)
        if not logs:
            break
        all_logs.extend(logs)
        if len(logs) < 200:
            break
    return all_logs


def extract_metrics(bt_result, logs):
    """Extract key metrics from backtest result and logs."""
    stats = bt_result.get("statistics", {}) or {}
    result = bt_result.get("result", {}) or {}
    
    # From QC statistics
    net_profit_str = stats.get("Net Profit", "0%").replace("%", "").replace(",", "")
    sharpe_str = stats.get("Sharpe Ratio", "0")
    sortino_str = stats.get("Sortino Ratio", "0")
    dd_str = stats.get("Drawdown", "0%").replace("%", "").replace(",", "")
    cagr_str = stats.get("Compounding Annual Return", "0%").replace("%", "").replace(",", "")
    total_trades_str = stats.get("Total Orders", "0")
    win_rate_str = stats.get("Win Rate", "0%").replace("%", "")
    pf_str = stats.get("Profit-Loss Ratio", "0")
    
    try:
        net_profit = float(net_profit_str)
    except:
        net_profit = 0.0
    try:
        sharpe = float(sharpe_str)
    except:
        sharpe = 0.0
    try:
        sortino = float(sortino_str)
    except:
        sortino = 0.0
    try:
        max_dd = float(dd_str)
    except:
        max_dd = 0.0
    try:
        cagr = float(cagr_str)
    except:
        cagr = 0.0
    try:
        total_trades = int(total_trades_str)
    except:
        total_trades = 0
    try:
        win_rate = float(win_rate_str)
    except:
        win_rate = 0.0
    try:
        pf = float(pf_str)
    except:
        pf = 0.0

    # Parse final equity from logs (look for "Return:" line)
    final_equity = 10000
    for log in reversed(logs):
        msg = log if isinstance(log, str) else str(log)
        if "Return:" in msg and "Equity:" in msg:
            try:
                eq_part = msg.split("Equity:")[1].split("|")[0].strip()
                final_equity = float(eq_part.replace("$", "").replace(",", ""))
            except:
                pass
            break

    # Count trades from logs
    trade_count_from_logs = 0
    for log in logs:
        msg = log if isinstance(log, str) else str(log)
        if "Trades:" in msg and "Wins:" in msg:
            try:
                t_part = msg.split("Trades:")[1].split("|")[0].strip()
                trade_count_from_logs = int(t_part)
            except:
                pass
            break

    return {
        "net_profit_pct": net_profit,
        "cagr_pct": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd_pct": max_dd,
        "total_orders": total_trades,
        "trade_count": trade_count_from_logs or total_trades,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "final_equity": final_equity,
    }


def score_result(metrics):
    """Score function: Sharpe*0.4 + (Return/DD)*0.3 + Consistency*0.2 - DD_penalty*0.1"""
    sharpe = metrics["sharpe"]
    ret = metrics["net_profit_pct"]
    dd = max(metrics["max_dd_pct"], 1.0)  # avoid div by zero
    trades = metrics["trade_count"]

    # Return / DD ratio (normalized)
    ret_dd = ret / dd if dd > 0 else 0

    # Consistency: trade count (more = better, normalized to baseline 123)
    consistency = min(trades / 123.0, 1.5)  # cap at 1.5x

    # DD penalty: severe if > 50%
    dd_penalty = max(0, (dd - 40) / 10)  # 0 if DD<40%, linear after

    score = sharpe * 0.4 + ret_dd * 0.3 + consistency * 0.2 - dd_penalty * 0.1
    return round(score, 4)


def passes_kill_gates(metrics):
    """Check kill gates: CAGR >= 12%, Sharpe >= 1.0"""
    return metrics["cagr_pct"] >= 12.0 and metrics["sharpe"] >= 1.0


# ════════════════════════════════════════════════
# MAIN LOOP
# ════════════════════════════════════════════════

def list_existing_backtests():
    """List all completed ParamLoop backtests on the project. Returns dict of label -> bt data."""
    r = requests.post(f"{BASE}/backtests/list", headers=headers(), json={"projectId": PROJECT_ID})
    data = r.json()
    backtests = data.get("backtests", [])
    
    completed = {}
    for bt in backtests:
        name = bt.get("name", "")
        status = bt.get("status", "")
        if "ParamLoop" in name and status in ("Completed.", "Completed"):
            # Extract label from name: "V2.0b ParamLoop G01 PT=0.30 SL=-0.25 R=0.04"
            # or "V2.0b ParamLoop BASELINE PT=0.35 SL=-0.20 R=0.05"
            parts = name.split("ParamLoop ")
            if len(parts) > 1:
                label_part = parts[1].split(" PT=")[0].strip()
                completed[label_part] = bt
    
    return completed


def read_completed_backtest(bt_id):
    """Read full stats from a completed backtest."""
    r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={
        "projectId": PROJECT_ID, "backtestId": bt_id
    })
    data = r.json()
    bt = data.get("backtest", data)
    return bt


def extract_metrics_from_stats(stats):
    """Extract metrics from the statistics dict (used for both fresh and resumed backtests)."""
    def safe_float(s, default=0.0):
        try:
            return float(str(s).replace("%", "").replace(",", "").replace("$", ""))
        except:
            return default
    def safe_int(s, default=0):
        try:
            return int(str(s).replace(",", ""))
        except:
            return default

    return {
        "net_profit_pct": safe_float(stats.get("Net Profit", "0")),
        "cagr_pct": safe_float(stats.get("Compounding Annual Return", "0")),
        "sharpe": safe_float(stats.get("Sharpe Ratio", "0")),
        "sortino": safe_float(stats.get("Sortino Ratio", "0")),
        "max_dd_pct": safe_float(stats.get("Drawdown", "0")),
        "total_orders": safe_int(stats.get("Total Orders", "0")),
        "trade_count": safe_int(stats.get("Total Orders", "0")),
        "win_rate_pct": safe_float(stats.get("Win Rate", "0")),
        "profit_factor": safe_float(stats.get("Profit-Loss Ratio", "0")),
        "final_equity": safe_float(stats.get("End Equity", "10000")),
    }


def main():
    print("=" * 70)
    print("V2.0b PARAMETER STABILITY LOOP")
    print(f"Grid: {len(PARAM_GRID)} combinations")
    print(f"Kill gates: CAGR >= 12%, Sharpe >= 1.0")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ════════════════════════════════════════════════
    # RESUME LOGIC: Check for already-completed backtests
    # ════════════════════════════════════════════════
    print("\n[RESUME] Checking for already-completed backtests...")
    existing = list_existing_backtests()
    print(f"  Found {len(existing)} completed ParamLoop backtests: {list(existing.keys())}")

    all_results = []
    skipped = 0

    # Recover results from already-completed backtests
    for label, bt_data in existing.items():
        bt_id = bt_data.get("backtestId", "")
        print(f"  Recovering results for {label} (BT: {bt_id})...")
        full_bt = read_completed_backtest(bt_id)
        stats = full_bt.get("statistics", {})
        param_set = full_bt.get("parameterSet", {})
        
        metrics = extract_metrics_from_stats(stats)
        score = score_result(metrics)
        gates = passes_kill_gates(metrics)
        
        result_row = {
            "label": label,
            "bt_id": bt_id,
            "status": "OK",
            "profit_target_pct": param_set.get("profit_target_pct", "?"),
            "stop_loss_pct": param_set.get("stop_loss_pct", "?"),
            "risk_per_trade": param_set.get("risk_per_trade", "?"),
            **metrics,
            "score": score,
            "pass_gates": gates,
        }
        all_results.append(result_row)
        
        gate_str = "PASS" if gates else "FAIL"
        print(f"    Return: {metrics['net_profit_pct']:+.2f}% | Sharpe: {metrics['sharpe']:.3f} | Gates: {gate_str}")

    # Upload code once (same for all combos)
    print("\n[SETUP] Uploading v20b_param_loop.py...")
    if not upload_code():
        print("FATAL: Code upload failed")
        sys.exit(1)
    print("  Code uploaded OK")

    for i, combo in enumerate(PARAM_GRID):
        label = combo.pop("label")
        combo_display = {k: v for k, v in combo.items()}

        # RESUME: Skip already-completed combos
        if label in existing:
            print(f"\n[{i+1}/{len(PARAM_GRID)}] {label} - SKIPPED (already completed)")
            combo["label"] = label
            skipped += 1
            continue
        
        print(f"\n{'='*70}")
        print(f"[{i+1}/{len(PARAM_GRID)}] {label}")
        print(f"  Params: {combo_display}")
        print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")
        
        # Merge fixed + variable params
        all_params = {**FIXED_PARAMS, **combo}
        
        # Step 1: Set parameters
        print("  Setting parameters...")
        if not set_parameters(all_params):
            print("  ERROR: Failed to set parameters, skipping")
            combo["label"] = label
            continue
        
        # Step 2: Compile (code already uploaded)
        print("  Compiling...")
        ok, cid = compile_project()
        if not ok:
            print("  ERROR: Compile failed, skipping")
            combo["label"] = label
            continue
        print(f"  Compiled: {cid}")
        
        # Step 3: Launch backtest
        bt_name = f"V2.0b ParamLoop {label} PT={combo['profit_target_pct']} SL={combo['stop_loss_pct']} R={combo['risk_per_trade']}"
        print(f"  Launching: {bt_name}")
        ok, bt_id = launch_backtest(cid, bt_name)
        if not ok:
            print("  ERROR: Launch failed, skipping")
            combo["label"] = label
            continue
        print(f"  BT ID: {bt_id}")
        
        # Step 4: Poll until done
        print("  Waiting for completion...")
        bt_result = poll_backtest(bt_id, max_wait=600)
        
        status = bt_result.get("status", "Unknown")
        if "Error" in str(status):
            print(f"  FAILED: {status}")
            all_results.append({
                "label": label, "bt_id": bt_id, "status": "ERROR",
                **combo_display, **{k: 0 for k in ["net_profit_pct", "cagr_pct", "sharpe", "sortino", 
                                                      "max_dd_pct", "total_orders", "trade_count",
                                                      "win_rate_pct", "profit_factor", "final_equity", "score"]},
                "pass_gates": False,
            })
            combo["label"] = label
            continue
        
        # Step 5: Read logs
        print("  Reading logs...")
        logs = read_logs(bt_id)
        print(f"  Got {len(logs)} log entries")
        
        # Step 6: Extract metrics
        metrics = extract_metrics(bt_result, logs)
        score = score_result(metrics)
        gates = passes_kill_gates(metrics)
        
        result_row = {
            "label": label,
            "bt_id": bt_id,
            "status": "OK",
            **combo_display,
            **metrics,
            "score": score,
            "pass_gates": gates,
        }
        all_results.append(result_row)
        
        # Print summary
        gate_str = "PASS" if gates else "FAIL"
        print(f"  ----------------------------------")
        print(f"  Return: {metrics['net_profit_pct']:+.2f}% | CAGR: {metrics['cagr_pct']:.1f}%")
        print(f"  Sharpe: {metrics['sharpe']:.3f} | Sortino: {metrics['sortino']:.3f}")
        print(f"  Max DD: {metrics['max_dd_pct']:.1f}% | Trades: {metrics['trade_count']}")
        print(f"  WR: {metrics['win_rate_pct']:.1f}% | PF: {metrics['profit_factor']:.2f}")
        print(f"  Score: {score:.4f} | Gates: {gate_str}")
        print(f"  ----------------------------------")
        
        combo["label"] = label
        
        # Brief pause between backtests
        time.sleep(5)

    # ════════════════════════════════════════════════
    # SAVE RESULTS
    # ════════════════════════════════════════════════
    print(f"\n[SUMMARY] Skipped {skipped} already-completed backtests, ran {len(all_results) - len(existing)} new ones")
    print("\n" + "=" * 70)
    print("SAVING RESULTS")
    
    # Save JSON
    with open(RESULTS_JSON, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"  JSON: {RESULTS_JSON}")
    
    # Save CSV
    if all_results:
        fieldnames = list(all_results[0].keys())
        with open(RESULTS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"  CSV: {RESULTS_CSV}")

    # ════════════════════════════════════════════════
    # FINAL SUMMARY TABLE
    # ════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("PARAMETER STABILITY LOOP - FINAL RESULTS")
    print("=" * 70)
    
    # Sort by score descending
    sorted_results = sorted(all_results, key=lambda x: x.get("score", 0), reverse=True)
    
    print(f"\n{'Label':<12} {'PT':>5} {'SL':>6} {'Risk':>5} {'Return':>8} {'CAGR':>6} {'Sharpe':>7} {'DD':>6} {'Trades':>6} {'Score':>7} {'Gate':>5}")
    print("-" * 85)
    
    for r in sorted_results:
        gate_str = "PASS" if r.get("pass_gates") else "FAIL"
        if r.get("status") == "ERROR":
            gate_str = "ERR"
        print(f"{r['label']:<12} {r.get('profit_target_pct','?'):>5} {r.get('stop_loss_pct','?'):>6} "
              f"{r.get('risk_per_trade','?'):>5} {r.get('net_profit_pct',0):>+7.1f}% "
              f"{r.get('cagr_pct',0):>5.1f}% {r.get('sharpe',0):>7.3f} "
              f"{r.get('max_dd_pct',0):>5.1f}% {r.get('trade_count',0):>6} "
              f"{r.get('score',0):>7.4f} {gate_str:>5}")

    # Count passes
    passes = sum(1 for r in all_results if r.get("pass_gates"))
    print(f"\nTotal: {len(all_results)} combos | Passed gates: {passes}/{len(all_results)}")
    
    if passes > 0:
        print("\nPASSING COMBOS:")
        for r in sorted_results:
            if r.get("pass_gates"):
                print(f"  {r['label']}: PT={r['profit_target_pct']} SL={r['stop_loss_pct']} "
                      f"Risk={r['risk_per_trade']} → Sharpe={r['sharpe']:.3f} CAGR={r['cagr_pct']:.1f}% Score={r['score']:.4f}")
    
    # Stability assessment
    if passes >= 30:
        print("\n[*] HIGHLY STABLE - V2.0b passes gates across 67%+ of parameter space (30+/45)")
    elif passes >= 20:
        print("\n[+] MODERATELY STABLE - V2.0b passes gates in ~50% of variations (20+/45)")
    elif passes >= 10:
        print("\n[~] MARGINALLY STABLE - V2.0b only works in narrow parameter range (10+/45)")
    else:
        print("\n[X] UNSTABLE - V2.0b fails gates in most parameter variations (<10/45)")
    
    print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
