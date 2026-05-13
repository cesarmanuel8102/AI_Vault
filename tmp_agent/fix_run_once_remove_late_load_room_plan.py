import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# find agent_run_once
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_run_once\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_run_once")

def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
b = def_indent + "    "

# find all occurrences of def _load_room_plan at body indent
defs = [i for i, ln in enumerate(lines) if re.match(rf"{re.escape(b)}def\s+_load_room_plan\s*\(", ln)]
if len(defs) < 2:
    print("SKIP: no hay definición tardía duplicada para remover (defs<2)")
    raise SystemExit(0)

# keep the first (early), remove the second
late = defs[1]

# remove until next line with indent == b and starts with 'def ' or 'if ' or 'mission,' etc? safest: remove until blank line after function ends.
# Function ends when indentation returns to b and line starts not with whitespace deeper than b (i.e., exactly b + something not starting with space)
end = None
for j in range(late+1, len(lines)):
    # stop when line starts with body indent and NOT with additional indentation (i.e., same level)
    if lines[j].startswith(b) and (not lines[j].startswith(b + "    ")):
        end = j
        break
if end is None:
    end = len(lines)

new_lines = lines[:late] + lines[end:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: removed late _load_room_plan block lines {late+1}-{end}")
