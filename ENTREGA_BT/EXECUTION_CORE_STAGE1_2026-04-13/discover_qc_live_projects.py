import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests


BASE_URL = "https://www.quantconnect.com/api/v2"


def load_creds(path: str) -> Dict[str, str]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "user_id": str(data.get("user_id") or data.get("userId") or "").strip(),
        "token": str(data.get("api_token") or data.get("apiToken") or data.get("token") or "").strip(),
    }


def headers(creds: Dict[str, str], ts: int) -> Dict[str, str]:
    h = hashlib.sha256(f"{creds['token']}:{ts}".encode("utf-8")).hexdigest()
    b = base64.b64encode(f"{creds['user_id']}:{h}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {b}", "Timestamp": str(ts), "Content-Type": "application/json"}


def post(endpoint: str, payload: Dict[str, Any], creds: Dict[str, str]) -> Dict[str, Any]:
    ts = int(datetime.utcnow().timestamp())
    r = requests.post(f"{BASE_URL}/{endpoint}", headers=headers(creds, ts), json=payload, timeout=45)
    r.raise_for_status()
    data = r.json()
    if data.get("success", False):
        return data

    errs = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE_URL}/{endpoint}", headers=headers(creds, ts2), json=payload, timeout=45)
        r2.raise_for_status()
        return r2.json()
    return data


def main() -> None:
    p = argparse.ArgumentParser(description="List recent QuantConnect live deployments")
    p.add_argument("--qc-secrets", default=r"C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json")
    p.add_argument("--days", type=int, default=45)
    args = p.parse_args()

    creds = load_creds(args.qc_secrets)
    end = int(datetime.utcnow().timestamp())
    start = int((datetime.utcnow() - timedelta(days=args.days)).timestamp())

    algos: List[Dict[str, Any]] = []
    seen = set()
    for status in ("Running", "RuntimeError", "Stopped", "Liquidated", "Deleted"):
        payload = {"userId": int(creds["user_id"]), "start": start, "end": end, "status": status}
        data = post("live/list", payload, creds)
        rows: List[Dict[str, Any]] = data.get("algorithms", [])
        for r in rows:
            key = (r.get("projectId"), r.get("deployId"))
            if key in seen:
                continue
            seen.add(key)
            algos.append(r)
    out = []
    for a in algos:
        out.append(
            {
                "projectId": a.get("projectId"),
                "projectName": a.get("projectName"),
                "deployId": a.get("deployId"),
                "status": a.get("status"),
                "brokerage": a.get("brokerage"),
                "launched": a.get("launched"),
                "stopped": a.get("stopped"),
            }
        )

    print(json.dumps({"count": len(out), "deployments": out}, indent=2, default=str))


if __name__ == "__main__":
    main()
