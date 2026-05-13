"""Poll a running QC backtest until completion and save results."""
import requests, time, json, os
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29721803
BT_ID = "b0564d9f27b245921e2f1067b70fe11d"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

waited = 0
while waited < 600:
    try:
        r = requests.post(f"{BASE}/backtests/read", headers=headers(),
                          json={"projectId": PROJECT_ID, "backtestId": BT_ID}, timeout=15)
        data = r.json()
        bt = data.get("backtest", {})
        progress = bt.get("progress", 0)
        error = bt.get("error", "")
        stats = bt.get("runtimeStatistics", {})
        equity = stats.get("Equity", "?")
        ret = stats.get("Return", "?")
        print(f"[{waited:>3}s] {progress*100:.1f}% | Equity: {equity} | Return: {ret}")

        if error and error != "None":
            print(f"ERROR: {error}")
            if bt.get("stacktrace"):
                print(f"STACK: {bt['stacktrace']}")
            break

        if progress >= 1.0:
            print("COMPLETE!")
            print(f"\n{'='*60}")
            for k, v in stats.items():
                print(f"  {k:.<30} {v}")
            statistics = bt.get("statistics", {})
            if statistics:
                print(f"\n--- Detailed ---")
                for k, v in statistics.items():
                    print(f"  {k:.<40} {v}")

            results_dir = "C:/AI_VAULT/tmp_agent/strategies/mtf_trend"
            with open(os.path.join(results_dir, "backtest_results.json"), "w") as f:
                json.dump(bt, f, indent=2, default=str)
            with open(os.path.join(results_dir, "backtest_results_v32.json"), "w") as f:
                json.dump(bt, f, indent=2, default=str)
            print(f"\n[SAVED] backtest_results.json + backtest_results_v32.json")
            break
    except Exception as e:
        print(f"[{waited:>3}s] Connection error: {e}")

    time.sleep(15)
    waited += 15

if waited >= 600:
    print("[TIMEOUT after 10 min]")
