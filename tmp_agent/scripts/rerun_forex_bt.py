"""Re-upload fixed main.py, compile, launch backtest.
Usage: python rerun_forex_bt.py [backtest_name] [param:value ...] [--file path/to/main.py]
  e.g. python rerun_forex_bt.py "Forex V2.0a MOD-A Only" module_mode:A_ONLY
  e.g. python rerun_forex_bt.py "MC V1.0" --file C:/AI_VAULT/tmp_agent/strategies/momentum_carry/main.py
"""
import sys, time, json, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652

# Parse args
bt_name = "Forex V2.0 BugFixes"
params = {}
source_file = "C:/AI_VAULT/tmp_agent/strategies/forex_v1/main.py"
args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--file" and i + 1 < len(args):
        source_file = args[i + 1]
        i += 2
    elif ":" in args[i]:
        k, v = args[i].split(":", 1)
        params[k] = v
        i += 1
    else:
        bt_name = args[i]
        i += 1

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# Set parameters on project if any
if params:
    print(f"Setting parameters: {params}")
    param_list = [{"key": k, "value": v} for k, v in params.items()]
    r = requests.post(f"{BASE}/projects/update", headers=headers(), json={
        "projectId": PROJECT_ID, "parameters": param_list
    })
    print(f"Params set: {r.json().get('success')}")

# Upload
print(f"Source: {source_file}")
with open(source_file, "r", encoding="utf-8") as f:
    code = f.read()
r = requests.post(f"{BASE}/files/update", headers=headers(), json={"projectId": PROJECT_ID, "name": "main.py", "content": code})
print(f"Upload: {r.json().get('success')}")

# Compile
r = requests.post(f"{BASE}/compile/create", headers=headers(), json={"projectId": PROJECT_ID})
data = r.json()
cid = data.get("compileId", "")
state = data.get("state", "")
waited = 0
while state not in ["BuildSuccess", "BuildError"] and waited < 60:
    time.sleep(3); waited += 3
    r = requests.post(f"{BASE}/compile/read", headers=headers(), json={"projectId": PROJECT_ID, "compileId": cid})
    data = r.json(); state = data.get("state", "")
print(f"Compile: {state}")
if state != "BuildSuccess":
    print(f"ERRORS: {json.dumps(data, indent=2)}"); exit(1)

# Backtest
r = requests.post(f"{BASE}/backtests/create", headers=headers(), json={
    "projectId": PROJECT_ID, "compileId": cid, "backtestName": bt_name
})
data = r.json()
bt = data.get("backtest", {})
bt_id = bt.get("backtestId", "")
print(f"Backtest '{bt_name}' launched: {bt_id}")

# Poll
waited = 0
while waited < 600:
    r = requests.post(f"{BASE}/backtests/read", headers=headers(), json={"projectId": PROJECT_ID, "backtestId": bt_id})
    data = r.json(); bt = data.get("backtest", {})
    progress = bt.get("progress", 0); error = bt.get("error", "")
    print(f"[{waited:>3}s] {progress*100:.1f}%", end="")
    if error:
        print(f"\nERROR: {error}")
        if bt.get("stacktrace"):
            print(f"STACK: {bt['stacktrace']}")
        break
    if progress >= 1.0:
        print(" COMPLETE!")
        stats = bt.get("runtimeStatistics", {})
        print(f"\n{'='*60}")
        for k, v in stats.items():
            print(f"  {k:.<30} {v}")
        statistics = bt.get("statistics", {})
        if statistics:
            print(f"\n--- Detailed ---")
            for k, v in statistics.items():
                print(f"  {k:.<40} {v}")
        import os
        results_dir = os.path.dirname(source_file)
        with open(os.path.join(results_dir, "backtest_results.json"), "w") as f:
            json.dump(bt, f, indent=2, default=str)
        print(f"\n[SAVED] backtest_results.json -> {results_dir}")

        # Update info
        info = {"project_id": PROJECT_ID, "compile_id": cid, "backtest_id": bt_id,
                "backtest_name": bt_name, "launched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "parameters": params, "source_file": source_file}
        with open(os.path.join(results_dir, "backtest_info.json"), "w") as f:
            json.dump(info, f, indent=2)
        break
    print("")
    time.sleep(10); waited += 10

if waited >= 600:
    print("[TIMEOUT]")
