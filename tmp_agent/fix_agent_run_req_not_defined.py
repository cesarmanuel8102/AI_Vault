import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Ensure we are patching the v6.2 block we inserted
if "v6.2: run loop MUST respect per-room plan.json" not in txt:
    raise SystemExit("No encuentro el bloque v6.2 en agent_run; abortando para no tocar lo incorrecto.")

# Replace the fragile lines that reference req directly.
# We replace:
#   room_id = getattr(req, 'room_id', None) or hdr_room or "default"
#   max_steps = int(getattr(req, 'max_steps', 10) or 10)
# with a robust local resolver.

pattern_room = r"\n\s*room_id\s*=\s*getattr\(req,\s*'room_id',\s*None\)\s*or\s*hdr_room\s*or\s*\"default\"\s*\n"
pattern_max  = r"\n\s*max_steps\s*=\s*int\(getattr\(req,\s*'max_steps',\s*10\)\s*or\s*10\)\s*\n"

m1 = re.search(pattern_room, txt)
m2 = re.search(pattern_max, txt)

if not (m1 and m2):
    # fallback: search more loosely
    if "getattr(req, 'room_id'" not in txt or "getattr(req, 'max_steps'" not in txt:
        raise SystemExit("No encuentro las líneas con getattr(req, ...) para reemplazar.")

replacement = """
    # Resolve request model without assuming parameter name (req/payload/body/etc.)
    _req = None
    try:
        _req = req  # type: ignore[name-defined]
    except Exception:
        _req = None
    if _req is None:
        for _k in ("payload","body","data","r","request_body","model"):
            try:
                if _k in locals() and locals().get(_k) is not None:
                    _req = locals().get(_k)
                    break
            except Exception:
                pass

    room_id = getattr(_req, "room_id", None) or hdr_room or "default"
    max_steps = int(getattr(_req, "max_steps", 10) or 10)
"""

# Do actual replacements (once each)
txt = re.sub(pattern_room, "\n" + replacement + "\n", txt, count=1)
txt = re.sub(pattern_max, "\n", txt, count=1)  # max_steps now included in replacement

p.write_text(txt, encoding="utf-8")
print("OK: agent_run ahora no depende de 'req' (resolver robusto por locals())")
