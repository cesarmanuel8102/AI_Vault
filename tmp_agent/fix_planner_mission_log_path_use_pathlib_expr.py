from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# Find the FIRST planner step line that sets "path" and contains mission_log.txt
idx = None
for i, ln in enumerate(lines):
    if '"path"' in ln and 'mission_log.txt' in ln:
        idx = i
        break

if idx is None:
    raise SystemExit("No encontré la línea con \"path\" para mission_log.txt")

# Replace the entire line with a safe pathlib expression (no backslash escaping issues)
indent = re.match(r"(\s*)", lines[idx]).group(1)
lines[idx] = (
    indent
    + '"path": str((__import__("pathlib").Path(r"C:\\\\AI_VAULT\\\\tmp_agent\\\\runs") / str(room_id) / "mission_log.txt")),\n'
)

p.write_text("".join(lines), encoding="utf-8")
print("OK: mission_log path fixed -> pathlib expression (safe).")
