import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

targets = [
    ("# === RUN_ONCE PERSIST APPLY DONE (FIX) BEGIN ===", "# === RUN_ONCE PERSIST APPLY DONE (FIX) END ==="),
    ("# === RUN_ONCE MARK READ DONE (FIX) BEGIN ===", "# === RUN_ONCE MARK READ DONE (FIX) END ==="),
    ("# === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) BEGIN ===", "# === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) END ==="),
]

def wrap_block(begin, end):
    # find block
    i0 = i1 = None
    for i, ln in enumerate(lines):
        if begin in ln:
            i0 = i
            break
    if i0 is None:
        return False
    for j in range(i0+1, len(lines)):
        if end in lines[j]:
            i1 = j
            break
    if i1 is None:
        raise SystemExit(f"Encontré BEGIN pero no END: {begin}")

    # Already wrapped?
    if i0 > 0 and "if False:" in lines[i0-1]:
        return True

    indent = re.match(r"(\s*)", lines[i0]).group(1)
    wrapped = []
    wrapped.append(indent + "if False:\n")
    # indent inner by +4 spaces
    inner = indent + "    "
    for k in range(i0, i1+1):
        wrapped.append(inner + lines[k].lstrip("\n"))  # preserve content, shift indent
    # replace in place
    lines[i0:i1+1] = wrapped
    return True

changed = 0
for b,e in targets:
    if wrap_block(b,e):
        changed += 1

p.write_text("".join(lines), encoding="utf-8")
print(f"OK: disabled {changed} run_once persistence blocks (if False)")
