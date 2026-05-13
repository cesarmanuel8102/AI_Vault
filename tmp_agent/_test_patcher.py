import json, os, sys
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
from brain_v9.autonomy.chat_excellence_patcher import (
    extract_constant_changes, dry_run_proposal, _plan_changes, _load_proposal
)

print("=== TEST 1: extract_constant_changes ===")
samples = [
    "Elevar _CB_FAIL_THRESHOLD de 2 a 5 y _CB_COOLDOWN_S de 180 a 60",
    "_CB_FAIL_THRESHOLD: from 2 to 5",
    "Cambiar _CB_COOLDOWN_S 180 -> 60",
    "_CB_COOLDOWN_S: 180 => 60",
    "deepseek14b timeout 30 a 15",
]
for s in samples:
    print(f"  IN : {s}")
    print(f"  OUT: {extract_constant_changes(s)}")

print()
print("=== TEST 2: dry_run on existing or synthetic proposal ===")
prop_dir = "C:/AI_VAULT/tmp_agent/state/proposed_patches"
files = sorted(os.listdir(prop_dir), reverse=True)
print(f"Found {len(files)} proposals: {files[:5]}")

target = None
for f in files:
    if not f.startswith("ce_prop_"):
        continue
    p = os.path.join(prop_dir, f)
    rec = json.load(open(p, encoding="utf-8"))
    if rec.get("status") == "pending_review":
        target = rec
        break

if target is None:
    print("  No pending_review proposal found - building synthetic from iter#6")
    hist_path = "C:/AI_VAULT/tmp_agent/state/chat_excellence_history.json"
    hist = json.load(open(hist_path, encoding="utf-8"))
    iter6 = next((it for it in hist if it.get("iter") == 6), None)
    if iter6:
        from brain_v9.autonomy.chat_excellence_executor import evaluate_iteration
        iter6 = dict(iter6)
        iter6["affected_files"] = ["core/llm.py"]
        iter6["affected_files_invalid"] = []
        iter6["affected_files_validated"] = True
        target = evaluate_iteration(iter6)
        print(f"  Synthesized: {target.get('proposal_id')} status={target.get('status')}")

if target:
    pid = target["proposal_id"]
    print(f"  Target: {pid}  status={target.get('status')}")
    print(f"  Affected: {target.get('affected_files')}")
    print(f"  Change[:300]: {target.get('proposed_change','')[:300]}")
    plan = _plan_changes(target)
    print(f"  Plan ok={plan.get('ok')} reason={plan.get('reason')}")
    print(f"  Skipped: {plan.get('skipped', [])[:3]}")
    if plan.get("ok"):
        print(f"  Edits: {len(plan['edits'])}")
        for e in plan["edits"]:
            print(f"    - {e['rel_path']}:{e['line_idx']+1}")
            print(f"      OLD: {e['old_line'].strip()}")
            print(f"      NEW: {e['new_line'].strip()}")
    result = dry_run_proposal(pid)
    print(f"  dry_run ok={result.get('ok')}")
    if result.get("diff"):
        print("  --- DIFF ---")
        print(result["diff"])
