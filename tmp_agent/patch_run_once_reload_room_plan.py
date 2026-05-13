import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# locate agent_run_once def
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_run_once\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_run_once(...)")

def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
b = def_indent + "    "

# find insertion point after room_id assignment (line containing 'room_id =')
i_room = None
for i in range(i_def, min(len(lines), i_def+60)):
    if re.match(rf"{re.escape(b)}room_id\s*=\s*", lines[i]):
        i_room = i
        break
if i_room is None:
    raise SystemExit("No encuentro asignación room_id dentro de agent_run_once")

MARK = "RUN_ONCE RELOAD ROOM PLAN (FIX)"
if any(MARK in ln for ln in lines[i_def:i_def+800]):
    print("SKIP: ya existe reload-room-plan")
    raise SystemExit(0)

helper = []
helper.append(f"{b}# === {MARK} BEGIN ===\n")
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
helper.append(f"{b}# === {MARK} END ===\n")

# insert helper after room_id line
new_lines = []
new_lines.extend(lines[:i_room+1])
new_lines.extend(helper)
new_lines.extend(lines[i_room+1:])

txt2 = "".join(new_lines)

# Replace occurrences of "_, plan2 = agent_store.load()" inside run_once with room load
txt2 = re.sub(rf"\n{re.escape(b)}_,\s*plan2\s*=\s*agent_store\.load\(\)\s*\n",
              f"\n{b}plan2 = _load_room_plan(room_id)\n",
              txt2)

# After executing a step propose/apply, reload plan from disk.
# Insert right after "res = agent_execute_step(...)" lines (both propose and apply)
txt2 = re.sub(
    rf"(\n{re.escape(b)}res\s*=\s*agent_execute_step\([^\n]*\)\s*\n)",
    r"\1" + f"{b}# reload per-room plan after execute_step\n{b}plan = _load_room_plan(room_id) or plan\n",
    txt2
)

# After agent_evaluate(...) calls, reload plan
txt2 = re.sub(
    rf"(\n{re.escape(b)}agent_evaluate\([^\n]*\)\s*\n)",
    r"\1" + f"{b}# reload per-room plan after evaluate\n{b}plan = _load_room_plan(room_id) or plan\n",
    txt2
)

p.write_text(txt2, encoding="utf-8")
print("OK: run_once now reloads per-room plan from disk after execute/evaluate and uses it for responses")
