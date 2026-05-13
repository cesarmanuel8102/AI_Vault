import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "PLAN_REAL_ENDPOINT_V2_GATED_V1"
if MARK in txt:
    print("SKIP: plan_real_v2 already exists")
    raise SystemExit(0)

# Anchor insert near existing plan_real endpoint end marker
m = re.search(r"# === PLAN_REAL_ENDPOINT_V1 END ===\s*\n", txt)
if not m:
    raise SystemExit("No encuentro PLAN_REAL_ENDPOINT_V1 END para anclar plan_real_v2")

insert_at = m.end()

endpoint = r'''

# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ===
class AgentPlanRealV2Request(BaseModel):
    goal: str = Field("", description="goal for planning (read-only + 1 gated write)")
    room_id: Optional[str] = None

class AgentPlanRealV2Response(BaseModel):
    ok: bool = True
    room_id: str
    plan: Dict[str, Any]
    mission: Dict[str, Any]

@app.post("/v1/agent/plan_real_v2", response_model=AgentPlanRealV2Response)
def agent_plan_real_v2(req: AgentPlanRealV2Request, request: Request):
    """
    REAL v2: read-only steps + one SAFE gated write (append_file new_file) into tmp_agent/runs/<room>/real_log.txt
    Does NOT touch repo. Purpose: validate approval flow end-to-end.
    """
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    room_id = (req.room_id or hdr_room or "default")

    mission, plan = agent_store.load()
    plan = dict(plan or {})
    plan["status"] = "planned"
    plan["room_id"] = room_id
    plan["goal"] = req.goal

    # Safe destination under tmp_agent/runs/<room>
    run_dir = r"C:\\AI_VAULT\\tmp_agent\\runs\\" + str(room_id)
    log_path = run_dir + r"\\real_log.txt"

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
        {
            "id": "S3",
            "title": "Write real_log.txt (append_file) — gated SAFE",
            "status": "todo",
            "tool_name": "append_file",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {
                "path": log_path,
                "content": "REAL_V2 START\\n"
            },
        },
    ]

    # Persist per-room plan/mission
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
# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ===
'''

txt2 = txt[:insert_at] + endpoint + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: added /v1/agent/plan_real_v2 (read-only + 1 gated write safe)")
