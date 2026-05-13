"""Pull Fat Violet Panda backtest + project source code from QC API."""
import hashlib, time, base64, json, requests, sys

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BT_ID = "c257a9b1067b18d391636749f3c05e02"
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

# 1. Pull backtest results
print("=" * 60)
print("PULLING FAT VIOLET PANDA BACKTEST")
print("=" * 60)
bt = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": BT_ID})
if not bt or not bt.get("success"):
    print(f"ERROR reading backtest: {bt}")
    sys.exit(1)

# Save raw JSON
with open("C:/AI_VAULT/tmp_agent/strategies/brain_v10/fat_violet_panda_raw.json", "w") as f:
    json.dump(bt, f, indent=2, default=str)
print("Raw JSON saved.")

b = bt.get("backtest", bt)
print(f"\nName: {b.get('name', 'N/A')}")
print(f"Created: {b.get('created', 'N/A')}")
print(f"Progress: {b.get('progress', 'N/A')}")
print(f"Note: {b.get('note', 'N/A')}")

# Extract statistics
stats = b.get("statistics", {})
runtime = b.get("runtimeStatistics", {})

print("\n--- STATISTICS ---")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")

print("\n--- RUNTIME STATISTICS ---")
for k, v in sorted(runtime.items()):
    print(f"  {k}: {v}")

# Rolling windows if available
rolling = b.get("rollingWindow", {})
if rolling:
    print("\n--- ROLLING WINDOWS ---")
    for period, data in sorted(rolling.items()):
        if isinstance(data, dict):
            print(f"\n  [{period}]")
            for k2, v2 in sorted(data.items()):
                print(f"    {k2}: {v2}")

# Alpha streams
alpha = b.get("alphaRuntimeStatistics", {})
if alpha:
    print("\n--- ALPHA RUNTIME ---")
    for k, v in sorted(alpha.items()):
        print(f"  {k}: {v}")

# Chart equity data - get final value
charts = b.get("charts", {})
if "Strategy Equity" in charts:
    eq = charts["Strategy Equity"]
    series = eq.get("Series", {})
    if "Equity" in series:
        vals = series["Equity"].get("Values", [])
        if vals:
            last = vals[-1] if isinstance(vals, list) else None
            if last:
                print(f"\nFinal equity data point: {last}")
            print(f"Total equity data points: {len(vals)}")

# 2. Pull backtest logs (first 500 lines)
print("\n" + "=" * 60)
print("PULLING BACKTEST LOGS")
print("=" * 60)
logs = api("backtests/read/log", {"projectId": PROJECT_ID, "backtestId": BT_ID, "start": 0, "end": 500})
if logs and logs.get("success"):
    log_lines = logs.get("BacktestLogs", logs.get("logs", []))
    if log_lines:
        print(f"Got {len(log_lines)} log lines. First 50:")
        for i, line in enumerate(log_lines[:50]):
            if isinstance(line, dict):
                print(f"  {line.get('Message', line)}")
            else:
                print(f"  {line}")
    else:
        print("No log lines returned")
else:
    print(f"Log pull result: {logs}")

# 3. List project files to see what source code exists
print("\n" + "=" * 60)
print("LISTING PROJECT FILES")
print("=" * 60)
files = api("files/read", {"projectId": PROJECT_ID})
if files and files.get("success"):
    file_list = files.get("files", [])
    print(f"Found {len(file_list)} files:")
    for f_info in file_list:
        name = f_info.get("name", "?")
        modified = f_info.get("modified", "?")
        size = f_info.get("content", "")
        print(f"  {name}  (modified: {modified}, size: {len(size)} chars)")
else:
    print(f"Files list result: {files}")

# 4. Read main.py source code
print("\n" + "=" * 60)
print("READING main.py SOURCE CODE")
print("=" * 60)
main_file = api("files/read", {"projectId": PROJECT_ID, "name": "main.py"})
if main_file and main_file.get("success"):
    file_list = main_file.get("files", [])
    if file_list:
        content = file_list[0].get("content", "")
        # Save to disk
        with open("C:/AI_VAULT/tmp_agent/state/qc_backups/fat_violet_panda_main.py", "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Source saved ({len(content)} chars)")
        # Print first 100 lines
        lines = content.split("\n")
        print(f"Total lines: {len(lines)}")
        print("\n--- FIRST 80 LINES ---")
        for i, line in enumerate(lines[:80]):
            try:
                print(f"  {i+1}: {line}")
            except UnicodeEncodeError:
                print(f"  {i+1}: [unicode line]")
        print("\n--- LAST 30 LINES ---")
        for i, line in enumerate(lines[-30:]):
            try:
                print(f"  {len(lines)-30+i+1}: {line}")
            except UnicodeEncodeError:
                print(f"  {len(lines)-30+i+1}: [unicode line]")
    else:
        print("No files returned for main.py")
else:
    print(f"main.py read result: {main_file}")

print("\n\nDONE.")
