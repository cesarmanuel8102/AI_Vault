"""Download all closed trades (orders) from a QC backtest.
Usage: python download_trades.py <backtest_id> <output_file>
"""
import sys, time, json, requests
from hashlib import sha256

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29721803

def auth_headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    return {
        "Timestamp": ts,
        "Authorization": f"Basic {__import__('base64').b64encode(f'{UID}:{h}'.encode()).decode()}"
    }

def main():
    bt_id = sys.argv[1] if len(sys.argv) > 1 else "7d6fc2e5ca3bbf86db6adf100a1c98b6"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "C:/AI_VAULT/tmp_agent/strategies/mtf_trend/bt_v34_trades.json"

    # Get orders
    url = f"{BASE}/backtests/orders?projectId={PROJECT_ID}&backtestId={bt_id}&start=0&end=5000"
    r = requests.get(url, headers=auth_headers())
    data = r.json()

    if not data.get("success"):
        print(f"ERROR: {data}")
        return

    orders = data.get("orders", [])
    print(f"Downloaded {len(orders)} orders")

    with open(out_file, "w") as f:
        json.dump(orders, f, indent=2)
    print(f"Saved to {out_file}")

if __name__ == "__main__":
    main()
