import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Remove the injected lines (marker + the 2 lines) regardless of indentation.
# We remove:
#   # SNAPSHOT_SET_PROPOSE_DONE: ...
#   if tool_name_step == 'runtime_snapshot_set':
#       target['status'] = 'done'
pat = r"\n[ \t]*# SNAPSHOT_SET_PROPOSE_DONE:.*\n[ \t]*if tool_name_step == 'runtime_snapshot_set':\n[ \t]*target\['status'\] = 'done'\n"

txt2, n = re.subn(pat, "\n", txt, count=1, flags=re.MULTILINE)
if n == 0:
    raise SystemExit("No encontré la inyección SNAPSHOT_SET_PROPOSE_DONE para remover (pattern mismatch).")

p.write_text(txt2, encoding="utf-8")
print("OK: removida inyección SNAPSHOT_SET_PROPOSE_DONE (evita IndentationError).")
