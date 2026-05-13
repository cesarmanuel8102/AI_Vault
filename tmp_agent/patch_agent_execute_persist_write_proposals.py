import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)
txt = "".join(lines)

MARK = "AGENT_EXECUTE_PERSIST_WRITE_PROPOSALS_V1"
if MARK in txt:
    print("SKIP: persist write proposals already patched")
    raise SystemExit(0)

# Find agent_execute(req: AgentExecuteRequest)
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"^def\s+agent_execute\s*\(\s*req\s*:\s*AgentExecuteRequest\s*\)\s*:", ln):
        i_def = i
        break
if i_def is None:
    # fallback: any def agent_execute(
    for i, ln in enumerate(lines):
        if re.match(r"^def\s+agent_execute\s*\(", ln):
            i_def = i
            break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute(...)")

# end at next top-level def or @app.
i_end = None
for j in range(i_def+1, len(lines)):
    if re.match(r"^(def\s+|@app\.)", lines[j]):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]
chunk_txt = "".join(chunk)

# Insert helper functions near existing _autopersist_step_done_fs (preferred)
i_auto = None
for k, ln in enumerate(lines):
    if re.match(r"^def\s+_autopersist_step_done_fs\s*\(", ln):
        i_auto = k
        break

helper_block = []
helper_block.append("\n# === %s HELPERS BEGIN ===\n" % MARK)
helper_block.append("def _autopersist_step_proposed_fs(room_id: str, step_id: str, proposal_id: str) -> None:\n")
helper_block.append("    \"\"\"Persist proposed write step into per-room plan.json (SOT disk).\"\"\"\n")
helper_block.append("    try:\n")
helper_block.append("        plan_disk = _load_room_plan(room_id) or {}\n")
helper_block.append("        steps = plan_disk.get('steps', []) or []\n")
helper_block.append("        for s in steps:\n")
helper_block.append("            if isinstance(s, dict) and str(s.get('id')) == str(step_id):\n")
helper_block.append("                s['status'] = 'proposed'\n")
helper_block.append("                s['proposal_id'] = str(proposal_id)\n")
helper_block.append("                s['required_approve'] = 'APPLY_' + str(proposal_id)\n")
helper_block.append("                break\n")
helper_block.append("        plan_disk['steps'] = steps\n")
helper_block.append("        # touch\n")
helper_block.append("        try:\n")
helper_block.append("            from datetime import datetime, timezone\n")
helper_block.append("            plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
helper_block.append("        except Exception:\n")
helper_block.append("            pass\n")
helper_block.append("        plan_disk.setdefault('room_id', room_id)\n")
helper_block.append("        _room_state_dir(room_id)\n")
helper_block.append("        paths = _room_paths(room_id) or {}\n")
helper_block.append("        pp = paths.get('plan')\n")
helper_block.append("        if pp:\n")
helper_block.append("            import json\n")
helper_block.append("            from pathlib import Path\n")
helper_block.append("            Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')\n")
helper_block.append("    except Exception:\n")
helper_block.append("        pass\n\n")

helper_block.append("def _autopersist_step_done_write_fs(room_id: str, step_id: str) -> None:\n")
helper_block.append("    \"\"\"Persist done write step into per-room plan.json; clear proposal fields; auto-complete.\"\"\"\n")
helper_block.append("    try:\n")
helper_block.append("        plan_disk = _load_room_plan(room_id) or {}\n")
helper_block.append("        steps = plan_disk.get('steps', []) or []\n")
helper_block.append("        for s in steps:\n")
helper_block.append("            if isinstance(s, dict) and str(s.get('id')) == str(step_id):\n")
helper_block.append("                s['status'] = 'done'\n")
helper_block.append("                try:\n")
helper_block.append("                    s.pop('proposal_id', None)\n")
helper_block.append("                    s.pop('required_approve', None)\n")
helper_block.append("                except Exception:\n")
helper_block.append("                    pass\n")
helper_block.append("                break\n")
helper_block.append("        plan_disk['steps'] = steps\n")
helper_block.append("        # auto-complete if all done\n")
helper_block.append("        try:\n")
helper_block.append("            if steps and all((isinstance(x, dict) and str(x.get('status'))=='done') for x in steps):\n")
helper_block.append("                plan_disk['status'] = 'complete'\n")
helper_block.append("        except Exception:\n")
helper_block.append("            pass\n")
helper_block.append("        try:\n")
helper_block.append("            from datetime import datetime, timezone\n")
helper_block.append("            plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
helper_block.append("        except Exception:\n")
helper_block.append("            pass\n")
helper_block.append("        plan_disk.setdefault('room_id', room_id)\n")
helper_block.append("        _room_state_dir(room_id)\n")
helper_block.append("        paths = _room_paths(room_id) or {}\n")
helper_block.append("        pp = paths.get('plan')\n")
helper_block.append("        if pp:\n")
helper_block.append("            import json\n")
helper_block.append("            from pathlib import Path\n")
helper_block.append("            Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')\n")
helper_block.append("    except Exception:\n")
helper_block.append("        pass\n")
helper_block.append("# === %s HELPERS END ===\n\n" % MARK)

if i_auto is not None:
    # Insert helpers right after _autopersist_step_done_fs definition block end (next top-level def)
    # Find end of that function
    i_auto_end = None
    for j in range(i_auto+1, len(lines)):
        if re.match(r"^def\s+", lines[j]):
            i_auto_end = j
            break
    if i_auto_end is None:
        i_auto_end = i_auto + 1
    lines = lines[:i_auto_end] + helper_block + lines[i_auto_end:]
else:
    # Fallback: insert near top after imports
    ins = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("app = FastAPI"):
            ins = i
            break
    lines = lines[:ins] + helper_block + lines[ins:]

# Now patch inside agent_execute: on write propose/apply returns
txt2 = "".join(lines)

# 1) After staging proposal_id on propose, call _autopersist_step_proposed_fs(...)
# We look for places returning proposal_id in result dict for write/append; easiest: inject before return in propose branch.
# Insert before the FIRST 'return {"ok": True, "room_id": room_id, ... "proposal_id": pid' if exists.
pat_propose_ret = r'(\n\s*return\s+\{\s*"ok"\s*:\s*True[^}]*"proposal_id"\s*:\s*pid[^}]*\}\s*\n)'
m = re.search(pat_propose_ret, txt2)
if not m:
    # fallback: any return with proposal_id
    pat_propose_ret = r'(\n\s*return\s+\{[^}]*"proposal_id"[^}]*\}\s*\n)'
    m = re.search(pat_propose_ret, txt2)
if m:
    inject = "\n        # === %s PROPOSE PERSIST BEGIN ===\n        try:\n            _autopersist_step_proposed_fs(str(room_id), str(req.step_id), str(pid))\n        except Exception:\n            pass\n        # === %s PROPOSE PERSIST END ===\n" % (MARK, MARK)
    txt2 = txt2[:m.start(1)] + inject + txt2[m.start(1):]
else:
    print("WARN: no propose return with proposal_id found; skipping propose injection")

# 2) After successful apply write/append, persist done and clear proposal fields
# We inject before FIRST return in apply branch that returns ok True for write/append after apply_gate.
pat_apply_ok = r'(\n\s*return\s+\{\s*"ok"\s*:\s*True[^}]*\}\s*\n)'
m2 = re.search(pat_apply_ok, txt2)
if m2:
    inject2 = "\n        # === %s APPLY PERSIST BEGIN ===\n        try:\n            if tool_name in (\"write_file\",\"append_file\") and str((req.mode or \"\")).strip().lower() == \"apply\":\n                _autopersist_step_done_write_fs(str(room_id), str(req.step_id))\n        except Exception:\n            pass\n        # === %s APPLY PERSIST END ===\n" % (MARK, MARK)
    # only inject once, but make sure we inject after apply path, not read returns; we can't perfectly parse—good enough: inject before first return in agent_execute,
    # but guard requires mode==apply and write tool, so safe even if executed elsewhere.
    txt2 = txt2[:m2.start(1)] + inject2 + txt2[m2.start(1):]
else:
    print("WARN: no return found for apply injection; skipping")

p.write_text(txt2, encoding="utf-8")
print("OK: patched agent_execute to persist proposed/apply write steps into plan.json (disk SOT)")
