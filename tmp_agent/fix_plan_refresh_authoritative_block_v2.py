from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 BEGIN ==="
END   = "    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 <= i0:
    raise SystemExit("No encuentro bloque PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 (BEGIN/END).")

new_block = r'''
    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 BEGIN ===
    # Authoritative overwrite for current room:
    # - Replace steps entirely (no merge)
    # - Persist per-room plan.json
    # - Return response_model-compatible payload (includes updated=True)
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    try:
        req_room = getattr(req, "room_id", None)
    except Exception:
        req_room = None

    room_id = (req_room or hdr_room or room_id or "default")

    try:
        incoming_steps = getattr(req, "steps", None)
    except Exception:
        incoming_steps = None

    if isinstance(incoming_steps, list):
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

        plan_new["steps"] = incoming_steps
        if not isinstance(plan_new.get("status"), str) or not plan_new["status"]:
            plan_new["status"] = "planned"
        if str(plan_new["status"]).lower() not in ("planned", "complete"):
            plan_new["status"] = "planned"

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
    # === PLAN_REFRESH_AUTHORITATIVE_OVERWRITE_V1 END ===
'''.strip("\n")

txt2 = txt[:i0] + new_block + "\n" + txt[i1+len(END):]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_refresh authoritative block rewritten (adds updated=True, fixes room_id from header).")
