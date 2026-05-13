"""
Forensic analysis of V2.0b BASELINE and top combos.
Pull all trade logs, equity curve, and analyze:
1. Wick patterns (unrealized gains given back)
2. Decline periods (DD timing vs market conditions)
3. Trade-by-trade P&L distribution
4. Temporal patterns (when does the strategy lose?)
"""
import hashlib, time, requests, base64, json, re
from datetime import datetime

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"

def get_headers():
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{UID}:{hashed}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts}

def read_all_logs(bt_id, max_pages=10):
    all_logs = []
    for page in range(max_pages):
        start = page * 200
        try:
            r = requests.post(f"{BASE}/backtests/read/log", headers=get_headers(), json={
                "projectId": 29490680, "backtestId": bt_id,
                "start": start, "end": start + 200, "query": " "
            }, timeout=30)
            logs = r.json().get("logs", [])
        except:
            logs = []
        if not logs:
            break
        all_logs.extend(logs)
        if len(logs) < 200:
            break
        time.sleep(0.5)
    return all_logs

def read_bt_full(bt_id):
    r = requests.post(f"{BASE}/backtests/read", headers=get_headers(), json={
        "projectId": 29490680, "backtestId": bt_id
    }, timeout=30)
    return r.json().get("backtest", {})

# ========================================
# Pull data for BASELINE, G13, G22
# ========================================
targets = {
    "BASELINE": "4f50bd98dc373876d938e00c74105996",
    "G13": "6cf99e695f848eff4812b453de7da3ae",
    "G22": "62c5221529bacbd600b4c478fc641443",  # PT=0.40, SL=-0.20, R=0.04 -- wait, need to verify
}

all_data = {}
for label, bt_id in targets.items():
    print(f"\n=== Pulling {label} ({bt_id}) ===")
    
    # Full BT data (has charts with equity)
    bt = read_bt_full(bt_id)
    stats = bt.get("statistics", {})
    charts = bt.get("charts", {})
    
    # Logs
    logs = read_all_logs(bt_id)
    print(f"  Logs: {len(logs)} entries")
    
    # Parse trades from logs
    trades = []
    opens = []
    closes = []
    equity_points = []
    weekly_reports = []
    cooldowns = []
    
    for log in logs:
        msg = log if isinstance(log, str) else str(log)
        
        # OPEN trade
        if "OPEN" in msg and ("CALL" in msg or "BUY" in msg or "credit=" in msg):
            opens.append(msg)
        
        # CLOSE trade
        if "CLOSE" in msg or "EXPIRED" in msg or "SL HIT" in msg or "PT HIT" in msg:
            closes.append(msg)
        
        # Trade with P&L
        if "P&L:" in msg or "pnl=" in msg or "PnL:" in msg:
            trades.append(msg)
        
        # Equity snapshots
        if "Equity:" in msg:
            equity_points.append(msg)
        
        # Weekly reports
        if "WEEKLY" in msg or "Week " in msg:
            weekly_reports.append(msg)
        
        # Cooldowns
        if "cooldown" in msg.lower() or "BLOCKED" in msg:
            cooldowns.append(msg)
    
    print(f"  Opens: {len(opens)}, Closes: {len(closes)}, P&L entries: {len(trades)}")
    print(f"  Equity snapshots: {len(equity_points)}")
    print(f"  Weekly reports: {len(weekly_reports)}")
    print(f"  Cooldowns: {len(cooldowns)}")
    
    all_data[label] = {
        "stats": stats,
        "logs": logs,
        "opens": opens,
        "closes": closes,
        "trades": trades,
        "equity_points": equity_points,
        "weekly_reports": weekly_reports,
        "cooldowns": cooldowns,
        "charts": list(charts.keys()) if charts else [],
    }
    
    # Print first few opens and closes for pattern analysis
    print(f"\n  --- First 5 OPENS ---")
    for o in opens[:5]:
        print(f"    {o[:200]}")
    
    print(f"\n  --- First 5 CLOSES ---")
    for c in closes[:5]:
        print(f"    {c[:200]}")
    
    print(f"\n  --- First 10 P&L entries ---")
    for t in trades[:10]:
        print(f"    {t[:200]}")
    
    print(f"\n  --- Equity snapshots (first 5, last 5) ---")
    for e in equity_points[:5]:
        print(f"    {e[:200]}")
    print(f"    ...")
    for e in equity_points[-5:]:
        print(f"    {e[:200]}")
    
    print(f"\n  --- Charts available: {all_data[label]['charts']}")

# Save raw data for deeper analysis
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/forensic_raw.json", "w") as f:
    # Can't serialize everything, save logs
    save_data = {}
    for label, data in all_data.items():
        save_data[label] = {
            "opens": data["opens"],
            "closes": data["closes"],
            "trades": data["trades"],
            "equity_points": data["equity_points"],
            "weekly_reports": data["weekly_reports"],
            "cooldowns": data["cooldowns"],
            "charts": data["charts"],
        }
    json.dump(save_data, f, indent=2)

print("\n\nRaw data saved to forensic_raw.json")
print("=" * 70)
