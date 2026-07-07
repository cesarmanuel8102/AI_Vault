"""Poll Brain server /health until it responds 200 or timeout."""
import sys
import time
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import os
TOKEN = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
if not TOKEN:
    print("ERROR: BRAIN_ADMIN_TOKEN required."); sys.exit(2)
BASE = "http://127.0.0.1:8091"

def probe(path: str, timeout: float = 5.0):
    url = f"{BASE}{path}"
    req = Request(url, headers={"X-Brain-Token": TOKEN, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except URLError as e:
        return None, f"URLError: {e.reason}"
    except Exception as e:
        return None, f"Exception: {type(e).__name__}: {e}"


def main() -> int:
    deadline = time.time() + 120.0
    last_status = None
    last_body = ""
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        status, body = probe("/health")
        last_status, last_body = status, body
        if status == 200:
            print(f"READY after {attempts} attempts")
            print(f"HEALTH_BODY: {body[:400]}")
            return 0
        elapsed = int(time.time() - (deadline - 120.0))
        print(f"attempt={attempts} elapsed={elapsed}s status={status} body={body[:120]}")
        time.sleep(2.0)
    print(f"TIMEOUT after {attempts} attempts. Last status={last_status}, body={last_body[:300]}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
