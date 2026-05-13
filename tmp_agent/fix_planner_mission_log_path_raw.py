import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Reemplaza el valor del "path": ... mission_log.txt ... (solo la primera ocurrencia)
pat = r'("path"\s*:\s*)(.+?mission_log\.txt.+?)(,)'

m = re.search(pat, txt)
if not m:
    raise SystemExit("No encontré 'path' de mission_log.txt para reemplazar.")

prefix = m.group(1)
suffix = m.group(3)

# OJO: esto es CÓDIGO PY dentro del brain_server, no JSON.
new_expr = r'r"C:\\AI_VAULT\\tmp_agent\\runs\\" + str(room_id) + r"\\mission_log.txt"'

txt2 = txt[:m.start()] + prefix + new_expr + suffix + txt[m.end():]
p.write_text(txt2, encoding="utf-8")
print("OK: mission_log path fixed (raw strings, no \\t).")
