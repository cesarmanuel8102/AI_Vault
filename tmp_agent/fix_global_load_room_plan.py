import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# If already defined globally (no indent), skip
for ln in lines:
    if re.match(r"^def\s+_load_room_plan\s*\(", ln):
        print("SKIP: global def _load_room_plan already exists")
        raise SystemExit(0)

# Find insertion point right after def _room_paths(...) block
i_room_paths = None
for i, ln in enumerate(lines):
    if re.match(r"^def\s+_room_paths\s*\(", ln):
        i_room_paths = i
        break
if i_room_paths is None:
    raise SystemExit("No encuentro def _room_paths(...).")

# Find next top-level def after _room_paths to insert before it
i_next = None
for j in range(i_room_paths+1, len(lines)):
    if re.match(r"^def\s+", lines[j]) and (j > i_room_paths):
        i_next = j
        break
if i_next is None:
    i_next = len(lines)

block = []
block.append("\n")
block.append("# === GLOBAL ROOM PLAN LOADER (FIX) BEGIN ===\n")
block.append("def _load_room_plan(room_id: str) -> dict:\n")
block.append("    \"\"\"Load per-room plan.json from rooms/<room_id>/...; returns {} if missing.\"\"\"\n")
block.append("    try:\n")
block.append("        _room_state_dir(room_id)\n")
block.append("        paths = _room_paths(room_id) or {}\n")
block.append("        import json\n")
block.append("        from pathlib import Path\n")
block.append("        pp = paths.get('plan')\n")
block.append("        if pp and Path(pp).exists():\n")
block.append("            return json.loads(Path(pp).read_text(encoding='utf-8')) or {}\n")
block.append("    except Exception:\n")
block.append("        return {}\n")
block.append("    return {}\n")
block.append("# === GLOBAL ROOM PLAN LOADER (FIX) END ===\n")

new_lines = lines[:i_next] + block + lines[i_next:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted global _load_room_plan before line {i_next+1}")
