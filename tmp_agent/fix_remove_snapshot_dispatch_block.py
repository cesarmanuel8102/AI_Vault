from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) BEGIN ==="
END   = "# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)

if i0 < 0 or i1 < 0 or i1 < i0:
    print("SKIP: no encontré el bloque DISPATCH (no hay nada que remover).")
    raise SystemExit(0)

# remove inclusive of END line
i1 = i1 + len(END)
# also remove trailing newline(s) after END if present
tail = txt[i1:]
if tail.startswith("\r\n"):
    i1 += 2
elif tail.startswith("\n"):
    i1 += 1

txt2 = txt[:i0] + txt[i1:]
p.write_text(txt2, encoding="utf-8")
print("OK: removido bloque EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX).")
