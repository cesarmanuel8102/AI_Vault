$ErrorActionPreference = 'Stop'
Set-Location C:/AI_VAULT/tmp_agent
$env:PYTHONPATH = 'C:/AI_VAULT/tmp_agent'

python -c @'
import json, sys
from brain_v9.autonomy.chat_excellence_patcher import (
    extract_constant_changes, dry_run_proposal, _plan_changes, _load_proposal
)

print("=== TEST 1: extract_constant_changes ===")
samples = [
    "Elevar _CB_FAIL_THRESHOLD de 2 a 5 y _CB_COOLDOWN_S de 180 a 60",
    "_CB_FAIL_THRESHOLD: from 2 to 5",
    "Cambiar _CB_COOLDOWN_S 180 -> 60",
    "_CB_COOLDOWN_S: 180 => 60",
    "deepseek14b timeout 30 a 15",  # constant w/o leading _ -> NO match expected
]
for s in samples:
    print(f"  IN : {s}")
    print(f"  OUT: {extract_constant_changes(s)}")

print()
print("=== TEST 2: dry_run on iter#6 proposal ===")
import os
prop_dir = "C:/AI_VAULT/tmp_agent/state/proposed_patches"
files = sorted(os.listdir(prop_dir), reverse=True)
print(f"Found {len(files)} proposals: {files[:5]}")

# pick most recent pending_review
target = None
for f in files:
    if not f.startswith("ce_prop_"): continue
    p = os.path.join(prop_dir, f)
    rec = json.load(open(p, encoding="utf-8"))
    if rec.get("status") == "pending_review":
        target = rec
        break

if target is None:
    print("  No pending_review proposal found - building synthetic from iter#6")
    # Synthesize one using iter#6 from history
    hist = json.load(open("C:/AI_VAULT/tmp_agent/state/chat_excellence_history.json", encoding="utf-8"))
    iter6 = next((it for it in hist if it.get("iter") == 6), None)
    if iter6:
        from brain_v9.autonomy.chat_excellence_executor import evaluate_iteration
        # Force valid affected_files for test - patch iter6 in-memory if needed
        if "core/llm.py" not in (iter6.get("affected_files") or []):
            iter6 = dict(iter6)
            iter6["affected_files"] = ["core/llm.py"]
            iter6["affected_files_invalid"] = []
            iter6["affected_files_validated"] = True
        target = evaluate_iteration(iter6)
        print(f"  Synthesized proposal: {target.get('proposal_id')} status={target.get('status')}")

if target:
    pid = target["proposal_id"]
    print(f"  Target proposal_id: {pid}")
    print(f"  Status: {target.get('status')}")
    print(f"  Affected files: {target.get('affected_files')}")
    print(f"  Proposed change (first 200ch): {target.get('proposed_change','')[:200]}")
    plan = _plan_changes(target)
    print(f"  Plan ok: {plan.get('ok')}, reason: {plan.get('reason')}")
    print(f"  Skipped: {plan.get('skipped', [])[:3]}")
    if plan.get("ok"):
        print(f"  Edits: {len(plan['edits'])}")
        for e in plan["edits"]:
            print(f"    - {e['rel_path']}:{e['line_idx']+1}")
            print(f"      OLD: {e['old_line'].strip()}")
            print(f"      NEW: {e['new_line'].strip()}")
    result = dry_run_proposal(pid)
    print(f"  dry_run ok: {result.get('ok')}")
    if result.get("diff"):
        print("  --- DIFF ---")
        print(result["diff"])
        print("  --- END DIFF ---")
'@
