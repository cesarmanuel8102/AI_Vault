"""Find Calm Red Orange Kangaroo backtest + pull results + read current source."""
import hashlib, time, base64, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

def auth():
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    cred = base64.b64encode(f"{USER_ID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {cred}", "Timestamp": ts}

def api(endpoint, payload=None):
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/{endpoint}", json=payload or {}, headers=auth(), timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return None

# 1. List all backtests to find CROK
print("=" * 60)
print("LISTING ALL BACKTESTS")
print("=" * 60)
bt_list = api("backtests/list", {"projectId": PROJECT_ID})
if bt_list and bt_list.get("success"):
    backtests = bt_list.get("backtests", [])
    print(f"Found {len(backtests)} backtests:")
    crok_id = None
    for bt in backtests:
        name = bt.get("name", "?")
        btid = bt.get("backtestId", "?")
        created = bt.get("created", "?")
        progress = bt.get("progress", "?")
        print(f"  {name} | ID: {btid} | Created: {created} | Progress: {progress}")
        if "Calm Red Orange" in name or "Kangaroo" in name:
            crok_id = btid
            print(f"  >>> FOUND TARGET: {name}")
    
    if not crok_id:
        print("\nWARNING: Could not find 'Calm Red Orange Kangaroo' by name.")
        print("Looking for most recent backtest...")
        if backtests:
            latest = sorted(backtests, key=lambda x: x.get("created", ""), reverse=True)[0]
            crok_id = latest.get("backtestId")
            print(f"Most recent: {latest.get('name')} | ID: {crok_id}")
else:
    print(f"ERROR listing backtests: {bt_list}")
    sys.exit(1)

if not crok_id:
    print("No backtest found. Exiting.")
    sys.exit(1)

# 2. Pull full backtest results
print(f"\n{'=' * 60}")
print(f"PULLING BACKTEST: {crok_id}")
print("=" * 60)
bt = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": crok_id})
if not bt or not bt.get("success"):
    print(f"ERROR reading backtest: {bt}")
    sys.exit(1)

with open("C:/AI_VAULT/tmp_agent/strategies/brain_v10/crok_raw.json", "w") as f:
    json.dump(bt, f, indent=2, default=str)
print("Raw JSON saved to crok_raw.json")

b = bt.get("backtest", bt)
print(f"\nName: {b.get('name', 'N/A')}")
print(f"Created: {b.get('created', 'N/A')}")
print(f"Progress: {b.get('progress', 'N/A')}")
print(f"Note: {b.get('note', 'N/A')}")
print(f"Backtest ID: {crok_id}")

stats = b.get("statistics", {})
runtime = b.get("runtimeStatistics", {})

print("\n--- ALL STATISTICS ---")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")

print("\n--- RUNTIME STATISTICS ---")
for k, v in sorted(runtime.items()):
    print(f"  {k}: {v}")

# 3. Read current main.py from project
print(f"\n{'=' * 60}")
print("READING CURRENT main.py FROM PROJECT")
print("=" * 60)
main_file = api("files/read", {"projectId": PROJECT_ID, "name": "main.py"})
if main_file and main_file.get("success"):
    file_list = main_file.get("files", [])
    if file_list:
        content = file_list[0].get("content", "")
        with open("C:/AI_VAULT/tmp_agent/state/qc_backups/crok_main.py", "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Source saved ({len(content)} chars, {len(content.splitlines())} lines)")
    else:
        print("No files returned")
else:
    print(f"Read result: {main_file}")

# 4. Pull logs (first 500 lines)
print(f"\n{'=' * 60}")
print("PULLING BACKTEST LOGS (first 200)")
print("=" * 60)
logs = api("backtests/read/log", {"projectId": PROJECT_ID, "backtestId": crok_id, "start": 0, "end": 200})
if logs and logs.get("success"):
    log_lines = logs.get("BacktestLogs", logs.get("logs", []))
    if log_lines:
        print(f"Got {len(log_lines)} log lines:")
        for line in log_lines:
            if isinstance(line, dict):
                msg = line.get("Message", str(line))
            else:
                msg = str(line)
            try:
                print(f"  {msg[:200]}")
            except:
                print("  [unicode line]")
    else:
        print("No log lines returned")
else:
    print(f"Log result: {logs}")

print("\nDONE.")
