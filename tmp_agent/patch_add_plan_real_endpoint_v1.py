import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "PLAN_REAL_ENDPOINT_V1"
if MARK in txt:
    print("SKIP: plan_real already exists")
    raise SystemExit(0)

# Insert a new endpoint right AFTER /v1/agent/plan handler block (before next @app.)
m = re.search(r'@app\.post\("/v1/agent/plan".*?\)\s*\ndef\s+agent_plan\s*\(.*?\):\n', txt, flags=re.DOTALL)
if not m:
    raise SystemExit("No encuentro /v1/agent/plan para anclar plan_real")

start = m.start()
after_def = m.end()
tail = txt[after_def:]
m2 = re.search(r"\n@app\.", tail)
end = (after_def + m2.start()) if m2 else len(txt)

# Find insertion point: end of agent_plan function (right before next decorator)
insert_at = end

endpoint = r'''

# === PLAN_REAL_ENDPOINT_V1 BEGIN ===
class AgentPlanRealRequest(BaseModel):
    goal: str = Field("", description="goal for planning (read-only)")
    room_id: Optional[str] = None

class AgentPlanRealResponse(BaseModel):
    ok: bool = True
    room_id: str
    plan: Dict[str, Any]
    mission: Dict[str, Any]

@app.post("/v1/agent/plan_real", response_model=AgentPlanRealResponse)
def agent_plan_real(req: AgentPlanRealRequest, request: Request):
    """
    Read-only planner. Does NOT modify /v1/agent/plan behavior.
    Creates a simple plan with list_dir + read_file steps.
    """
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    room_id = (req.room_id or hdr_room or "default")

    # load current mission/plan, but we will overwrite plan steps for this room
    mission, plan = agent_store.load()
    plan = dict(plan or {})
    plan["status"] = "planned"
    plan["room_id"] = room_id
    plan["goal"] = req.goal

    plan["steps"] = [
        {
            "id": "S1",
            "title": "Inspect risk folder (list_dir)",
            "status": "todo",
            "tool_name": "list_dir",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk"},
        },
        {
            "id": "S2",
            "title": "Read risk_engine.py (read_file)",
            "status": "todo",
            "tool_name": "read_file",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk\\\\risk_engine.py", "max_bytes": 200000},
        },
    ]

    # Persist per-room (same mechanism your SOT expects)
    try:
        agent_store.save_plan(plan)
    except Exception:
        pass
    try:
        _rid = room_id
        _room_state_dir(_rid)
        _paths = _room_paths(_rid) or {}
        import json
        from pathlib import Path
        pp = _paths.get("plan")
        if pp:
            Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        mp = _paths.get("mission")
        if mp:
            Path(mp).write_text(json.dumps(mission or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission or {"room_id": room_id}}
# === PLAN_REAL_ENDPOINT_V1 END ===
'''

txt2 = txt[:insert_at] + endpoint + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: added /v1/agent/plan_real (read-only) endpoint")
