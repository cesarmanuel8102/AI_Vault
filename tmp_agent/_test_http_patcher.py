import urllib.request, urllib.error, json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8090"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

print("=== LIST proposals ===")
code, body = req("GET", "/brain/chat_excellence/proposals?limit=10")
print(f"  HTTP {code} count={body.get('count')} stats={body.get('stats')}")
for it in body.get("items", []):
    print(f"   {it['proposal_id']} status={it['status']} risk={it['risk_class']} files={it.get('affected_files')}")

# pick the synthetic one we created
target = "ce_prop_20260504_133441"
print(f"\n=== GET {target} ===")
code, body = req("GET", f"/brain/chat_excellence/proposals/{target}")
print(f"  HTTP {code} status={body.get('status')}")

print(f"\n=== DRY_RUN {target} ===")
code, body = req("POST", f"/brain/chat_excellence/proposals/{target}/dry_run")
print(f"  HTTP {code} ok={body.get('ok')} edits={body.get('edits_count')} skipped={body.get('skipped')}")

# Reset proposal status to pending_review for clean apply test (its current status is rolled_back)
import json as _j
prop_path = f"C:/AI_VAULT/tmp_agent/state/proposed_patches/{target}.json"
rec = _j.load(open(prop_path, encoding="utf-8"))
print(f"\n  Current persisted status: {rec['status']}")
rec["status"] = "pending_review"
rec.pop("backups", None)
rec.pop("rolled_back_at", None)
_j.dump(rec, open(prop_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("  Reset to pending_review for full e2e test")

print(f"\n=== APPLY (dry_run=true default) ===")
code, body = req("POST", f"/brain/chat_excellence/proposals/{target}/apply", body={})
print(f"  HTTP {code} mode={body.get('mode')} ok={body.get('ok')} edits={body.get('edits_count')}")

print(f"\n=== APPLY (dry_run=false) — REAL ===")
code, body = req("POST", f"/brain/chat_excellence/proposals/{target}/apply",
                 body={"dry_run": False, "by": "http_test", "note": "r10.2b e2e"})
print(f"  HTTP {code} mode={body.get('mode')} ok={body.get('ok')} status={body.get('status')}")
print(f"  backups={body.get('backups')}")

# verify file
from pathlib import Path
content = Path("C:/AI_VAULT/tmp_agent/brain_v9/core/llm.py").read_text(encoding="utf-8")
print(f"  file has _CB_FAIL_THRESHOLD = 5: {'_CB_FAIL_THRESHOLD = 5' in content}")
print(f"  file has _CB_COOLDOWN_S = 60: {'_CB_COOLDOWN_S = 60' in content}")

print(f"\n=== ROLLBACK ===")
code, body = req("POST", f"/brain/chat_excellence/proposals/{target}/rollback",
                 body={"reason": "r10.2b e2e cleanup"})
print(f"  HTTP {code} ok={body.get('ok')} restored={body.get('restored')}")

content2 = Path("C:/AI_VAULT/tmp_agent/brain_v9/core/llm.py").read_text(encoding="utf-8")
print(f"  file has _CB_FAIL_THRESHOLD = 2: {'_CB_FAIL_THRESHOLD = 2' in content2}")
print(f"  file has _CB_COOLDOWN_S = 180: {'_CB_COOLDOWN_S = 180' in content2}")

print("\n=== ALL HTTP TESTS DONE ===")
