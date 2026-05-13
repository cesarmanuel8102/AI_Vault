from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Locate /v1/agent/plan_refresh endpoint block
m = re.search(r'@app\.post\("/v1/agent/plan_refresh"[^\n]*\)\s*\n(?P<defline>def\s+agent_plan_refresh\s*\(.*?\):\s*\n)', txt, flags=re.DOTALL)
if not m:
    raise SystemExit("No encuentro el endpoint /v1/agent/plan_refresh para reescribir.")

start = m.start()
defline = m.group("defline")

# block end = next decorator at column 0
tail = txt[m.end():]
m2 = re.search(r"\n@app\.", tail)
end = (m.end() + m2.start()) if m2 else len(txt)

# Keep the decorator line(s) exactly as-is (from start to just after defline)
head = txt[start:m.end()]  # includes decorator + def line
# Now replace function body entirely (authoritative overwrite)
body = r'''
    """
    Authoritative plan overwrite for current room.
    Accepts either:
      - req.steps (list)
      - req.plan["steps"] (dict container)
    Always returns response-model-compatible payload including updated=True.
    """
    # resolve room_id (header > req.room_id > default)
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    try:
        req_room = getattr(req, "room_id", None)
    except Exception:
        req_room = None

    room_id = (req_room or hdr_room or "default")

    # Extract steps (support both shapes)
    incoming_steps = None
    try:
        incoming_steps = getattr(req, "steps", None)
    except Exception:
        incoming_steps = None

    if not isinstance(incoming_steps, list):
        try:
            plan_in = getattr(req, "plan", None)
        except Exception:
            plan_in = None
        if isinstance(plan_in, dict):
            incoming_steps = plan_in.get("steps")

    if not isinstance(incoming_steps, list):
        raise HTTPException(status_code=400, detail="PLAN_REFRESH_INVALID: steps list required")

    # Load mission/plan for context (best-effort)
    try:
        mission_cur, plan_cur = agent_store.load()
    except Exception:
        mission_cur, plan_cur = ({}, {})

    plan_new = dict(plan_cur or {})
    plan_new["room_id"] = room_id

    try:
        plan_new["goal"] = getattr(req, "goal", "") or plan_new.get("goal", "")
    except Exception:
        pass

    # AUTHORITATIVE OVERWRITE
    plan_new["steps"] = incoming_steps

    # Normalize status
    st = str(plan_new.get("status") or "planned").strip().lower()
    if st not in ("planned", "complete"):
        st = "planned"
    plan_new["status"] = st

    # Persist via agent_store + disk SOT
    try:
        agent_store.save_plan(plan_new)
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
            Path(pp).write_text(json.dumps(plan_new, ensure_ascii=False, indent=2), encoding="utf-8")
        mp = _paths.get("mission")
        if mp:
            Path(mp).write_text(json.dumps(mission_cur or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Response-model compatible
    return {
        "ok": True,
        "updated": True,
        "room_id": room_id,
        "plan": plan_new,
        "mission": mission_cur or {"room_id": room_id},
    }
'''

new_block = head + body + "\n"
txt2 = txt[:start] + new_block + txt[end:]

p.write_text(txt2, encoding="utf-8")
print("OK: agent_plan_refresh rewritten (authoritative overwrite + updated=True + room_id from header/req).")
