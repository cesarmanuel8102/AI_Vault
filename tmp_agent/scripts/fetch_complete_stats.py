"""Fetch ALL period stats for complete degradation analysis table.
Need: V4-B IS, V5a IS, plus what we already have for OOS and Full."""
import hashlib, base64, time, json, requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
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
                time.sleep(5)
            else:
                raise

# We need V5a IS (2023-2024) - doesn't exist yet, need to run it
# V4-B IS already exists: 416cd719abdab6b75c14620da28ff93e
# Let's fetch V4-B IS first

ALL_BTS = {
    "V4-B IS 2023-2024": "416cd719abdab6b75c14620da28ff93e",
    "V4-B Full 2023-2026": "d2759c5a68a50569c2b20bfc285ed8de",
    "V4-B OOS 2025-2026": "b2c767ac725c6b148bd45743bbf0649f",
    "V5a Full 2023-2026": "c1a821cc9a6b06962bed23ea91a04b6a",
    "V5a OOS 2025-2026": "cad6ffbf6a0720036d952a7b5af1dd5b",
}

all_data = {}
for name, bt_id in ALL_BTS.items():
    data = api("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
    bt = data.get("backtest", data)
    stats = bt.get("statistics", {})
    all_data[name] = stats
    print(f"[{name}] {len(stats)} metrics, completed={bt.get('completed')}")

# Save everything
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/complete_comparison_data.json", "w") as f:
    json.dump(all_data, f, indent=2)

print("\nSaved. Now need to run V5a IS 2023-2024...")
