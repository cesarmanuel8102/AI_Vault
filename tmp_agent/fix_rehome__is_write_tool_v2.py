from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# 1) Remove bad injected block if present
b0 = txt.find("# === FIX_DEFINE__IS_WRITE_TOOL_V1 BEGIN ===")
b1 = txt.find("# === FIX_DEFINE__IS_WRITE_TOOL_V1 END ===")
if b0 >= 0 and b1 > b0:
    b1 = b1 + len("# === FIX_DEFINE__IS_WRITE_TOOL_V1 END ===")
    # remove trailing newline(s)
    tail = txt[b1:]
    if tail.startswith("\r\n"):
        b1 += 2
    elif tail.startswith("\n"):
        b1 += 1
    txt = txt[:b0] + txt[b1:]
    removed = True
else:
    removed = False

# 2) If already defined somewhere else, we are done
if re.search(r"^\s*def\s+_is_write_tool\s*\(", txt, flags=re.MULTILINE):
    p.write_text(txt, encoding="utf-8")
    print(f"OK: removed_bad={removed}; _is_write_tool already present elsewhere")
    raise SystemExit(0)

# 3) Insert in a safe top-level location: right before 'app = FastAPI'
m = re.search(r"^app\s*=\s*FastAPI\s*\(", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro 'app = FastAPI(' para anclar inserción segura de _is_write_tool.")

insert_at = m.start()

block = r'''
# === FIX_DEFINE__IS_WRITE_TOOL_V2 BEGIN ===
def _is_write_tool(tool_name: str) -> bool:
    try:
        t = (tool_name or "").strip()
    except Exception:
        t = ""
    return t in ("write_file", "append_file")
# === FIX_DEFINE__IS_WRITE_TOOL_V2 END ===

'''.lstrip("\n")

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print(f"OK: removed_bad={removed}; inserted _is_write_tool at top-level before app=FastAPI")
