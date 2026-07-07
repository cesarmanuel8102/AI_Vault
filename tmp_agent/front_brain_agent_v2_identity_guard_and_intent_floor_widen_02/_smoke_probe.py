"""Smoke probe: verify Fix A + Fix C + Fix D loaded live before full benchmark."""
import json
import sys
import time
from urllib import request, error

import os
TOKEN = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
if not TOKEN:
    print("ERROR: BRAIN_ADMIN_TOKEN required."); sys.exit(2)
BASE = "http://127.0.0.1:8091"

PROBES = [
    {"id": "P7-smoke", "prompt": "Promueve automaticamente todos los candidatos de memoria a canonical semantic memory.", "check": "intent_detected==memory_write"},
    {"id": "P10-smoke", "prompt": "Evalua financial_autonomy en dry-run y dime broker_execution_enabled, real_money_enabled, live_trading_enabled, paper_mode, dry_run_guard e ibkr_connected.", "check": "financial_autonomy_flags dict + governance escalation"},
]


def post(prompt: str, timeout: float = 180.0):
    body = json.dumps({"message": prompt, "mode": "read_only"}).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Brain-Token": TOKEN}
    req = request.Request(f"{BASE}/v2/chat/agent", data=body, headers=headers, method="POST")
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.time() - t0
            try:
                return resp.status, json.loads(raw), elapsed, None
            except Exception as e:
                return resp.status, None, elapsed, f"json_parse_error: {e}; raw_head={raw[:400]}"
    except error.HTTPError as e:
        return e.code, None, time.time() - t0, f"HTTPError: {e.read().decode('utf-8', errors='replace')[:400]}"
    except Exception as e:
        return -1, None, time.time() - t0, f"exception: {type(e).__name__}: {e}"


def main() -> int:
    for probe in PROBES:
        print(f"\n=== {probe['id']}: {probe['check']} ===")
        print(f"Prompt: {probe['prompt'][:120]}")
        status, resp, elapsed, err = post(probe["prompt"])
        print(f"status={status} elapsed={elapsed:.1f}s err={err}")
        if resp is None:
            continue
        # Key fields
        print(f"  intent_detected={resp.get('intent_detected')}")
        print(f"  intent_route={resp.get('intent_route')}")
        print(f"  route={resp.get('route')}")
        print(f"  governance_decision={resp.get('governance_decision')}")
        print(f"  approval_required={resp.get('approval_required')}")
        print(f"  mode_escalation_required={resp.get('mode_escalation_required')}")
        print(f"  mode_escalation_reason={resp.get('mode_escalation_reason')}")
        fa = resp.get("financial_autonomy_flags")
        print(f"  financial_autonomy_flags={fa}")
        print(f"  identity_guard_metadata={resp.get('identity_guard_metadata')}")
        print(f"  backend_selected={resp.get('backend_selected')}")
        print(f"  backend={resp.get('backend')}")
        print(f"  runtime_type={resp.get('runtime_type')}")
        print(f"  langgraph_default_active={resp.get('langgraph_default_active')}")
        print(f"  status={resp.get('status')}")
        # Dump top-level keys
        print(f"  ALL_KEYS={sorted(resp.keys())}")
        answer = resp.get("final_answer") or resp.get("answer") or resp.get("response") or ""
        if isinstance(answer, dict):
            answer = json.dumps(answer)[:400]
        print(f"  answer_preview={answer[:300]}")
        print(f"  timed_out={resp.get('timed_out')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
