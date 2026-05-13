import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Fix: replace the broken multiline f-string content for MISSION START with a safe literal
# Target line pattern: "content": f"MISSION START ... (unterminated)
pat = r'("content"\s*:\s*)f"MISSION START[\s\S]*?"\s*,'
m = re.search(pat, txt)
if not m:
    # looser: find the "content": f"MISSION START then replace up to next comma on same/next lines
    pat2 = r'("content"\s*:\s*)f"MISSION START[\s\S]*?\n\s*"\s*,'
    m2 = re.search(pat2, txt)
    if not m2:
        raise SystemExit("No encontré el bloque roto de content=f\"MISSION START...\" para reparar.")
    pat = pat2

replacement = r'\1"MISSION START\\n",'
txt2, n = re.subn(pat, replacement, txt, count=1)
if n == 0:
    raise SystemExit("No se aplicó el reemplazo (pattern mismatch).")

p.write_text(txt2, encoding="utf-8")
print("OK: fixed unterminated MISSION START string (now uses \"MISSION START\\\\n\")")
