"""
Fetch V5 backtest logs with pagination (max 200 lines per page).
"""
import hashlib, base64, time, json, requests, datetime

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BT_ID = "f12e677ce3f29adfea593b48a2343b2b"
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
            if attempt < 2:
                time.sleep(3)
            else:
                raise

all_logs = []
start_ts = int(datetime.datetime(2023, 1, 1).timestamp())
end_ts = int(datetime.datetime(2026, 4, 28).timestamp())

# Paginate: QC seems to want start/end as page boundaries
# Try with length parameter
for page in range(50):  # max 50 pages = 10000 log lines
    offset = page * 200
    resp = api("backtests/read/log", {
        "projectId": PROJECT_ID,
        "backtestId": BT_ID,
        "query": "",
        "start": offset,
        "end": offset + 200,
    })

    if not resp.get("success", False):
        if page == 0:
            print(f"Page 0 failed: {resp.get('errors', [])}")
            # Try different format
            resp = api("backtests/read/log", {
                "projectId": PROJECT_ID,
                "backtestId": BT_ID,
                "query": "",
                "start": 0,
                "end": 200,
            })
            if resp.get("success"):
                logs = resp.get("logs", [])
                all_logs.extend(logs)
                print(f"  Page 0: {len(logs)} lines (alt format)")
                if len(logs) < 200:
                    break
                continue
            else:
                print(f"Alt format also failed: {resp}")
                break
        break

    logs = resp.get("logs", [])
    all_logs.extend(logs)
    print(f"  Page {page}: {len(logs)} lines (total: {len(all_logs)})")

    if len(logs) < 200:
        break

    time.sleep(0.5)

print(f"\nTotal log lines: {len(all_logs)}")

if all_logs:
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_logs.txt", "w", encoding="ascii", errors="replace") as f:
        for line in all_logs:
            f.write(str(line).encode("ascii", errors="replace").decode() + "\n")

    print("\n=== KEY DIAGNOSTICS ===")
    for line in all_logs:
        s = str(line)
        if any(kw in s for kw in ["V2.0b-v5 INIT", "FIX1", "FIX2", "FIX3", "FIX4",
                                   "TRAIL_ON", "TRAIL=", "cutoff_blocks", "regime_blocks",
                                   "mfe_scale", "capture", "CONF_DIST", "BY TICKER",
                                   "BY EXIT", "Trades:", "PnL:", "Equity:", "Return:",
                                   "FINAL REPORT", "====", "trailing_exits",
                                   "qqq_regime", "mfe_mult", "MFE_CAPTURE", "signals="]):
            print(f"  {s[:280]}")

print("\nDONE")
