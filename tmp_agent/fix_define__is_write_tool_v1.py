from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# If already defined, skip
if re.search(r"^\s*def\s+_is_write_tool\s*\(", txt, flags=re.MULTILINE):
    print("SKIP: _is_write_tool already defined")
    raise SystemExit(0)

m = re.search(r"_is_write_tool\s*\(", txt)
if not m:
    raise SystemExit("No encuentro uso de _is_write_tool( para anclar inserción.")

insert_at = m.start()

block = r'''
# === FIX_DEFINE__IS_WRITE_TOOL_V1 BEGIN ===
def _is_write_tool(tool_name: str) -> bool:
    try:
        t = (tool_name or "").strip()
    except Exception:
        t = ""
    return t in ("write_file", "append_file")
# === FIX_DEFINE__IS_WRITE_TOOL_V1 END ===

'''.lstrip("\n")

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: inserted _is_write_tool() before first usage.")
