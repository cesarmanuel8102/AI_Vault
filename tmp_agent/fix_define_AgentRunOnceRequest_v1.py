from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# If already defined, do nothing
if re.search(r"^\s*class\s+AgentRunOnceRequest\s*\(", txt, flags=re.MULTILINE):
    print("SKIP: AgentRunOnceRequest already defined")
    raise SystemExit(0)

# Anchor: run_once endpoint decorator
m = re.search(r"^@app\.post\(\"/v1/agent/run_once\"[^\n]*\)\s*\n", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro el decorator @app.post(\"/v1/agent/run_once\" ...) para anclar la inserción.")

insert_at = m.start()

block = r'''
# === FIX_DEFINE_AGENTRUNONCEREQUEST_V1 BEGIN ===
class AgentRunOnceRequest(BaseModel):
    """
    Request for /v1/agent/run_once.
    approve_token: token to apply a pending gated write step (APPLY_<proposal_id>).
    room_id: optional; header x-room-id preferred.
    """
    approve_token: Optional[str] = None
    room_id: Optional[str] = None
# === FIX_DEFINE_AGENTRUNONCEREQUEST_V1 END ===

'''.lstrip("\n")

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: inserted AgentRunOnceRequest before /v1/agent/run_once")
