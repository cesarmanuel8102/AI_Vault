"""
Extract ALL trade logs from G15 IS and OOS backtests for forensic analysis.
Paginate through all logs, extract OPEN/CLOSE/SCAN lines.
"""
import hashlib, base64, time, json, requests, os

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies/yoel_options"

def auth_headers():
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

def api(endpoint, payload, retries=5, timeout=45):
    for attempt in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=auth_headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
            else:
                raise

def get_all_logs(bt_id, label):
    """Pull ALL log lines from a backtest, paginated."""
    all_lines = []
    start = 0
    page_size = 200
    while True:
        print(f"  [{label}] Fetching logs {start}-{start+page_size}...")
        try:
            resp = api("backtests/read/log", {
                "projectId": PROJECT_ID,
                "backtestId": bt_id,
                "query": "",
                "start": start,
                "end": start + page_size
            })
        except Exception as e:
            print(f"  Log fetch error at {start}: {e}")
            break
        
        logs = resp.get("BacktestLogs", resp.get("backtestLogs", []))
        if not logs:
            break
        all_lines.extend(logs)
        print(f"    Got {len(logs)} lines (total: {len(all_lines)})")
        if len(logs) < page_size:
            break
        start += page_size
        time.sleep(1)
    
    return all_lines

BACKTESTS = [
    {"id": "53be8c0a98d224efcb23117b8ff8a703", "label": "G15_OOS"},
    {"id": "a293813fc69d64e453846dff2ba3a3b1", "label": "G15_IS"},
]

for bt in BACKTESTS:
    bt_id = bt["id"]
    label = bt["label"]
    print(f"\n{'='*70}")
    print(f"=== Extracting logs: {label} (BT: {bt_id}) ===")
    print(f"{'='*70}")
    
    all_lines = get_all_logs(bt_id, label)
    print(f"\n  Total lines: {len(all_lines)}")
    
    # Filter relevant lines
    opens = []
    closes = []
    scans = []
    final_report = []
    eod_lines = []
    in_report = False
    
    for line in all_lines:
        if isinstance(line, dict):
            msg = line.get("Message", line.get("message", str(line)))
            ts = line.get("Time", line.get("time", ""))
        else:
            msg = str(line)
            ts = ""
        
        if "OPEN " in msg and "YOEL_CALL" in msg:
            opens.append({"time": ts, "msg": msg})
        elif "CLOSE " in msg and "YOEL_CALL" in msg:
            closes.append({"time": ts, "msg": msg})
        elif "SCAN:" in msg:
            scans.append({"time": ts, "msg": msg})
        elif "FINAL REPORT" in msg or in_report:
            in_report = True
            final_report.append({"time": ts, "msg": msg})
        elif "EOD" in msg:
            eod_lines.append({"time": ts, "msg": msg})
    
    print(f"  Opens: {len(opens)}")
    print(f"  Closes: {len(closes)}")
    print(f"  Scans: {len(scans)}")
    print(f"  Final report lines: {len(final_report)}")
    
    # Save all data
    result = {
        "bt_id": bt_id,
        "label": label,
        "total_lines": len(all_lines),
        "opens": opens,
        "closes": closes,
        "scans": scans,
        "final_report": final_report,
        "eod_lines": eod_lines,
    }
    
    outfile = f"{OUTPUT_DIR}/g15_{label.lower()}_forensic_logs.json"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=True)
    print(f"  Saved: {outfile}")
    
    # Print all trades for quick view
    print(f"\n  --- ALL TRADES ({label}) ---")
    for o in opens:
        # Clean for ASCII
        msg = o["msg"].encode("ascii", errors="replace").decode()
        print(f"  {o['time'][:19]} | {msg}")
    print(f"  ---")
    for c in closes:
        msg = c["msg"].encode("ascii", errors="replace").decode()
        print(f"  {c['time'][:19]} | {msg}")
    
    # Print final report
    if final_report:
        print(f"\n  --- FINAL REPORT ({label}) ---")
        for r in final_report:
            msg = r["msg"].encode("ascii", errors="replace").decode()
            print(f"  {msg}")

# Also extract the closedTrades from the backtest result JSON for richer data
print(f"\n{'='*70}")
print("=== Extracting closedTrades from backtest results ===")
print(f"{'='*70}")

for bt in BACKTESTS:
    bt_id = bt["id"]
    label = bt["label"]
    print(f"\n  [{label}] Reading backtest result...")
    try:
        resp = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        bt_data = resp.get("backtest", resp)
        
        # Get profit-loss data and orders
        total_orders = bt_data.get("statistics", {}).get("Total Orders", "?")
        print(f"  Total Orders: {total_orders}")
        
        # Save full backtest data for analysis
        outfile = f"{OUTPUT_DIR}/g15_{label.lower()}_full_bt_data.json"
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(bt_data, f, indent=2, ensure_ascii=True, default=str)
        print(f"  Saved full BT data: {outfile}")
        
        # Check for profitLoss, rollingWindow, etc
        pnl = bt_data.get("profitLoss", {})
        print(f"  ProfitLoss entries: {len(pnl) if isinstance(pnl, dict) else 'N/A'}")
        
    except Exception as e:
        print(f"  Error: {e}")

print("\nDONE.")
