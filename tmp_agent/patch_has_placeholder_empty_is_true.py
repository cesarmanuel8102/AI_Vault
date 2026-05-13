import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# locate def _has_placeholder
i = None
for idx, ln in enumerate(lines):
    if re.match(r"\s*def\s+_has_placeholder\s*\(", ln):
        i = idx
        break
if i is None:
    raise SystemExit("No encuentro def _has_placeholder")

# find return line inside it
j = None
for k in range(i, i+60):
    if k >= len(lines): break
    if "return" in lines[k] and "PLANNER_PLACEHOLDER" in lines[k]:
        j = k
        break
if j is None:
    raise SystemExit("No encuentro return con PLANNER_PLACEHOLDER dentro de _has_placeholder")

indent = re.match(r"(\s*)", lines[j]).group(1)
lines[j] = indent + "return ('PLANNER_PLACEHOLDER' in content) or (content.strip() == '')\n"

p.write_text("".join(lines), encoding="utf-8")
print("OK: _has_placeholder ahora también dispara si content está vacío.")
