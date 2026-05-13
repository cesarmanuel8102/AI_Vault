import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# localizar handler GET /v1/agent/plan
get_rx = r'@router\.get\(\s*[\'"]\/v1\/agent\/plan[\'"]\s*\)\s*\n\s*def\s+agent_get_plan\s*\(.*?\)\s*:\s*\n'
m = re.search(get_rx, s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro GET /v1/agent/plan en brain_router.py")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# idempotencia
if "PLAN_RESET_HARD_V3" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: ya existía PLAN_RESET_HARD_V3 (no se duplicó).")
    raise SystemExit(0)

# encontrar el return final
ret_pat = re.compile(r'^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"plan"\s*:\s*plan\s*\}\s*$', re.M)
mr = ret_pat.search(block)
if not mr:
    raise SystemExit('ERROR: No encontré return {"ok": True, "plan": plan} en GET /v1/agent/plan')

indent = re.match(r'^(\s*)', mr.group(0)).group(1)

inject = f"""{indent}# PLAN_RESET_HARD_V3: reset duro por mismatch o stale created_ts (con _meta para verificar ejecución)
{indent}try:
{indent}    mp = (STATE_AGENT_ROOT / room_id / "mission.json")
{indent}    if mp.exists():
{indent}        mobj = json.loads(mp.read_text(encoding="utf-8", errors="ignore") or "{{}}") or {{}}
{indent}        mid = mobj.get("mission_id")
{indent}        m_created = mobj.get("created_ts")
{indent}        m_updated = mobj.get("updated_ts")
{indent}        if mid:
{indent}            p_mid = plan.get("mission_id") if isinstance(plan, dict) else None
{indent}            p_created = plan.get("created_ts") if isinstance(plan, dict) else None
{indent}            reset_reason = None
{indent}            if not isinstance(plan, dict):
{indent}                reset_reason = "plan_not_dict"
{indent}            elif p_mid != mid:
{indent}                reset_reason = "mission_id_mismatch"
{indent}            elif m_created and p_created and (p_created != m_created):
{indent}                reset_reason = "created_ts_stale"
{indent}            elif m_created and not p_created:
{indent}                reset_reason = "created_ts_missing"
{indent}
{indent}            if reset_reason:
{indent}                plan = {{
{indent}                    "mission_id": mid,
{indent}                    "created_ts": m_created,
{indent}                    "updated_ts": m_updated,
{indent}                    "profile": "default",
{indent}                    "cursor": 0,
{indent}                    "steps": [],
{indent}                    "_meta": {{"reset_reason": reset_reason, "ts": m_updated or m_created}}
{indent}                }}
{indent}            else:
{indent}                # misma misión y no stale: refrescar updated_ts + saneo mínimo
{indent}                if m_updated:
{indent}                    plan["updated_ts"] = m_updated
{indent}                if not plan.get("profile"):
{indent}                    plan["profile"] = "default"
{indent}                if "cursor" not in plan:
{indent}                    plan["cursor"] = 0
{indent}                if "steps" not in plan or plan["steps"] is None:
{indent}                    plan["steps"] = []
{indent}                plan.setdefault("_meta", {{"reset_reason": "no_reset", "ts": m_updated or m_created}})
{indent}
{indent}            # persistir siempre lo que devolvemos
{indent}            try:
{indent}                room_dir = (STATE_AGENT_ROOT / room_id)
{indent}                room_dir.mkdir(parents=True, exist_ok=True)
{indent}                (room_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
{indent}            except Exception:
{indent}                pass
{indent}except Exception as e:
{indent}    # dejar rastro mínimo en respuesta (sin romper)
{indent}    try:
{indent}        if isinstance(plan, dict):
{indent}            plan.setdefault("_meta", {{}})
{indent}            plan["_meta"]["reset_reason"] = "exception"
{indent}            plan["_meta"]["error"] = repr(e)
{indent}    except Exception:
{indent}        pass

"""

block2 = block[:mr.start()] + inject + block[mr.start():]
s2 = s[:start] + block2 + s[end:]
p.write_text(s2, encoding="utf-8")
print("OK: brain_router.py parcheado: GET /plan hard reset v3 + _meta.")
