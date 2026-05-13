import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

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

# locate the propose execute line: res = agent_execute_step(... mode="propose")
i_exec = None
for i in range(i_def, min(len(lines), i_def+500)):
    if re.search(r"res\s*=\s*agent_execute_step\(.+mode\s*=\s*\"propose\"", lines[i]):
        i_exec = i
        break
if i_exec is None:
    # fallback: any res = agent_execute_step(... mode="propose")
    for i in range(i_def, min(len(lines), i_def+500)):
        if "res = agent_execute_step" in lines[i] and "mode=\"propose\"" in lines[i].replace(" ", ""):
            i_exec = i
            break
if i_exec is None:
    raise SystemExit("No encuentro la línea res = agent_execute_step(... mode='propose') en run_once")

MARK = "RUN_ONCE MARK READ DONE (FIX)"
if any(MARK in ln for ln in lines[i_def:i_def+700]):
    print("SKIP: ya existe MARK READ DONE")
    raise SystemExit(0)

block = []
block.append(f"{b}# === {MARK} BEGIN ===\n")
block.append(f"{b}# For read-only steps, persist status=done into per-room plan.json\n")
block.append(f"{b}if _is_read_tool(tool_name):\n")
block.append(f"{b}    try:\n")
block.append(f"{b}        plan_disk = _load_room_plan(room_id) or {{}}\n")
block.append(f"{b}        steps_disk = plan_disk.get('steps', []) or []\n")
block.append(f"{b}        for _s in steps_disk:\n")
block.append(f"{b}            if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):\n")
block.append(f"{b}                _s['status'] = 'done'\n")
block.append(f"{b}                break\n")
block.append(f"{b}        plan_disk['steps'] = steps_disk\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            from datetime import datetime, timezone\n")
block.append(f"{b}            plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            pass\n")
block.append(f"{b}        plan_disk.setdefault('room_id', room_id)\n")
block.append(f"{b}        _room_state_dir(room_id)\n")
block.append(f"{b}        _paths = _room_paths(room_id) or {{}}\n")
block.append(f"{b}        import json\n")
block.append(f"{b}        from pathlib import Path\n")
block.append(f"{b}        pp = _paths.get('plan')\n")
block.append(f"{b}        if pp:\n")
block.append(f"{b}            Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{b}        plan = plan_disk\n")
block.append(f"{b}        steps = plan.get('steps', []) or []\n")
block.append(f"{b}    except Exception:\n")
block.append(f"{b}        pass\n")
block.append(f"{b}# === {MARK} END ===\n")

# Insert right AFTER the res = agent_execute_step(...) propose line
new_lines = []
new_lines.extend(lines[:i_exec+1])
new_lines.extend(block)
new_lines.extend(lines[i_exec+1:])

p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted read-only done persistence after execute_step propose at line {i_exec+1}")
