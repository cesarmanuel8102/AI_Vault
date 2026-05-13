import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "RUN_ONCE PERSIST APPLY DONE (FIX)"
if MARK in txt:
    print("SKIP: ya existe persist apply done")
    raise SystemExit(0)

lines = txt.splitlines(True)

# Encontrar la línea del approve_token apply: res = agent_execute_step(... mode="apply" ...)
i_apply = None
for i, ln in enumerate(lines):
    if "mode=\"apply\"" in ln.replace(" ", "") and "agent_execute_step" in ln:
        i_apply = i
        break
if i_apply is None:
    raise SystemExit("No encuentro llamada agent_execute_step(... mode='apply' ...)")

indent = re.match(r"(\s*)", lines[i_apply]).group(1)

block = []
block.append(f"{indent}# === {MARK} BEGIN ===\n")
block.append(f"{indent}# Persist step status=done in per-room plan.json after apply\n")
block.append(f"{indent}try:\n")
block.append(f"{indent}    plan_disk = _load_room_plan(room_id) or {{}}\n")
block.append(f"{indent}    steps_disk = plan_disk.get('steps', []) or []\n")
block.append(f"{indent}    for _s in steps_disk:\n")
block.append(f"{indent}        if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):\n")
block.append(f"{indent}            _s['status'] = 'done'\n")
block.append(f"{indent}            # limpiar campos de propuesta\n")
block.append(f"{indent}            try:\n")
block.append(f"{indent}                _s.pop('required_approve', None)\n")
block.append(f"{indent}                _s.pop('proposal_id', None)\n")
block.append(f"{indent}            except Exception:\n")
block.append(f"{indent}                pass\n")
block.append(f"{indent}            break\n")
block.append(f"{indent}    plan_disk['steps'] = steps_disk\n")
block.append(f"{indent}    # auto-complete si todos done\n")
block.append(f"{indent}    try:\n")
block.append(f"{indent}        if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk):\n")
block.append(f"{indent}            plan_disk['status'] = 'complete'\n")
block.append(f"{indent}    except Exception:\n")
block.append(f"{indent}        pass\n")
block.append(f"{indent}    from datetime import datetime, timezone\n")
block.append(f"{indent}    plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{indent}    plan_disk.setdefault('room_id', room_id)\n")
block.append(f"{indent}    _room_state_dir(room_id)\n")
block.append(f"{indent}    _paths = _room_paths(room_id) or {{}}\n")
block.append(f"{indent}    import json\n")
block.append(f"{indent}    from pathlib import Path\n")
block.append(f"{indent}    pp = _paths.get('plan')\n")
block.append(f"{indent}    if pp:\n")
block.append(f"{indent}        Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{indent}except Exception:\n")
block.append(f"{indent}    pass\n")
block.append(f"{indent}# === {MARK} END ===\n")

# Insertar justo después de la línea apply execute_step
new_lines = lines[:i_apply+1] + block + lines[i_apply+1:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted persist-apply-done block after line {i_apply+1}")
