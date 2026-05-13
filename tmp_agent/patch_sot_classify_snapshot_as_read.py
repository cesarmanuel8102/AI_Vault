import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === EXECUTE_STEP PERSIST PLAN (FIX) BEGIN ==="
if BEGIN not in txt:
    raise SystemExit("No encuentro bloque SOT EXECUTE_STEP PERSIST PLAN (FIX).")

# Replace is_read/is_write within SOT block (first occurrence)
txt2, n1 = re.subn(
    r"is_read\s*=\s*tool_name_step\s+in\s*\([^)]+\)\n",
    "is_read = tool_name_step in ('list_dir','read_file','runtime_snapshot_set','runtime_snapshot_get')\n",
    txt,
    count=1
)
txt2, n2 = re.subn(
    r"is_write\s*=\s*tool_name_step\s+in\s*\([^)]+\)\n",
    "is_write = tool_name_step in ('write_file','append_file')\n",
    txt2,
    count=1
)

if n1 == 0 or n2 == 0:
    raise SystemExit("No pude reemplazar is_read/is_write (pattern mismatch).")

p.write_text(txt2, encoding="utf-8")
print("OK: SOT classify snapshot_set/get as read-like; only write_file/append_file are gated writes.")
