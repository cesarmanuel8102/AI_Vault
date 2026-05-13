import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# locate agent_execute_step
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_execute_step\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute_step(...)")

def_indent = re.match(r"(\s*)def\s+agent_execute_step", lines[i_def]).group(1)
b = def_indent + "    "

# end at next decorator at same indent
i_end = None
for j in range(i_def+1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]
chunk_txt = "".join(chunk)

MARK = "EXECUTE_STEP PERSIST PLAN (FIX)"
if MARK in chunk_txt:
    print("SKIP: ya existe EXECUTE_STEP persist")
    raise SystemExit(0)

# insert before every "return {" at base body indent inside execute_step
block = []
block.append(f"{b}# === {MARK} BEGIN ===\n")
block.append(f"{b}# Single Source of Truth: persist plan step state here (per-room plan.json)\n")
block.append(f"{b}try:\n")
block.append(f"{b}    rid = None\n")
block.append(f"{b}    try:\n")
block.append(f"{b}        rid = getattr(req, 'room_id', None)\n")
block.append(f"{b}    except Exception:\n")
block.append(f"{b}        rid = None\n")
block.append(f"{b}    room_id = rid or 'default'\n")
block.append(f"{b}\n")
block.append(f"{b}    step_id_local = None\n")
block.append(f"{b}    try:\n")
block.append(f"{b}        step_id_local = getattr(req, 'step_id', None)\n")
block.append(f"{b}    except Exception:\n")
block.append(f"{b}        step_id_local = None\n")
block.append(f"{b}    step_id_local = str(step_id_local or '')\n")
block.append(f"{b}\n")
block.append(f"{b}    mode_local = ''\n")
block.append(f"{b}    try:\n")
block.append(f"{b}        mode_local = str(getattr(req, 'mode', '') or '')\n")
block.append(f"{b}    except Exception:\n")
block.append(f"{b}        mode_local = ''\n")
block.append(f"{b}\n")
block.append(f"{b}    tool_name_local = ''\n")
block.append(f"{b}    try:\n")
block.append(f"{b}        tool_name_local = str((result or {{}}).get('tool_name') or (locals().get('tool_name') or ''))\n")
block.append(f"{b}    except Exception:\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            tool_name_local = str(locals().get('tool_name') or '')\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            tool_name_local = ''\n")
block.append(f"{b}\n")
block.append(f"{b}    def _load_plan_disk(_rid: str) -> dict:\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            _room_state_dir(_rid)\n")
block.append(f"{b}            _paths = _room_paths(_rid) or {{}}\n")
block.append(f"{b}            import json\n")
block.append(f"{b}            from pathlib import Path\n")
block.append(f"{b}            pp = _paths.get('plan')\n")
block.append(f"{b}            if pp and Path(pp).exists():\n")
block.append(f"{b}                return json.loads(Path(pp).read_text(encoding='utf-8')) or {{}}\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            return {{}}\n")
block.append(f"{b}        return {{}}\n")
block.append(f"{b}\n")
block.append(f"{b}    def _save_plan_disk(_rid: str, plan_disk: dict) -> None:\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            _room_state_dir(_rid)\n")
block.append(f"{b}            _paths = _room_paths(_rid) or {{}}\n")
block.append(f"{b}            import json\n")
block.append(f"{b}            from pathlib import Path\n")
block.append(f"{b}            pp = _paths.get('plan')\n")
block.append(f"{b}            if pp:\n")
block.append(f"{b}                Path(pp).write_text(json.dumps(plan_disk or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            pass\n")
block.append(f"{b}\n")
block.append(f"{b}    def _touch(plan_disk: dict) -> None:\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            from datetime import datetime, timezone\n")
block.append(f"{b}            plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            pass\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            plan_disk.setdefault('room_id', room_id)\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            pass\n")
block.append(f"{b}\n")
block.append(f"{b}    if room_id and step_id_local:\n")
block.append(f"{b}        plan_disk = _load_plan_disk(room_id) or {{}}\n")
block.append(f"{b}        steps_disk = plan_disk.get('steps', []) or []\n")
block.append(f"{b}        if isinstance(steps_disk, list):\n")
block.append(f"{b}            target = None\n")
block.append(f"{b}            for _s in steps_disk:\n")
block.append(f"{b}                if isinstance(_s, dict) and str(_s.get('id')) == step_id_local:\n")
block.append(f"{b}                    target = _s\n")
block.append(f"{b}                    break\n")
block.append(f"{b}\n")
block.append(f"{b}            is_read = tool_name_local in ('list_dir','read_file')\n")
block.append(f"{b}            is_write = tool_name_local in ('write_file','append_file')\n")
block.append(f"{b}\n")
block.append(f"{b}            # 1) read-only propose => done\n")
block.append(f"{b}            if target and is_read and mode_local == 'propose':\n")
block.append(f"{b}                target['status'] = 'done'\n")
block.append(f"{b}\n")
block.append(f"{b}            # 2) write propose => proposed + proposal_id\n")
block.append(f"{b}            if target and is_write and mode_local == 'propose':\n")
block.append(f"{b}                pid = None\n")
block.append(f"{b}                try:\n")
block.append(f"{b}                    pid = (result or {{}}).get('proposal_id')\n")
block.append(f"{b}                except Exception:\n")
block.append(f"{b}                    pid = None\n")
block.append(f"{b}                if pid:\n")
block.append(f"{b}                    target['status'] = 'proposed'\n")
block.append(f"{b}                    target['proposal_id'] = str(pid)\n")
block.append(f"{b}                    target['required_approve'] = 'APPLY_' + str(pid)\n")
block.append(f"{b}\n")
block.append(f"{b}            # 3) write apply => done + clear proposal fields\n")
block.append(f"{b}            if target and is_write and mode_local == 'apply':\n")
block.append(f"{b}                target['status'] = 'done'\n")
block.append(f"{b}                try:\n")
block.append(f"{b}                    target.pop('required_approve', None)\n")
block.append(f"{b}                    target.pop('proposal_id', None)\n")
block.append(f"{b}                except Exception:\n")
block.append(f"{b}                    pass\n")
block.append(f"{b}\n")
block.append(f"{b}            plan_disk['steps'] = steps_disk\n")
block.append(f"{b}\n")
block.append(f"{b}            # auto-complete if all done\n")
block.append(f"{b}            try:\n")
block.append(f"{b}                if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk if isinstance(x, dict)):\n")
block.append(f"{b}                    plan_disk['status'] = 'complete'\n")
block.append(f"{b}            except Exception:\n")
block.append(f"{b}                pass\n")
block.append(f"{b}\n")
block.append(f"{b}            _touch(plan_disk)\n")
block.append(f"{b}            _save_plan_disk(room_id, plan_disk)\n")
block.append(f"{b}except Exception:\n")
block.append(f"{b}    pass\n")
block.append(f"{b}# === {MARK} END ===\n")

new_chunk = []
inserted = 0
for ln in chunk:
    if re.match(rf"{re.escape(b)}return\s+\{{", ln):
        new_chunk.extend(block)
        inserted += 1
    new_chunk.append(ln)

if inserted == 0:
    raise SystemExit("No encontré 'return {' dentro de agent_execute_step para insertar persistencia.")

new_lines = lines[:i_def] + new_chunk + lines[i_end:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: execute_step persistence inserted before {inserted} returns")
