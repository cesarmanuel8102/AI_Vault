from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "FIX_DEFINE__HAS_PLACEHOLDER_V1"
if MARK in txt:
    print("SKIP: _has_placeholder already patched")
    raise SystemExit(0)

# If already defined anywhere, just add marker and exit
if re.search(r"^\s*def\s+_has_placeholder\s*\(", txt, flags=re.MULTILINE):
    # add a marker near the definition if not present (best-effort)
    txt2 = txt.replace("def _has_placeholder", f"# {MARK}\ndef _has_placeholder", 1)
    p.write_text(txt2, encoding="utf-8")
    print("OK: _has_placeholder already existed; marker added")
    raise SystemExit(0)

# Anchor safe insertion: right before app = FastAPI(
m = re.search(r"^app\s*=\s*FastAPI\s*\(", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro 'app = FastAPI(' para anclar inserción de _has_placeholder.")

insert_at = m.start()

block = r'''
# === FIX_DEFINE__HAS_PLACEHOLDER_V1 BEGIN ===
def _has_placeholder(obj) -> bool:
    """
    Returns True if obj contains placeholder markers that indicate the planner
    hasn't produced real content yet (safety/quality guard).
    """
    try:
        PH = ("PLANNER_PLACEHOLDER", "PLACEHOLDER", "TODO_PLACEHOLDER")
        def _scan(x):
            if x is None:
                return False
            if isinstance(x, str):
                u = x.upper()
                return any(p in u for p in PH)
            if isinstance(x, dict):
                for k, v in x.items():
                    if _scan(k) or _scan(v):
                        return True
                return False
            if isinstance(x, (list, tuple, set)):
                for it in x:
                    if _scan(it):
                        return True
                return False
            return False
        return _scan(obj)
    except Exception:
        return False
# === FIX_DEFINE__HAS_PLACEHOLDER_V1 END ===

'''.lstrip("\n")

txt2 = txt[:insert_at] + block + txt[insert_at:]
# add marker for idempotency
txt2 = txt2.replace("# === FIX_DEFINE__HAS_PLACEHOLDER_V1 BEGIN ===", f"# {MARK}\n# === FIX_DEFINE__HAS_PLACEHOLDER_V1 BEGIN ===", 1)

p.write_text(txt2, encoding="utf-8")
print("OK: inserted _has_placeholder() at top-level before app=FastAPI")
