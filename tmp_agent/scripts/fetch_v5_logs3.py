"""
Fetch V5 backtest logs with correct params.
"""
import hashlib, base64, time, json, requests

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
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise

# Fetch logs with start/end timestamps
# Backtest period: 2023-01-01 to 2026-04-28
import datetime
start_ts = int(datetime.datetime(2023, 1, 1).timestamp())
end_ts = int(datetime.datetime(2026, 4, 28).timestamp())

print(f"Fetching logs: start={start_ts} end={end_ts}")
resp = api("backtests/read/log", {
    "projectId": PROJECT_ID,
    "backtestId": BT_ID,
    "query": "",
    "start": start_ts,
    "end": end_ts,
})
print(f"Success: {resp.get('success')}")
logs = resp.get("logs", resp.get("Logs", []))
print(f"Log count: {len(logs)}")

if logs:
    with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v5_logs.txt", "w", encoding="ascii", errors="replace") as f:
        for line in logs:
            f.write(str(line).encode("ascii", errors="replace").decode() + "\n")
    print(f"Saved {len(logs)} lines")

    # Print key diagnostic lines
    print("\n=== KEY DIAGNOSTICS ===")
    for line in logs:
        s = str(line)
        if any(kw in s for kw in ["V2.0b-v5 INIT", "FIX1", "FIX2", "FIX3", "FIX4",
                                   "TRAIL_ON", "TRAIL=", "cutoff_blocks", "regime_blocks",
                                   "mfe_scale", "capture", "CONF_DIST", "BY TICKER",
                                   "BY EXIT", "Trades:", "PnL:", "Return:", "Equity:",
                                   "FINAL REPORT", "====", "trailing_exits",
                                   "qqq_regime", "mfe_mult"]):
            print(f"  {s[:250]}")
else:
    print(f"Response: {json.dumps(resp, indent=2, default=str)[:1000]}")

print("\nDONE")
