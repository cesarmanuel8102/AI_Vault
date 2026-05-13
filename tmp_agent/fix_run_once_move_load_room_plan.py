import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# locate agent_run_once
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_run_once\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_run_once")

def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
b = def_indent + "    "

# find room_id assignment
i_room = None
for i in range(i_def, min(len(lines), i_def+120)):
    if re.match(rf"{re.escape(b)}room_id\s*=\s*", lines[i]):
        i_room = i
        break
if i_room is None:
    raise SystemExit("No encuentro room_id = ... en agent_run_once")

# if already defined shortly after room_id, skip
window = "".join(lines[i_room+1:i_room+60])
if "def _load_room_plan" in window:
    print("SKIP: _load_room_plan ya está definido temprano")
    raise SystemExit(0)

helper = []
helper.append(f"{b}# === RUN_ONCE RELOAD ROOM PLAN (FIX) EARLY DEF ===\n")
helper.append(f"{b}def _load_room_plan(_rid: str) -> dict:\n")
helper.append(f"{b}    try:\n")
helper.append(f"{b}        _room_state_dir(_rid)\n")
helper.append(f"{b}        _paths = _room_paths(_rid) or {{}}\n")
helper.append(f"{b}        import json\n")
helper.append(f"{b}        from pathlib import Path\n")
helper.append(f"{b}        pp = _paths.get('plan')\n")
helper.append(f"{b}        if pp and Path(pp).exists():\n")
helper.append(f"{b}            return json.loads(Path(pp).read_text(encoding='utf-8')) or {{}}\n")
helper.append(f"{b}    except Exception:\n")
helper.append(f"{b}        return {{}}\n")
helper.append(f"{b}    return {{}}\n")
helper.append(f"{b}# === END EARLY DEF ===\n")

new_lines = []
new_lines.extend(lines[:i_room+1])
new_lines.extend(helper)
new_lines.extend(lines[i_room+1:])

p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted early _load_room_plan after room_id at line {i_room+1}")
