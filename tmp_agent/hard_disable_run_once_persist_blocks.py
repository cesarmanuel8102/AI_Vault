from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

blocks = [
    ("# === RUN_ONCE PERSIST APPLY DONE (FIX) BEGIN ===", "# === RUN_ONCE PERSIST APPLY DONE (FIX) END ==="),
    ("# === RUN_ONCE MARK READ DONE (FIX) BEGIN ===", "# === RUN_ONCE MARK READ DONE (FIX) END ==="),
    ("# === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) BEGIN ===", "# === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) END ==="),
]

lines = txt.splitlines(True)

def disable(begin, end):
    i0=i1=None
    for i,ln in enumerate(lines):
        if begin in ln:
            i0=i; break
    if i0 is None: return False
    for j in range(i0+1,len(lines)):
        if end in lines[j]:
            i1=j; break
    if i1 is None: raise SystemExit(f"BEGIN sin END: {begin}")
    # si ya está bajo if False:, no tocar
    if i0>0 and "if False:" in lines[i0-1]:
        return True
    indent = re.match(r"(\s*)", lines[i0]).group(1)
    wrapped=[indent+"if False:\n"]
    inner=indent+"    "
    for k in range(i0,i1+1):
        wrapped.append(inner+lines[k])
    lines[i0:i1+1]=wrapped
    return True

changed=0
for b,e in blocks:
    if disable(b,e):
        changed += 1

Path(SERVER).write_text("".join(lines), encoding="utf-8")
print(f"OK: run_once persist blocks hard-disabled (found={changed})")
