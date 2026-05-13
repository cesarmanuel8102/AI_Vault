import re
import json
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

def _replace_fn_block(decorator_regex: str, new_block: str):
    global s
    m = re.search(decorator_regex, s, flags=re.S)
    if not m:
        raise SystemExit(f"ERROR: No encuentro endpoint con patrón: {decorator_regex}")
    start = m.start()
    after = s[m.end():]
    m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
    end = (m.end() + m2.start()) if m2 else len(s)
    s = s[:start] + new_block + s[end:]

# -------------------------
# PATCH: POST /v1/agent/mission (inyectar sync plan.json)
# -------------------------
post_rx = r'@router\.post\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+agent_set_mission\s*\(.*?\)\s*:\s*\n'
m = re.search(post_rx, s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro @router.post('/v1/agent/mission')")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

if "SYNC_PLAN_WITH_MISSION_V2" not in block:
    # Insertar antes del return final
    ret_pat = re.compile(r'^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"mission"\s*:\s*mission\s*\}\s*$', re.M)
    mr = ret_pat.search(block)
    if not mr:
        raise SystemExit('ERROR: No encontré return {"ok": True, "mission": mission} en POST /v1/agent/mission')
    indent = re.match(r'^(\s*)', mr.group(0)).group(1)

    inject = f"""{indent}# SYNC_PLAN_WITH_MISSION_V2: crear/reconciliar plan.json al mission_id vigente
{indent}try:
{indent}    room_dir = (STATE_AGENT_ROOT / room_id)
{indent}    room_dir.mkdir(parents=True, exist_ok=True)
{indent}    pp = (room_dir / "plan.json")
{indent}    plan_obj = {{}}
{indent}    if pp.exists():
{indent}        try:
{indent}            plan_obj = json.loads(pp.read_text(encoding="utf-8", errors="ignore") or "{{}}") or {{}}
{indent}        except Exception:
{indent}            plan_obj = {{}}
{indent}    # crear mínimo si no existe o está vacío
{indent}    if not isinstance(plan_obj, dict) or not plan_obj:
{indent}        plan_obj = {{
{indent}            "mission_id": mission.get("mission_id"),
{indent}            "created_ts": mission.get("created_ts"),
{indent}            "updated_ts": mission.get("updated_ts"),
{indent}            "profile": "default",
{indent}            "cursor": 0,
{indent}            "steps": []
{indent}        }}
{indent}    else:
{indent}        # reconciliar mission_id si está desalineado
{indent}        if plan_obj.get("mission_id") != mission.get("mission_id"):
{indent}            plan_obj["mission_id"] = mission.get("mission_id")
{indent}            # mantener created_ts existente si ya estaba, si no usar el de mission
{indent}            if not plan_obj.get("created_ts"):
{indent}                plan_obj["created_ts"] = mission.get("created_ts")
{indent}            plan_obj["updated_ts"] = mission.get("updated_ts")
{indent}            if not plan_obj.get("profile"):
{indent}                plan_obj["profile"] = "default"
{indent}            if "cursor" not in plan_obj:
{indent}                plan_obj["cursor"] = 0
{indent}            if "steps" not in plan_obj or plan_obj["steps"] is None:
{indent}                plan_obj["steps"] = []
{indent}    pp.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")
{indent}except Exception:
{indent}    pass

"""
    block2 = block[:mr.start()] + inject + block[mr.start():]
    s = s[:start] + block2 + s[end:]

# -------------------------
# PATCH: GET /v1/agent/plan (reconciliar con mission.json si mismatch)
# -------------------------
get_plan_rx = r'@router\.get\(\s*[\'"]\/v1\/agent\/plan[\'"]\s*\)\s*\n\s*def\s+agent_get_plan\s*\(.*?\)\s*:\s*\n'
m = re.search(get_plan_rx, s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro @router.get('/v1/agent/plan')")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

if "RECONCILE_PLAN_MISSION_V2_ON_READ" not in block:
    # Insertar justo antes del return {"ok": True, "plan": plan}
    ret_pat = re.compile(r'^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"plan"\s*:\s*plan\s*\}\s*$', re.M)
    mr = ret_pat.search(block)
    if not mr:
        raise SystemExit('ERROR: No encontré return {"ok": True, "plan": plan} en GET /v1/agent/plan')
    indent = re.match(r'^(\s*)', mr.group(0)).group(1)

    inject = f"""{indent}# RECONCILE_PLAN_MISSION_V2_ON_READ: si mission.json existe y plan.mission_id difiere, reconciliar + persistir
{indent}try:
{indent}    mp = (STATE_AGENT_ROOT / room_id / "mission.json")
{indent}    if mp.exists():
{indent}        mobj = json.loads(mp.read_text(encoding="utf-8", errors="ignore") or "{{}}") or {{}}
{indent}        mid = mobj.get("mission_id")
{indent}        if mid and isinstance(plan, dict) and plan.get("mission_id") != mid:
{indent}            plan["mission_id"] = mid
{indent}            # updated_ts: usar el de mission si existe
{indent}            uts = (mobj.get("updated_ts") or "")
{indent}            if uts:
{indent}                plan["updated_ts"] = uts
{indent}            # persistir plan.json reconciliado
{indent}            try:
{indent}                pp = (STATE_AGENT_ROOT / room_id / "plan.json")
{indent}                (STATE_AGENT_ROOT / room_id).mkdir(parents=True, exist_ok=True)
{indent}                pp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
{indent}            except Exception:
{indent}                pass
{indent}except Exception:
{indent}    pass

"""
    block2 = block[:mr.start()] + inject + block[mr.start():]
    s = s[:start] + block2 + s[end:]

p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: POST mission sincroniza plan.json; GET plan reconcilia mission_id vs mission.json.")
