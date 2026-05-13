import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Reemplaza cualquier línea "path": ...mission_log.txt
# por un Path join estable.
pat = r'("path"\s*:\s*)([^,\n]*mission_log\.txt[^,\n]*)(,)'
m = re.search(pat, txt)
if not m:
    raise SystemExit("No encontré el campo path de mission_log.txt en el planner.")

replacement = r'\1str(Path(r"C:\AI_VAULT\tmp_agent\runs") / str(room_id) / "mission_log.txt")\3'
txt2 = re.sub(pat, replacement, txt, count=1)

p.write_text(txt2, encoding="utf-8")
print("OK: planner mission_log path ahora usa Path(...) (sin \\t / escapes).")
