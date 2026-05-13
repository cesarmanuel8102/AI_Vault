from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "FIX_PLAN_REFRESH_REQUEST_MODEL_AND_SIGNATURE_V1"
if MARK in txt:
    print("SKIP: already patched")
    raise SystemExit(0)

# 1) Ensure AgentPlanRefreshRequest has room_id/goal/steps/plan (permissive)
m_req = re.search(r'(^class\s+AgentPlanRefreshRequest\s*\(BaseModel\):\s*\n)(?P<body>(?:^[ \t]+.*\n)+)', txt, flags=re.MULTILINE)
if not m_req:
    raise SystemExit("No encuentro class AgentPlanRefreshRequest(BaseModel):")

body = m_req.group("body")

def has_field(name: str) -> bool:
    return re.search(rf'^\s*{re.escape(name)}\s*:', body, flags=re.MULTILINE) is not None

ins = []
if not has_field("room_id"):
    ins.append("    room_id: Optional[str] = None\n")
if not has_field("goal"):
    ins.append("    goal: str = \"\"\n")
if not has_field("steps"):
    ins.append("    steps: Optional[list] = None\n")
if not has_field("plan"):
    ins.append("    plan: Optional[Dict[str, Any]] = None\n")

if ins:
    # insert right after class line (before existing fields)
    cls_start = m_req.start(1)
    cls_line_end = m_req.end(1)
    txt = txt[:cls_line_end] + "".join(ins) + txt[cls_line_end:]
    print(f"OK: AgentPlanRefreshRequest fields added: {', '.join([x.strip() for x in ins])}")
else:
    print("OK: AgentPlanRefreshRequest already has required fields")

# 2) Fix agent_plan_refresh signature to accept request: Request
# Accept either:
#   def agent_plan_refresh(req: AgentPlanRefreshRequest):
#   def agent_plan_refresh(req: AgentPlanRefreshRequest, request: Request):
pat_def = r'^def\s+agent_plan_refresh\s*\(\s*req\s*:\s*AgentPlanRefreshRequest\s*\)\s*:'
m_def = re.search(pat_def, txt, flags=re.MULTILINE)
if m_def:
    txt = re.sub(pat_def,
                 'def agent_plan_refresh(req: AgentPlanRefreshRequest, request: Request):',
                 txt, count=1, flags=re.MULTILINE)
    print("OK: agent_plan_refresh signature patched to include request: Request")
else:
    # if already has request param, ok
    if re.search(r'^def\s+agent_plan_refresh\s*\(\s*req\s*:\s*AgentPlanRefreshRequest\s*,\s*request\s*:\s*Request\s*\)\s*:',
                 txt, flags=re.MULTILINE):
        print("OK: agent_plan_refresh already has request: Request")
    else:
        raise SystemExit("No encontré def agent_plan_refresh(...) para parchear firma.")

# 3) Drop a marker comment at top of function docstring area (just after def line) for idempotency
m_def2 = re.search(r'^def\s+agent_plan_refresh[^\n]*:\n', txt, flags=re.MULTILINE)
if not m_def2:
    raise SystemExit("No encuentro def agent_plan_refresh tras patch.")
insert_at = m_def2.end()
txt = txt[:insert_at] + f"    # {MARK}\n" + txt[insert_at:]

p.write_text(txt, encoding="utf-8")
print("OK: plan_refresh request model + signature fixed")
