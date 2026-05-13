"""Fetch ALL statistics for multiple backtests for full comparison table"""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"

BACKTESTS = {
    "V4-B FULL 2023-2026": "d2759c5a68a50569c2b20bfc285ed8de",
    "V5 ALL-FIXES": "f12e677ce3f29adfea593b48a2343b2b",
    "V5a FIX3-only": "c1a821cc9a6b06962bed23ea91a04b6a",
    "V5b FIX2-only": "c0fac48a599f1f0bdf3b798343e3c646",
}

def auth_headers():
    ts = str(int(time.time()))
    token_bytes = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{token_bytes}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts, "Content-Type": "application/json"}

all_stats = {}
for name, bt_id in BACKTESTS.items():
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/backtests/read", headers=auth_headers(),
                              json={"projectId": PROJECT_ID, "backtestId": bt_id}, timeout=30)
            data = r.json()
            bt = data.get("backtest", data)
            completed = bt.get("completed", False)
            stats = bt.get("statistics", {})
            all_stats[name] = {"completed": completed, "stats": stats, "bt_id": bt_id}
            print(f"[{name}] completed={completed}, stats_count={len(stats)}")
            break
        except Exception as e:
            print(f"[{name}] attempt {attempt+1} failed: {e}")
            time.sleep(3)

# Save for later use
with open("C:/AI_VAULT/tmp_agent/scripts/all_bt_stats.json", "w") as f:
    json.dump(all_stats, f, indent=2)

print("\nDone. Saved to all_bt_stats.json")
