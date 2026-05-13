from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Insert after the END marker of RUN_ONCE ROOM LOAD (FIX)
marker = "# === RUN_ONCE ROOM LOAD (FIX) END ==="
idx = txt.find(marker)
if idx < 0:
    raise SystemExit("No encuentro marker RUN_ONCE ROOM LOAD (FIX) END")

# Find line end after marker
lines = txt.splitlines(True)
out = []
inserted = False
for ln in lines:
    out.append(ln)
    if (not inserted) and (marker in ln):
        # add setdefault right after marker
        indent = re.match(r"(\s*)", ln).group(1)
        body = indent  # same indent level as marker (inside def)
        out.append(f"{body}# Ensure plan carries room_id for auditing\n")
        out.append(f"{body}try:\n")
        out.append(f"{body}    if isinstance(plan, dict):\n")
        out.append(f"{body}        plan.setdefault('room_id', room_id)\n")
        out.append(f"{body}except Exception:\n")
        out.append(f"{body}    pass\n")
        inserted = True

Path(SERVER).write_text("".join(out), encoding="utf-8")
print("OK: added plan.setdefault(room_id) after run_once room load block")
