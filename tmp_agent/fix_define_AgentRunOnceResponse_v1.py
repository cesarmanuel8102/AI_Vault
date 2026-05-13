from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# If already defined, do nothing
if re.search(r"^\s*class\s+AgentRunOnceResponse\s*\(", txt, flags=re.MULTILINE):
    print("SKIP: AgentRunOnceResponse already defined")
    raise SystemExit(0)

# Find the run_once endpoint decorator
m = re.search(r"^@app\.post\(\"/v1/agent/run_once\"[^\n]*\)\s*\n", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro el decorator @app.post(\"/v1/agent/run_once\" ...) para anclar la inserción.")

insert_at = m.start()

block = r'''
# === FIX_DEFINE_AGENTRUNONCERESPONSE_V1 BEGIN ===
class AgentRunOnceResponse(BaseModel):
    """
    Response envelope for /v1/agent/run_once.
    Keep it permissive: different internal branches may return different fields.
    """
    ok: bool = True
    action: str = ""
    step_id: str = ""
    room_id: str = ""
    error: str = ""
    result: Optional[Dict[str, Any]] = None
# === FIX_DEFINE_AGENTRUNONCERESPONSE_V1 END ===

'''.lstrip("\n")

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: inserted AgentRunOnceResponse before /v1/agent/run_once")
