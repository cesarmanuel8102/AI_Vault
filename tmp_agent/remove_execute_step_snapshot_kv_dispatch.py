from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 BEGIN ==="
END   = "# === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 < i0:
    raise SystemExit("No encuentro BEGIN/END de EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1")

i1 = i1 + len(END)
tail = txt[i1:]
if tail.startswith("\r\n"):
    i1 += 2
elif tail.startswith("\n"):
    i1 += 1

p.write_text(txt[:i0] + txt[i1:], encoding="utf-8")
print("OK: removed EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 block")
