"""
End-to-end autoconstruction test.
Runs the full self-improvement pipeline:
  1. create_staged_change (captures impact_before with chat metrics)
  2. validate_staged_change (syntax + import checks)
  3. promote_staged_change (generates PS1, restarts Brain V9, health check)
  4. Wait for promotion job to complete
  5. Verify: new Brain V9 healthy, new fastpath works, ledger updated
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

from brain_v9.brain.self_improvement import (
    create_staged_change,
    validate_staged_change,
    promote_staged_change,
)

TARGET_FILE = "C:/AI_VAULT/tmp_agent/brain_v9/core/session.py"
OBJECTIVE = "Add 'que hora es' fastpath - trivial autoconstruction test"

print("=" * 60)
print("  END-TO-END AUTOCONSTRUCTION TEST")
print("=" * 60)

# Step 1: Create staged change
print("\n[1/5] Creating staged change...")
try:
    meta = create_staged_change([TARGET_FILE], OBJECTIVE, "code_patch")
    change_id = meta["change_id"]
    print(f"  change_id: {change_id}")
    print(f"  status: {meta['status']}")
    print(f"  impact_before keys: {list(meta.get('impact_before', {}).keys())}")
    ib = meta.get("impact_before", {})
    print(f"  impact_before.chat_success_rate: {ib.get('chat_success_rate', 'NOT FOUND')}")
    print(f"  impact_before.self_test_score: {ib.get('self_test_score', 'NOT FOUND')}")
    print(f"  impact_before.u_score: {ib.get('u_score', 'NOT FOUND')}")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 2: Validate staged change
print(f"\n[2/5] Validating staged change {change_id}...")
try:
    val = validate_staged_change(change_id)
    print(f"  passed: {val['passed']}")
    print(f"  checks: {list(val.get('checks', {}).keys())}")
    for check_name, check_data in val.get("checks", {}).items():
        passed = check_data.get("passed")
        print(f"    {check_name}: {'PASS' if passed else ('SKIP' if passed is None else 'FAIL')}")
    if val.get("errors"):
        print(f"  errors: {val['errors']}")
    if not val["passed"]:
        print("  VALIDATION FAILED - aborting")
        sys.exit(1)
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 3: Promote staged change
print(f"\n[3/5] Promoting staged change {change_id}...")
print("  (This will restart Brain V9 - expect downtime)")
try:
    promo = promote_staged_change(change_id)
    print(f"  status: {promo['status']}")
    print(f"  job_id: {promo.get('job_id', '?')}")
    print(f"  helper: {promo.get('helper', '?')}")
    artifact_path = promo.get("artifact", "")
    job_path = promo.get("job_artifact", "")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 4: Wait for promotion job to complete
print(f"\n[4/5] Waiting for promotion job to complete...")
import requests

# Wait for Brain V9 to go down and come back
time.sleep(5)
max_wait = 90
start = time.time()
healthy = False
for i in range(max_wait):
    try:
        r = requests.get("http://localhost:8090/health", timeout=3)
        if r.ok and r.json().get("status") == "healthy":
            elapsed = time.time() - start
            print(f"  Brain V9 healthy after {elapsed:.1f}s")
            healthy = True
            break
    except:
        pass
    time.sleep(1)

if not healthy:
    print(f"  Brain V9 did not come back healthy after {max_wait}s")
    sys.exit(1)

# Check promotion result artifact
time.sleep(3)  # give PS1 time to write artifact
if artifact_path and Path(artifact_path).exists():
    result_data = json.loads(Path(artifact_path).read_text(encoding="utf-8-sig"))
    print(f"  promotion_result.promoted: {result_data.get('promoted', '?')}")
    print(f"  promotion_result.rollback: {result_data.get('rollback', '?')}")
    print(f"  promotion_result.health_status: {result_data.get('health_status', '?')}")
    print(f"  promotion_result.metric_check_passed: {result_data.get('metric_check_passed', '?')}")
    endpoints = result_data.get("endpoint_results", [])
    for ep in endpoints:
        if isinstance(ep, dict):
            print(f"    endpoint {ep.get('endpoint','?')}: ok={ep.get('ok','?')}")
else:
    print(f"  promotion artifact not found at {artifact_path}")

# Step 5: Verify new fastpath works
print(f"\n[5/5] Verifying new 'que hora es' fastpath...")
try:
    r = requests.post("http://localhost:8090/chat",
                       json={"message": "que hora es"},
                       timeout=15)
    data = r.json()
    resp = data.get("response", "")
    model = data.get("model_used", "?")
    success = data.get("success", False)
    has_time = "hora" in resp.lower() or ":" in resp
    print(f"  response: {resp[:120]}")
    print(f"  model: {model}")
    print(f"  success: {success}")
    print(f"  fastpath confirmed: {model == 'system' and has_time}")
except Exception as e:
    print(f"  FAILED: {e}")

# Read updated ledger
print(f"\n--- LEDGER CHECK ---")
ledger_path = Path("C:/AI_VAULT/tmp_agent/state/self_improvement/self_improvement_ledger.json")
if ledger_path.exists():
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = None
    for e in ledger["entries"]:
        if e["change_id"] == change_id:
            entry = e
            break
    if entry:
        print(f"  change_id: {entry['change_id']}")
        print(f"  status: {entry['status']}")
        print(f"  validation: {entry.get('validation', '?')}")
        print(f"  gate: {entry.get('gate', '?')}")
        ib2 = entry.get("impact_before", {})
        print(f"  impact_before.chat_success_rate: {ib2.get('chat_success_rate', 'NOT FOUND')}")
        print(f"  impact_before.self_test_score: {ib2.get('self_test_score', 'NOT FOUND')}")
        print(f"  impact_before.chat_total: {ib2.get('chat_total', 'NOT FOUND')}")
        ia = entry.get("impact_after")
        print(f"  impact_after: {ia if ia else 'NULL'}")
        delta = entry.get("impact_delta")
        print(f"  impact_delta: {delta if delta else 'NULL'}")
    else:
        print(f"  Entry for {change_id} not found in ledger!")
else:
    print("  Ledger file not found!")

print("\n" + "=" * 60)
print("  END-TO-END TEST COMPLETE")
print("=" * 60)
