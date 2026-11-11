"""Fetch structured TRACE records from a QuantConnect cloud backtest."""

from base64 import b64encode
from hashlib import sha256
from pathlib import Path
import argparse
import json
import time

import requests


ROOT = Path(__file__).resolve().parent
API_URL = "https://www.quantconnect.com/api/v2/backtests/read/log"


def parse_trace_lines(lines):
    """Return valid JSON payloads embedded after the TRACE marker."""
    records = []
    for line in lines:
        marker = line.find("TRACE|")
        if marker < 0:
            continue
        try:
            payload = json.loads(line[marker + len("TRACE|") :])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _headers(credentials):
    timestamp = str(int(time.time()))
    signature = sha256(
        f"{credentials['api-token']}:{timestamp}".encode()
    ).hexdigest()
    authentication = b64encode(
        f"{credentials['user-id']}:{signature}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {authentication}",
        "Timestamp": timestamp,
        "Content-Type": "application/json",
    }


def fetch_trace_lines(project_id, backtest_id, credentials):
    """Fetch all TRACE log lines in API-sized pages."""
    lines = []
    start = 0
    while True:
        response = requests.post(
            API_URL,
            headers=_headers(credentials),
            json={
                "projectId": project_id,
                "backtestId": backtest_id,
                "start": start,
                "end": start + 200,
                "query": "TRACE|",
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(payload.get("errors") or "QuantConnect log request failed")
        page = payload.get("logs") or []
        lines.extend(page)
        total = int(payload.get("length") or len(lines))
        start += len(page)
        if not page or start >= total:
            return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id", type=int)
    parser.add_argument("backtest_id")
    parser.add_argument("output")
    args = parser.parse_args()

    credentials = json.loads((Path.home() / ".lean" / "credentials").read_text())
    records = parse_trace_lines(
        fetch_trace_lines(args.project_id, args.backtest_id, credentials)
    )
    (ROOT / args.output).write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    print(json.dumps({"records": len(records)}, indent=2))


if __name__ == "__main__":
    main()
