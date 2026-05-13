import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# find agent_run_once
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_run_once\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_run_once(...)")

def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
body = def_indent + "    "

# find line where room_id is set
i_room = None
for i in range(i_def, min(len(lines), i_def+40)):
    if re.match(rf"{re.escape(body)}room_id\s*=\s*", lines[i]):
        i_room = i
        break
if i_room is None:
    raise SystemExit("No encuentro asignación room_id dentro de agent_run_once")

# find the line "mission, plan = agent_store.load()"
i_load = None
for i in range(i_room, min(len(lines), i_room+30)):
    if "mission, plan = agent_store.load()" in lines[i]:
        i_load = i
        break
if i_load is None:
    raise SystemExit("No encuentro 'mission, plan = agent_store.load()' cerca; abortando.")

MARK = "RUN_ONCE ROOM LOAD (FIX)"
if any(MARK in ln for ln in lines[i_def:i_def+600]):
    print("SKIP: ya existe RUN_ONCE ROOM LOAD (FIX)")
    raise SystemExit(0)

block = []
block.append(f"{body}# === {MARK} BEGIN ===\n")
block.append(f"{body}mission, plan = {{}}, {{}}\n")
block.append(f"{body}try:\n")
block.append(f"{body}    _room_state_dir(room_id)\n")
block.append(f"{body}    paths = _room_paths(room_id) or {{}}\n")
block.append(f"{body}    import json\n")
block.append(f"{body}    from pathlib import Path\n")
block.append(f"{body}    pm = paths.get('mission')\n")
block.append(f"{body}    pp = paths.get('plan')\n")
block.append(f"{body}    if pm and Path(pm).exists():\n")
block.append(f"{body}        mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {{}}\n")
block.append(f"{body}    if pp and Path(pp).exists():\n")
block.append(f"{body}        plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {{}}\n")
block.append(f"{body}except Exception:\n")
block.append(f"{body}    mission, plan = {{}}, {{}}\n")
block.append(f"{body}# Fallback compat: if empty, try global store\n")
block.append(f"{body}if not plan:\n")
block.append(f"{body}    try:\n")
block.append(f"{body}        mission, plan = agent_store.load()\n")
block.append(f"{body}    except Exception:\n")
block.append(f"{body}        mission, plan = {{}}, {{}}\n")
block.append(f"{body}# === {MARK} END ===\n")

# Replace the single line "mission, plan = agent_store.load()" with our block
new_lines = []
new_lines.extend(lines[:i_load])
new_lines.extend(block)
new_lines.extend(lines[i_load+1:])

p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: replaced agent_store.load() in run_once with per-room disk load at line {i_load+1}")
