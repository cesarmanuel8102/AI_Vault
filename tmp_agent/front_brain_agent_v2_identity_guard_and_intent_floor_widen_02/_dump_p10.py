"""Dump full raw response body for P10 to find financial_autonomy_flags placement."""
import json
import sys
from urllib import request, error

TOKEN = "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B"
BASE = "http://127.0.0.1:8091"

body = json.dumps({"message": "Evalua financial_autonomy en dry-run y dime broker_execution_enabled, real_money_enabled, live_trading_enabled, paper_mode, dry_run_guard e ibkr_connected.", "mode": "read_only"}).encode("utf-8")
headers = {"Content-Type": "application/json", "X-Brain-Token": TOKEN}
req = request.Request(f"{BASE}/v2/chat/agent", data=body, headers=headers, method="POST")

try:
    with request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)

        # Search for "financial_autonomy_flags" anywhere in the tree
        def find_key(obj, target, path="root"):
            hits = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == target:
                        hits.append((f"{path}.{k}", type(v).__name__, str(v)[:200]))
                    hits.extend(find_key(v, target, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    hits.extend(find_key(v, target, f"{path}[{i}]"))
            return hits

        hits = find_key(parsed, "financial_autonomy_flags")
        print(f"Occurrences of financial_autonomy_flags: {len(hits)}")
        for h in hits:
            print(f"  path={h[0]} type={h[1]} val={h[2]}")

        # Also dump top-level structure
        print(f"\nTop-level keys ({len(parsed)}):")
        for k, v in parsed.items():
            t = type(v).__name__
            preview = "" if v is None else (str(v)[:80] if not isinstance(v, (dict, list)) else f"({len(v)} items)")
            print(f"  {k} ({t}) {preview}")

        # Write to file for inspection
        with open("C:/AI_VAULT_CANONICAL/tmp_agent/front_brain_agent_v2_identity_guard_and_intent_floor_widen_02/_p10_dump.json", "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        print("\nFull body written to _p10_dump.json")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)
