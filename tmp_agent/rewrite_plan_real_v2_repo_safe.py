from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ==="
END   = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 <= i0:
    raise SystemExit("No encuentro bloque PLAN_REAL_ENDPOINT_V2_GATED_V1 (BEGIN/END).")

new_block = r'''
# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ===
class AgentPlanRealV2Request(BaseModel):
    goal: str = Field("", description="goal for planning (read-only + 1 gated write, repo-safe)")
    room_id: Optional[str] = None

class AgentPlanRealV2Response(BaseModel):
    ok: bool = True
    room_id: str
    plan: Dict[str, Any]
    mission: Dict[str, Any]

@app.post("/v1/agent/plan_real_v2", response_model=AgentPlanRealV2Response)
def agent_plan_real_v2(req: AgentPlanRealV2Request, request: Request):
    """
    REAL v2 (repo-safe):
    - Read-only steps (list_dir/read_file)
    - One gated write step (append_file new_file) applied INSIDE repo root:
        C:\\AI_VAULT\\workspace\\brainlab\\_agent_runs\\<room>\\real_log.txt

    This validates propose->approval->apply end-to-end WITHOUT touching code files.
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

    # Must be inside repo root accepted by apply_gate
    dest_dir = r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)

    plan["steps"] = [
        {
            "id": "S1",
            "title": "Inspect risk folder (list_dir)",
            "status": "todo",
            "tool_name": "list_dir",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk"},
        },
        {
            "id": "S2",
            "title": "Read risk_engine.py (read_file)",
            "status": "todo",
            "tool_name": "read_file",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py", "max_bytes": 200000},
        },
        {
            "id": "S3",
            "title": "Write real_log.txt (append_file) — gated SAFE (repo)",
            "status": "todo",
            "tool_name": "append_file",
            "mode": "propose",
            "kind": "new_file",
            "dest_dir": dest_dir,
            "tool_args": {
                "path": "real_log.txt",
                "content": "REAL_V2 START\\n",
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
'''.lstrip("\n")

txt2 = txt[:i0] + new_block + txt[i1 + len(END):]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_real_v2 rewritten repo-safe (dest_dir inside repo root).")
