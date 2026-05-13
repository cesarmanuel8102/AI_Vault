import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === EXECUTE_STEP PERSIST PLAN (FIX) BEGIN ==="
if BEGIN not in txt:
    raise SystemExit("No encuentro el bloque EXECUTE_STEP PERSIST PLAN (FIX).")

# Reemplaza is_read/is_write lines dentro del bloque (una vez)
txt2, n1 = re.subn(
    r"is_read\s*=\s*tool_name_step\s+in\s*\([^)]+\)\n",
    "is_read = tool_name_step in ('list_dir','read_file','runtime_snapshot_get')\n",
    txt,
    count=1
)
txt2, n2 = re.subn(
    r"is_write\s*=\s*tool_name_step\s+in\s*\([^)]+\)\n",
    "is_write = tool_name_step in ('write_file','append_file','runtime_snapshot_set')\n",
    txt2,
    count=1
)

if n1 == 0 or n2 == 0:
    raise SystemExit("No pude reemplazar is_read/is_write dentro del bloque SOT; revisa formato del bloque.")

# Ajuste especial: runtime_snapshot_set en propose debe quedar done (no proposed)
# Insertamos lógica después del write-propose
needle = "if target and is_write and mode_local == 'propose':"
if needle not in txt2:
    raise SystemExit("No encuentro el if de write-propose en SOT; abortando.")

# Insert only once
if "SNAPSHOT_SET_PROPOSE_DONE" not in txt2:
    txt2 = txt2.replace(
        needle,
        needle + "\n                # SNAPSHOT_SET_PROPOSE_DONE: snapshot_set no requiere approval\n                if tool_name_step == 'runtime_snapshot_set':\n                    target['status'] = 'done'\n"
    )

p.write_text(txt2, encoding="utf-8")
print("OK: SOT execute_step clasifica runtime_snapshot_set/get y snapshot_set queda done en propose.")
