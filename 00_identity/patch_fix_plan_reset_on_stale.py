import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# handler GET /v1/agent/plan
get_rx = r'@router\.get\(\s*[\'"]\/v1\/agent\/plan[\'"]\s*\)\s*\n\s*def\s+agent_get_plan\s*\(.*?\)\s*:\s*\n'
m = re.search(get_rx, s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro GET /v1/agent/plan")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# buscamos el bloque que insertamos antes (marker)
if "RECONCILE_PLAN_MISSION_V2_ON_READ" not in block and "RESET_PLAN_ON_MISMATCH_ON_READ_V2" not in block:
    raise SystemExit("ERROR: No encuentro el bloque de reconcile/reset en GET /plan (marker esperado).")

# idempotencia
if "RESET_PLAN_ON_STALE_CREATED_TS_V2" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: ya existía RESET_PLAN_ON_STALE_CREATED_TS_V2 (no se duplicó).")
    raise SystemExit(0)

# capturar segmento desde el primer marker conocido hasta antes del return {"ok": True, "plan": plan}
seg_rx = re.compile(
    r'(?P<head>^\s*#\s*(RECONCILE_PLAN_MISSION_V2_ON_READ|RESET_PLAN_ON_MISMATCH_ON_READ_V2)[^\n]*\n)'
    r'(?P<body>.*?)(?=^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"plan"\s*:\s*plan\s*\}\s*$)',
    flags=re.S | re.M
)
ms = seg_rx.search(block)
if not ms:
    raise SystemExit("ERROR: No pude capturar segmento marker->return en GET /plan")

head = ms.group("head")
indent = re.match(r'^(\s*)', head).group(1)

new_body = f"""{indent}# RESET_PLAN_ON_STALE_CREATED_TS_V2: si mission existe y plan.created_ts != mission.created_ts => reset duro
{indent}try:
{indent}    mp = (STATE_AGENT_ROOT / room_id / "mission.json")
{indent}    if mp.exists():
{indent}        mobj = json.loads(mp.read_text(encoding="utf-8", errors="ignore") or "{{}}") or {{}}
{indent}        mid = mobj.get("mission_id")
{indent}        m_created = mobj.get("created_ts")
{indent}        if mid and isinstance(plan, dict):
{indent}            p_created = plan.get("created_ts")
{indent}            # si es otra misión O el plan es stale por created_ts distinto => reset duro
{indent}            if (plan.get("mission_id") != mid) or (m_created and p_created and p_created != m_created) or (m_created and not p_created):
{indent}                plan = {{
{indent}                    "mission_id": mid,
{indent}                    "created_ts": m_created,
{indent}                    "updated_ts": mobj.get("updated_ts"),
{indent}                    "profile": "default",
{indent}                    "cursor": 0,
{indent}                    "steps": []
{indent}                }}
{indent}            else:
{indent}                # misma misión y no stale: refrescar updated_ts + saneo mínimo
{indent}                if mobj.get("updated_ts"):
{indent}                    plan["updated_ts"] = mobj.get("updated_ts")
{indent}                if not plan.get("profile"):
{indent}                    plan["profile"] = "default"
{indent}                if "cursor" not in plan:
{indent}                    plan["cursor"] = 0
{indent}                if "steps" not in plan or plan["steps"] is None:
{indent}                    plan["steps"] = []
{indent}
{indent}            # persistir plan.json
{indent}            try:
{indent}                room_dir = (STATE_AGENT_ROOT / room_id)
{indent}                room_dir.mkdir(parents=True, exist_ok=True)
{indent}                (room_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
{indent}            except Exception:
{indent}                pass
{indent}except Exception:
{indent}    pass

"""

block2 = block[:ms.start("head")] + head + new_body + block[ms.end("body"):]
s2 = s[:start] + block2 + s[end:]
p.write_text(s2, encoding="utf-8")

print("OK: brain_router.py parcheado: GET /plan resetea si created_ts está stale vs mission.created_ts.")
