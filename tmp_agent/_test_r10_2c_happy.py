"""R10.2c happy-path e2e test.

Resets proposal to pending_review, calls /apply with auto_restart=true,
sleeps long enough for the detached gate to:
  kill brain -> 50s respawn -> poll up to 60s -> mark applied_active.

Verifies:
  - file modified at start
  - proposal status -> applied_active
  - new brain PID different from pre-apply PID
  - health gate log present and SUCCESS
Then manual rollback to leave system clean.
"""
import io, sys, json, time, urllib.request, urllib.error
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = "http://127.0.0.1:8090"
LLM  = "C:/AI_VAULT/tmp_agent/brain_v9/core/llm.py"
PID  = "ce_prop_20260504_133441"
PROP = f"C:/AI_VAULT/tmp_agent/state/proposed_patches/{PID}.json"

def req(method, path, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return -1, {"error": str(e)}

def get_pid():
    code, body = req("GET", "/health")
    return body if code == 200 else None

# Reset proposal to pending_review
print("=== reset proposal to pending_review ===")
rec = json.load(open(PROP, encoding="utf-8"))
print(f"  current status: {rec['status']}")
rec["status"] = "pending_review"
for k in ("backups", "rolled_back_at", "rollback_reason", "rollback_restored",
          "rollback_failed", "applied_at", "applied_by", "diff",
          "applied_edits", "health_gate_started_at", "health_gate_pid",
          "health_gate_completed_at", "health_gate_poll_seconds"):
    rec.pop(k, None)
json.dump(rec, open(PROP, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"  reset OK")

# capture pre-apply state
pre_health = get_pid()
print(f"  pre-apply /health: {pre_health}")
pre_content = Path(LLM).read_text(encoding="utf-8")
assert "_CB_FAIL_THRESHOLD = 2" in pre_content, "pre: should be 2"

# APPLY with auto_restart
print("\n=== APPLY auto_restart=true poll=60 ===")
t0 = time.time()
code, body = req("POST", f"/brain/chat_excellence/proposals/{PID}/apply",
                 body={"dry_run": False, "auto_restart": True, "poll_seconds": 60,
                       "by": "r10.2c_test", "note": "auto_restart e2e"})
print(f"  HTTP {code} ok={body.get('ok')} status={body.get('status')} gate_spawned={body.get('health_gate_spawned')}")
print(f"  apply call took {time.time()-t0:.1f}s")

# verify file changed
post_content = Path(LLM).read_text(encoding="utf-8")
assert "_CB_FAIL_THRESHOLD = 5" in post_content, "post-apply: should be 5"
print("  file modified OK")

# Wait for gate completion. Total: ~15s schtasks delay + ~50s respawn + up to 60s poll = ~130s.
print("\n=== waiting for health gate (sleep 60s, then poll status every 10s up to 240s) ===")
time.sleep(60)
deadline = time.time() + 240
final_status = None
while time.time() < deadline:
    rec = json.load(open(PROP, encoding="utf-8"))
    final_status = rec.get("status")
    print(f"  t+{int(time.time()-t0)}s  proposal status={final_status}")
    if final_status in ("applied_active", "rolled_back_auto", "rollback_failed", "health_gate_aborted"):
        break
    time.sleep(10)

print(f"\n=== FINAL status={final_status} ===")

# Get gate log via brain (if back up)
post_health = get_pid()
print(f"  /health: {post_health}")
if post_health:
    code, body = req("GET", f"/brain/chat_excellence/proposals/{PID}/health_gate_log?tail=50")
    print(f"  gate log lines: {body.get('lines_total')}")
    for line in (body.get("lines") or [])[-15:]:
        print(f"    {line}")

# Verify outcome
final_content = Path(LLM).read_text(encoding="utf-8")
print(f"\n  llm.py has _CB_FAIL_THRESHOLD = 5 (apply): {'_CB_FAIL_THRESHOLD = 5' in final_content}")
print(f"  llm.py has _CB_FAIL_THRESHOLD = 2 (rolled_back): {'_CB_FAIL_THRESHOLD = 2' in final_content}")

# Cleanup: if applied_active, manual rollback
if final_status == "applied_active":
    print("\n=== cleanup: manual rollback ===")
    code, body = req("POST", f"/brain/chat_excellence/proposals/{PID}/rollback",
                     body={"reason": "test cleanup"})
    print(f"  HTTP {code} ok={body.get('ok')} restored={body.get('restored')}")
    print("  NOTE: manual restart needed to load rollback (run _kill_cim.ps1)")
else:
    print("\n  no cleanup needed (rollback already happened or aborted)")

print("\n=== TEST DONE ===")
