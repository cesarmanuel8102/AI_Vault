import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

if any("EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1" in ln for ln in lines):
    print("SKIP: dispatch KV ya existe")
    raise SystemExit(0)

# find agent_execute_step def
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_execute_step\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute_step(...)")

# find first tool_name assignment after def
i_tool = None
for i in range(i_def, min(len(lines), i_def+800)):
    if re.match(r"\s*tool_name\s*=\s*", lines[i]):
        i_tool = i
        break
if i_tool is None:
    raise SystemExit("No encuentro asignación tool_name = ... dentro de agent_execute_step")

indent = re.match(r"(\s*)", lines[i_tool]).group(1)

block = []
block.append(f"{indent}# === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 BEGIN ===\n")
block.append(f"{indent}# Handle runtime_snapshot_set/get as non-gated tools (room-scoped KV)\n")
block.append(f"{indent}if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):\n")
block.append(f"{indent}    args = (step.get('tool_args') or {{}}) if isinstance(step, dict) else {{}}\n")
block.append(f"{indent}    snap_path = str(args.get('path') or '')\n")
block.append(f"{indent}    if tool_name == 'runtime_snapshot_set':\n")
block.append(f"{indent}        val = args.get('value')\n")
block.append(f"{indent}        # enrich minimal fields if dict\n")
block.append(f"{indent}        try:\n")
block.append(f"{indent}            from datetime import datetime, timezone\n")
block.append(f"{indent}            now = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{indent}        except Exception:\n")
block.append(f"{indent}            now = ''\n")
block.append(f"{indent}        if isinstance(val, dict):\n")
block.append(f"{indent}            vv = dict(val)\n")
block.append(f"{indent}            vv['ts'] = vv.get('ts') or now\n")
block.append(f"{indent}            try:\n")
block.append(f"{indent}                vv['goal'] = vv.get('goal') or str((plan or {{}}).get('goal') or '')\n")
block.append(f"{indent}            except Exception:\n")
block.append(f"{indent}                vv['goal'] = vv.get('goal') or ''\n")
block.append(f"{indent}            vv['room_id'] = vv.get('room_id') or str(room_id)\n")
block.append(f"{indent}            val = vv\n")
block.append(f"{indent}        res2 = _runtime_snapshot_set_kv(str(room_id), snap_path, val)\n")
block.append(f"{indent}        result = {{'ok': True, 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{indent}    else:\n")
block.append(f"{indent}        res2 = _runtime_snapshot_get_kv(str(room_id), snap_path)\n")
block.append(f"{indent}        result = {{'ok': bool(res2.get('ok', False)), 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{indent}    # continue (persist SOT will mark done)\n")
block.append(f"{indent}# === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 END ===\n")

# insert after tool_name line
lines = lines[:i_tool+1] + block + lines[i_tool+1:]
p.write_text("".join(lines), encoding="utf-8")
print("OK: inserted EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1")
