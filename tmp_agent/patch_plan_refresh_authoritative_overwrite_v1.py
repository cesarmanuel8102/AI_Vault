from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1"
if MARK in txt:
    print("SKIP: plan_refresh authoritative overwrite already present")
    raise SystemExit(0)

# Locate endpoint /v1/agent/plan_refresh
m = re.search(r'@app\.post\("/v1/agent/plan_refresh"[^\n]*\)\s*\ndef\s+agent_plan_refresh\s*\(.*?\):\n', txt, flags=re.DOTALL)
if not m:
    raise SystemExit("No encuentro endpoint /v1/agent/plan_refresh para parchear.")

start = m.end()
tail = txt[start:]
m2 = re.search(r"\n@app\.", tail)
end = (start + m2.start()) if m2 else len(txt)
block = txt[m.start():end]

# Insert overwrite logic near top of handler after room_id resolved.
# Anchor: first occurrence of 'room_id ='
a = re.search(r'^\s*room_id\s*=\s*.*$', block, flags=re.MULTILINE)
if not a:
    raise SystemExit("No encuentro asignación room_id dentro de agent_plan_refresh.")

insert_at = m.start() + a.end()

inject = r'''

    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 BEGIN ===
    # Make plan_refresh authoritative for the current room:
    # - Replace steps entirely (no merge with existing planner plan)
    # - Reset status to planned unless caller sets complete explicitly
    try:
        incoming_steps = getattr(req, "steps", None)
    except Exception:
        incoming_steps = None

    if isinstance(incoming_steps, list):
        try:
            # Load current (room-scoped) mission/plan
            mission_cur, plan_cur = agent_store.load()
        except Exception:
            mission_cur, plan_cur = ({}, {})

        plan_new = dict(plan_cur or {})
        plan_new["room_id"] = room_id
        try:
            plan_new["goal"] = getattr(req, "goal", "") or plan_new.get("goal", "")
        except Exception:
            pass
        plan_new["steps"] = incoming_steps
        if not isinstance(plan_new.get("status"), str) or not plan_new["status"]:
            plan_new["status"] = "planned"
        if str(plan_new["status"]).lower() not in ("planned","complete"):
            plan_new["status"] = "planned"

        # Persist through same SOT path (disk)
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
        except Exception:
            pass

        # Return early (authoritative overwrite)
        return {"ok": True, "room_id": room_id, "plan": plan_new, "mission": mission_cur or {"room_id": room_id}}
    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 END ===

'''

block2 = block[:a.end()] + inject + block[a.end():]
txt2 = txt[:m.start()] + block2 + txt[end:]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_refresh ahora es authoritative overwrite por room (no merge).")
