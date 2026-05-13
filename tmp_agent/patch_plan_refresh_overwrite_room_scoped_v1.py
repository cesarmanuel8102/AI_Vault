import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "PLAN_REFRESH_OVERWRITE_ROOM_SCOPED_V1"
if MARK in txt:
    print("SKIP: plan_refresh overwrite patch already present")
    raise SystemExit(0)

# Find /v1/agent/plan_refresh endpoint def
m = re.search(r'@app\.post\("/v1/agent/plan_refresh".*?\)\s*\ndef\s+agent_plan_refresh\s*\(.*?\):\n', txt, flags=re.DOTALL)
if not m:
    raise SystemExit("No encuentro endpoint /v1/agent/plan_refresh para parchear.")

start = m.start()
after_def = m.end()
tail = txt[after_def:]
m2 = re.search(r"\n@app\.", tail)
end = (after_def + m2.start()) if m2 else len(txt)

hdr = txt[start:after_def]

# New implementation: overwrite plan for this room with req.steps
impl = r'''
    # === PLAN_REFRESH_OVERWRITE_ROOM_SCOPED_V1 BEGIN ===
    """
    Overwrite per-room plan.json with req.steps (authoritative).
    This endpoint is used for tests/ops to inject a custom plan.
    """
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    room_id = (getattr(req, "room_id", None) or hdr_room or "default")

    # Build plan from request
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
    except Exception:
        now = None

    try:
        steps_in = getattr(req, "steps", None)
    except Exception:
        steps_in = None
    if not isinstance(steps_in, list):
        steps_in = []

    plan = {
        "status": "planned",
        "steps": steps_in,
        "updated_at": now,
        "room_id": room_id,
    }
    try:
        g = getattr(req, "goal", None)
        if isinstance(g, str):
            plan["goal"] = g
    except Exception:
        pass

    # mission best-effort
    mission = {"room_id": room_id, "updated_at": now}

    # Persist to agent_store (best-effort)
    try:
        agent_store.save_plan(plan)
    except Exception:
        pass

    # Persist to disk (SOT)
    try:
        _room_state_dir(room_id)
        _paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pp = _paths.get("plan")
        if pp:
            Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        mp = _paths.get("mission")
        if mp:
            Path(mp).write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission}
    # === PLAN_REFRESH_OVERWRITE_ROOM_SCOPED_V1 END ===
'''.lstrip("\n")

txt2 = txt[:start] + hdr + impl + txt[end:]
p.write_text(txt2, encoding="utf-8")
print("OK: patched /v1/agent/plan_refresh to overwrite per-room plan with req.steps")
