import re
from pathlib import Path
from datetime import datetime, timezone
import json

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"

BEGIN = "# === AGENT_PLAN ROOM SAVE (FIX) BEGIN ==="
END   = "# === AGENT_PLAN ROOM SAVE (FIX) END ==="

p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

lines = txt.splitlines(True)  # keepends
i_begin = None
i_end = None

for i, ln in enumerate(lines):
    if BEGIN in ln:
        i_begin = i
        break
if i_begin is None:
    raise SystemExit(f"No encuentro marker BEGIN: {BEGIN}")

for j in range(i_begin + 1, len(lines)):
    if END in lines[j]:
        i_end = j
        break
if i_end is None:
    raise SystemExit(f"No encuentro marker END: {END}")

indent = re.match(r"[ \t]*", lines[i_begin]).group(0)

# Bloque reemplazo con markers AL MISMO INDENT que el marker original
block = []
block.append(f"{indent}{BEGIN}\n")
block.append(f"{indent}# Persist mission/plan to rooms/<room_id>/... (NO-OP si no hay room_id)\n")
block.append(f"{indent}try:\n")
block.append(f"{indent}    if 'room_id' in locals() and room_id:\n")
block.append(f"{indent}        _room_state_dir(room_id)\n")
block.append(f"{indent}        paths = _room_paths(room_id) or {{}}\n")
block.append(f"{indent}        from pathlib import Path\n")
block.append(f"{indent}        from datetime import datetime, timezone\n")
block.append(f"{indent}        import json\n")
block.append(f"{indent}        now = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{indent}        try:\n")
block.append(f"{indent}            if isinstance(plan, dict):\n")
block.append(f"{indent}                plan['updated_at'] = now\n")
block.append(f"{indent}        except Exception:\n")
block.append(f"{indent}            pass\n")
block.append(f"{indent}        try:\n")
block.append(f"{indent}            if isinstance(mission, dict):\n")
block.append(f"{indent}                mission['updated_at'] = now\n")
block.append(f"{indent}        except Exception:\n")
block.append(f"{indent}            pass\n")
block.append(f"{indent}        pm = paths.get('mission')\n")
block.append(f"{indent}        pp = paths.get('plan')\n")
block.append(f"{indent}        if pm:\n")
block.append(f"{indent}            Path(pm).write_text(json.dumps(mission or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{indent}        if pp:\n")
block.append(f"{indent}            Path(pp).write_text(json.dumps(plan or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{indent}except Exception:\n")
block.append(f"{indent}    pass\n")
block.append(f"{indent}{END}\n")

new_lines = lines[:i_begin] + block + lines[i_end+1:]
p.write_text("".join(new_lines), encoding="utf-8")

print("OK: bloque AGENT_PLAN ROOM SAVE (FIX) reemplazado con indent consistente")
print(f"BEGIN line: {i_begin+1}, END line: {i_end+1}, indent repr: {indent!r}")
