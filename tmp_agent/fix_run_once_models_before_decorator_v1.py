from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Find the run_once decorator
m = re.search(r'^@app\.post\("/v1/agent/run_once"[^\n]*\)\s*\n', txt, flags=re.MULTILINE)
if not m:
    raise SystemExit('No encuentro el decorator @app.post("/v1/agent/run_once"...).')

insert_at = m.start()

need_req = not re.search(r'^\s*class\s+AgentRunOnceRequest\s*\(', txt, flags=re.MULTILINE)
need_res = not re.search(r'^\s*class\s+AgentRunOnceResponse\s*\(', txt, flags=re.MULTILINE)

if not need_req and not need_res:
    print("SKIP: AgentRunOnceRequest/Response ya existen")
    raise SystemExit(0)

block = []

block.append("# === FIX_RUN_ONCE_MODELS_BEFORE_DECORATOR_V1 BEGIN ===\n")

if need_req:
    block.append(
        "class AgentRunOnceRequest(BaseModel):\n"
        "    \"\"\"Request for /v1/agent/run_once.\"\"\"\n"
        "    approve_token: Optional[str] = None\n"
        "    room_id: Optional[str] = None\n\n"
    )

if need_res:
    block.append(
        "class AgentRunOnceResponse(BaseModel):\n"
        "    \"\"\"Response envelope for /v1/agent/run_once.\"\"\"\n"
        "    ok: bool = True\n"
        "    action: str = \"\"\n"
        "    step_id: str = \"\"\n"
        "    room_id: str = \"\"\n"
        "    error: str = \"\"\n"
        "    result: Optional[Dict[str, Any]] = None\n\n"
    )

block.append("# === FIX_RUN_ONCE_MODELS_BEFORE_DECORATOR_V1 END ===\n\n")

txt2 = txt[:insert_at] + "".join(block) + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print(f"OK: inserted missing run_once models before decorator (need_req={need_req}, need_res={need_res})")
