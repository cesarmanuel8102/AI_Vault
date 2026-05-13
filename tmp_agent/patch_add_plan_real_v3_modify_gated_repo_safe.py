from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "PLAN_REAL_ENDPOINT_V3_MODIFY_V1"
if MARK in txt:
    print("SKIP: plan_real_v3 already exists")
    raise SystemExit(0)

# Anchor insert right after PLAN_REAL_ENDPOINT_V2_GATED_V1 block end (preferred),
# fallback: after PLAN_REAL_ENDPOINT_V1 block end.
anchor = None
m = re.search(r"# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ===\s*\n", txt)
if m:
    anchor = m.end()
else:
    m = re.search(r"# === PLAN_REAL_ENDPOINT_V1 END ===\s*\n", txt)
    if m:
        anchor = m.end()

if anchor is None:
    raise SystemExit("No encuentro ancla para insertar plan_real_v3 (END de plan_real_v1/v2).")

endpoint = r'''

# === PLAN_REAL_ENDPOINT_V3_MODIFY_V1 BEGIN ===
class AgentPlanRealV3Request(BaseModel):
    goal: str = Field("", description="goal for planning (read-only + 1 gated modify write, repo-safe)")
    room_id: Optional[str] = None

class AgentPlanRealV3Response(BaseModel):
    ok: bool = True
    room_id: str
    plan: Dict[str, Any]
    mission: Dict[str, Any]

@app.post("/v1/agent/plan_real_v3", response_model=AgentPlanRealV3Response)
def agent_plan_real_v3(req: AgentPlanRealV3Request, request: Request):
    """
    REAL v3 (repo-safe, modify gated):
    - Read-only: list_dir + read_file (same as v2)
    - One gated MODIFY: append marker into:
        C:\\AI_VAULT\\workspace\\brainlab\\_agent_runs\\<room>\\real_log.txt

    This validates propose->approval->apply on kind=modify (without touching code files).
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

    # Repo-safe folder
    run_dir = r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)
    # Target file inside repo-safe folder
    log_repo_path = run_dir + r"\real_log.txt"

    # Marker (single line, deterministic enough)
    try:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
    except Exception:
        ts = ""
    marker = f"REAL_V3 MARK {ts}\\n"

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
            "title": "Modify real_log.txt (append marker) — gated SAFE (repo)",
            "status": "todo",
            "tool_name": "append_file",
            "mode": "propose",
            "kind": "modify",
            "repo_path": log_repo_path,
            "dest_dir": run_dir,
            "tool_args": {
                "path": "real_log.txt",
                "content": marker,
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
# === PLAN_REAL_ENDPOINT_V3_MODIFY_V1 END ===

'''

txt2 = txt[:anchor] + endpoint + txt[anchor:]
p.write_text(txt2, encoding="utf-8")
print("OK: added /v1/agent/plan_real_v3 (modify gated repo-safe)")
