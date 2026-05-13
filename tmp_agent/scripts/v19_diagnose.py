"""
V19 Diagnosis Script - Extract logs from QC backtests to understand:
1. What probabilities the model outputs (distribution)
2. Label distribution (class balance)
3. How many signals >= threshold
4. Trade quality breakdown (TP/SL/TIME/SIG exits)
5. What % of time model is trained vs not
"""
import hashlib, base64, time, json, requests, re, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

def auth_headers():
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api_get(endpoint, params=None, retries=5, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}/{endpoint}", headers=auth_headers(), params=params or {}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API GET {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                raise

def api_post(endpoint, payload, retries=5, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API POST {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                raise

# Backtest IDs
BT_IDS = {
    "IS":   "a3dce1dfd01e347698238ca6050b86be",
    "OOS":  "780e3090698afcb982981f93a3e13c59",
    "Full": "8bc94fc761b3321ed31697a2731073b1",
}

for label, bt_id in BT_IDS.items():
    print(f"\n{'='*70}")
    print(f"=== {label} Backtest: {bt_id} ===")
    print(f"{'='*70}")

    # 1. Read backtest details (includes orders)
    resp = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
    bt = resp.get("backtest", resp)

    # Extract logs
    logs = bt.get("logs", [])
    print(f"\nTotal log entries: {len(logs)}")

    # Parse TRAIN messages
    train_logs = []
    for log in logs:
        if isinstance(log, str) and "TRAIN:" in log:
            train_logs.append(log)
        elif isinstance(log, dict):
            msg = log.get("message", "") or log.get("Message", "")
            if "TRAIN:" in msg:
                train_logs.append(msg)

    print(f"\n--- TRAINING LOGS ({len(train_logs)}) ---")
    for tl in train_logs:
        print(f"  {tl}")

    # Parse PRELOAD messages
    preload_logs = []
    for log in logs:
        msg = log if isinstance(log, str) else (log.get("message", "") or log.get("Message", ""))
        if "PRELOAD" in msg:
            preload_logs.append(msg)
    print(f"\n--- PRELOAD LOGS ({len(preload_logs)}) ---")
    for pl in preload_logs:
        print(f"  {pl}")

    # Parse all debug messages
    all_debug = []
    for log in logs:
        if isinstance(log, str):
            all_debug.append(log)
        elif isinstance(log, dict):
            msg = log.get("message", "") or log.get("Message", "")
            if msg:
                all_debug.append(msg)

    print(f"\n--- ALL DEBUG MESSAGES ({len(all_debug)}) ---")
    for d in all_debug[:100]:  # First 100
        print(f"  {d}")
    if len(all_debug) > 100:
        print(f"  ... ({len(all_debug) - 100} more)")

    # Extract orders info
    orders = bt.get("orders", {})
    if orders:
        print(f"\n--- ORDERS ({len(orders)}) ---")
        entry_probs = []
        exit_reasons = {"TP": 0, "SL": 0, "TIME": 0, "SIG": 0, "OTHER": 0}

        for oid, order in orders.items():
            tag = order.get("tag", "") or order.get("Tag", "")
            symbol = order.get("symbol", {})
            sym = symbol.get("Value", "?") if isinstance(symbol, dict) else str(symbol)
            direction = order.get("direction", "?") or order.get("Direction", "?")
            qty = order.get("quantity", "?") or order.get("Quantity", "?")
            fill_px = order.get("price", "?") or order.get("Price", "?")
            status = order.get("status", "?") or order.get("Status", "?")
            dt = order.get("time", "?") or order.get("Time", "?")

            print(f"  [{dt}] {sym} dir={direction} qty={qty} tag={tag}")

            # Parse entry probability
            m = re.search(r"LONG\s+p=(\d+\.\d+)", str(tag))
            if m:
                entry_probs.append(float(m.group(1)))

            # Parse exit reason
            m2 = re.search(r"EXIT-(\w+)", str(tag))
            if m2:
                reason = m2.group(1)
                if reason in exit_reasons:
                    exit_reasons[reason] += 1
                else:
                    exit_reasons["OTHER"] += 1

        print(f"\n--- ENTRY PROBABILITIES ({len(entry_probs)}) ---")
        if entry_probs:
            import numpy as np
            probs = np.array(entry_probs)
            print(f"  Min:    {probs.min():.4f}")
            print(f"  Max:    {probs.max():.4f}")
            print(f"  Mean:   {probs.mean():.4f}")
            print(f"  Median: {np.median(probs):.4f}")
            print(f"  Std:    {probs.std():.4f}")
            # Distribution bins
            bins = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.01]
            for i in range(len(bins)-1):
                cnt = int(((probs >= bins[i]) & (probs < bins[i+1])).sum())
                print(f"  [{bins[i]:.2f}-{bins[i+1]:.2f}): {cnt}")

        print(f"\n--- EXIT REASONS ---")
        for reason, cnt in exit_reasons.items():
            print(f"  {reason}: {cnt}")
    else:
        print("\nNo orders found in response")

    # Parse TRAIN logs for signal density
    for tl in train_logs:
        m = re.search(r"signals>=[\d.]+:\s*(\d+)\s*\((\d+)%\)", tl)
        if m:
            sig_count = int(m.group(1))
            sig_pct = int(m.group(2))
            m2 = re.search(r"(\d+)\s*samp", tl)
            total_samp = int(m2.group(1)) if m2 else 0
            m3 = re.search(r"pos=([\d.]+)", tl)
            pos_rate = float(m3.group(1)) if m3 else 0
            print(f"\n  TRAIN BREAKDOWN: {total_samp} samples, pos_rate={pos_rate:.3f}, signals={sig_count} ({sig_pct}%)")

    # Also check the raw results file for more info
    print(f"\n--- STATISTICS ---")
    stats = bt.get("statistics", {})
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    # Check for runtime errors
    error = bt.get("error", "")
    if error:
        print(f"\n  RUNTIME ERROR: {error}")
    stacktrace = bt.get("stacktrace", "")
    if stacktrace:
        print(f"  STACKTRACE: {stacktrace[:500]}")

    print("")

# Also try the logs endpoint specifically
print("\n\n" + "="*70)
print("=== Trying /backtests/read/log endpoint for Full backtest ===")
print("="*70)
try:
    resp = api_post("backtests/read", {
        "projectId": PROJECT_ID,
        "backtestId": BT_IDS["Full"]
    })
    bt = resp.get("backtest", resp)

    # Check all top-level keys
    print(f"\nTop-level keys in response: {list(resp.keys())}")
    print(f"Top-level keys in backtest: {list(bt.keys())}")

    # Check for log-related keys
    for k in bt.keys():
        v = bt[k]
        if isinstance(v, (list, str)) and "log" in k.lower():
            if isinstance(v, list):
                print(f"\n  {k} (list, {len(v)} items):")
                for item in v[:20]:
                    print(f"    {item}")
            else:
                print(f"\n  {k}: {v[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n\nDONE.")
