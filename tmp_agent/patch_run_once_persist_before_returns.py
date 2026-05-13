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
    raise SystemExit("No encuentro def agent_run_once(...)")

def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
body_indent = def_indent + "    "

# end at next decorator
i_end = None
for j in range(i_def+1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]
chunk_txt = "".join(chunk)
MARK = "RUN_ONCE ROOM PERSIST BEFORE RETURN (FIX)"
if MARK in chunk_txt:
    print("SKIP: ya existe persist-before-return en run_once")
    raise SystemExit(0)

block = [
    f"{body_indent}# === {MARK} BEGIN ===\n",
    f"{body_indent}try:\n",
    f"{body_indent}    _room_state_dir(room_id)\n",
    f"{body_indent}    paths = _room_paths(room_id) or {{}}\n",
    f"{body_indent}    import json\n",
    f"{body_indent}    from pathlib import Path\n",
    f"{body_indent}    from datetime import datetime, timezone\n",
    f"{body_indent}    now = datetime.now(timezone.utc).isoformat()\n",
    f"{body_indent}    try:\n",
    f"{body_indent}        if isinstance(plan, dict):\n",
    f"{body_indent}            plan['updated_at'] = now\n",
    f"{body_indent}            plan.setdefault('room_id', room_id)\n",
    f"{body_indent}    except Exception:\n",
    f"{body_indent}        pass\n",
    f"{body_indent}    try:\n",
    f"{body_indent}        if isinstance(mission, dict):\n",
    f"{body_indent}            mission['updated_at'] = now\n",
    f"{body_indent}            mission.setdefault('room_id', room_id)\n",
    f"{body_indent}    except Exception:\n",
    f"{body_indent}        pass\n",
    f"{body_indent}    pm = paths.get('mission')\n",
    f"{body_indent}    pp = paths.get('plan')\n",
    f"{body_indent}    if pm:\n",
    f"{body_indent}        Path(pm).write_text(json.dumps(mission or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n",
    f"{body_indent}    if pp:\n",
    f"{body_indent}        Path(pp).write_text(json.dumps(plan or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n",
    f"{body_indent}except Exception:\n",
    f"{body_indent}    pass\n",
    f"{body_indent}# === {MARK} END ===\n",
]

new_chunk = []
inserted = 0

for ln in chunk:
    # if this is a return dict at base indent, insert block right before it
    if re.match(rf"{re.escape(body_indent)}return\s+\{{", ln):
        new_chunk.extend(block)
        inserted += 1
    new_chunk.append(ln)

if inserted == 0:
    raise SystemExit("No encontré 'return {' en agent_run_once; abortando.")
print(f"OK: insertado persist-before-return en {inserted} returns dentro de run_once")

new_lines = lines[:i_def] + new_chunk + lines[i_end:]
p.write_text("".join(new_lines), encoding="utf-8")
