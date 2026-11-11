"""Fetch a completed QuantConnect backtest using local LEAN credentials."""

from base64 import b64encode
from hashlib import sha256
from pathlib import Path
import argparse
import json
import time

import requests


ROOT = Path(__file__).resolve().parent
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id", type=int)
    parser.add_argument("backtest_id")
    parser.add_argument("output")
    args = parser.parse_args()
    credentials = json.loads((Path.home() / ".lean" / "credentials").read_text())
    timestamp = str(int(time.time()))
    signature = sha256(
        f"{credentials['api-token']}:{timestamp}".encode()
    ).hexdigest()
    authentication = b64encode(
        f"{credentials['user-id']}:{signature}".encode()
    ).decode()
    response = requests.post(
        "https://www.quantconnect.com/api/v2/backtests/read",
        headers={
            "Authorization": f"Basic {authentication}",
            "Timestamp": timestamp,
            "Content-Type": "application/json",
        },
        json={"projectId": args.project_id, "backtestId": args.backtest_id},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    (ROOT / args.output).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    backtest = payload.get("backtest", {})
    print(json.dumps({
        "success": payload.get("success"),
        "completed": backtest.get("completed"),
        "error": backtest.get("error"),
        "statistics": backtest.get("statistics"),
        "runtimeStatistics": backtest.get("runtimeStatistics"),
        "closedTrades": len((backtest.get("totalPerformance") or {}).get("closedTrades") or []),
        "orders": len(backtest.get("orders") or {}),
    }, indent=2))


if __name__ == "__main__":
    main()
