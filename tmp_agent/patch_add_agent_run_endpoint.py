import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

if '"/v1/agent/run"' in txt:
    print("SKIP: /v1/agent/run ya existe")
    raise SystemExit(0)

# Insert right after run_once endpoint block end marker if present, else after run_once function end.
lines = txt.splitlines(True)

# Find run_once function def line
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_run_once\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro agent_run_once")

# Find end of run_once by next decorator at same indent
def_indent = re.match(r"(\s*)def\s+agent_run_once", lines[i_def]).group(1)
i_end = None
for j in range(i_def+1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

# Build block for /v1/agent/run
block = []
block.append("\n")
block.append("# ===== Agent run (v6.1) =====\n")
block.append("class AgentRunRequest(BaseModel):\n")
block.append("    room_id: Optional[str] = None\n")
block.append("    max_steps: int = 10\n")
block.append("\n")
block.append("class AgentRunResponse(BaseModel):\n")
block.append("    ok: bool\n")
block.append("    room_id: str\n")
block.append("    steps_executed: int\n")
block.append("    stopped_reason: str\n")
block.append("    trace: list[Dict[str, Any]] = Field(default_factory=list)\n")
block.append("    plan: Dict[str, Any]\n")
block.append("\n")
block.append('@app.post("/v1/agent/run", response_model=AgentRunResponse)\n')
block.append("def agent_run(req: AgentRunRequest, request: Request):\n")
block.append("    # Loop controlado: usa agent_run_once como tick.\n")
block.append("    try:\n")
block.append('        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None\n')
block.append("    except Exception:\n")
block.append("        hdr_room = None\n")
block.append("    room_id = req.room_id or hdr_room or \"default\"\n")
block.append("    max_steps = int(req.max_steps or 10)\n")
block.append("    if max_steps < 1:\n")
block.append("        max_steps = 1\n")
block.append("    if max_steps > 100:\n")
block.append("        max_steps = 100\n")
block.append("\n")
block.append("    trace = []\n")
block.append("    stopped = \"max_steps\"\n")
block.append("    plan_last = {}\n")
block.append("\n")
block.append("    for i in range(max_steps):\n")
block.append("        r = agent_run_once(AgentRunOnceRequest(room_id=room_id), request)\n")
block.append("        try:\n")
block.append("            trace.append({\n")
block.append("                \"action\": r.get(\"action\"),\n")
block.append("                \"step_id\": r.get(\"step_id\"),\n")
block.append("                \"needs_approval\": bool(r.get(\"needs_approval\", False)),\n")
block.append("                \"approve_token\": r.get(\"approve_token\"),\n")
block.append("            })\n")
block.append("        except Exception:\n")
block.append("            pass\n")
block.append("        plan_last = r.get(\"plan\") or {}\n")
block.append("\n")
block.append("        # Stop conditions\n")
block.append("        if bool(r.get(\"needs_approval\", False)):\n")
block.append("            stopped = \"needs_approval\"\n")
block.append("            break\n")
block.append("        act = str(r.get(\"action\") or \"\")\n")
block.append("        if act == \"noop_complete\":\n")
block.append("            stopped = \"complete\"\n")
block.append("            break\n")
block.append("        if act in {\"noop_no_todo\", \"evaluate_sweep\"}:\n")
block.append("            stopped = act\n")
block.append("            break\n")
block.append("\n")
block.append("    return {\n")
block.append("        \"ok\": True,\n")
block.append("        \"room_id\": room_id,\n")
block.append("        \"steps_executed\": len(trace),\n")
block.append("        \"stopped_reason\": stopped,\n")
block.append("        \"trace\": trace,\n")
block.append("        \"plan\": plan_last or {},\n")
block.append("    }\n")
block.append("# ===== End Agent run =====\n")

new_lines = lines[:i_end] + block + lines[i_end:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted /v1/agent/run after run_once (insert at line {i_end+1})")
