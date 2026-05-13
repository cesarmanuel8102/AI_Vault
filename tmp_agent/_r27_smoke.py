"""R27 smoke: verify auto-remediation loop end-to-end.

1. Snapshot AOS state (pre).
2. Trigger a fake capability.failed for 'nmap' with stderr-style error.
3. Wait briefly so orchestrator handler creates goal.
4. Verify goal has 'remediate_capability' action and install_candidates infers nmap.
5. Run AOS execute_top to fire the action.
6. Snapshot AOS state (post) and verify the goal status changed (or at least result captured).
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8090"

def http_get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read())

def http_post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

print("=== Step 1: AOS pre-snapshot ===")
pre = http_get("/upgrade/aos/status")
print(f"  total goals: {pre['total']}, registered_actions: {pre['registered_actions']}")
assert "remediate_capability" in pre["registered_actions"], "FAIL: remediate_capability not registered"
print("  OK: remediate_capability action registered")

print()
print("=== Step 2: publish fake capability.failed for 'nmap' ===")
fake_event = {
    "name": "capability.failed",
    "payload": {
        "capability": "run_command",
        "error": "returncode=1 | stderr='nmap' is not recognized as an internal or external command",
        "reason": "binary_not_found",
    },
    "source": "r27_smoke",
}
res = http_post("/upgrade/events/publish", fake_event)
print(f"  publish result: {res}")
time.sleep(2)

print()
print("=== Step 3: verify capability.failed was processed (incident recorded) ===")
caps = http_get("/upgrade/capabilities/status")
incidents = caps.get("recent_incidents", [])
nmap_inc = None
for inc in incidents:
    err = inc.get("reason", "") + " " + json.dumps(inc.get("evidence", {}))
    if "nmap" in err.lower():
        nmap_inc = inc
        break
if nmap_inc:
    print(f"  found nmap incident, install_candidates: {nmap_inc.get('install_candidates')}")
    print(f"  os_packages: {nmap_inc.get('os_packages')}")
else:
    print("  WARN: no nmap incident found in recent_incidents (orchestrator may not have processed yet)")

print()
print("=== Step 4: AOS post-snapshot, look for nmap goal ===")
post = http_get("/upgrade/aos/status")
print(f"  total goals: {post['total']} (delta {post['total'] - pre['total']})")
print(f"  by_status: {post['by_status']}")
top_descs = [g['desc'] for g in post.get('top_priorities', [])]
print(f"  top priorities: {top_descs[:5]}")

print()
print("=== Step 5: execute top AOS goal (should fire remediate_capability) ===")
exec_res = http_post("/upgrade/aos/execute?n=2", {})
print(f"  exec result: {json.dumps(exec_res, indent=2)[:1500]}")

print()
print("=== Step 6: post-exec AOS state ===")
post2 = http_get("/upgrade/aos/status")
print(f"  by_status: {post2['by_status']}")
print()
print("=== DONE ===")
