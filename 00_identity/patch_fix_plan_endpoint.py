import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# asegurar import (idempotente)
if "from agent_loop import AgentLoop, AgentPaths" not in s:
    m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
    ins = "from agent_loop import AgentLoop, AgentPaths\n"
    if m:
        s = s[:m.end()] + ins + s[m.end():]
    else:
        s = ins + s

# localizar handler GET /v1/agent/plan
m = re.search(r'@router\.get\(\s*[\'"]\/v1\/agent\/plan[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:\s*\n', s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro @router.get('/v1/agent/plan') en brain_router.py")

fn_name = m.group(1)

# capturar bloque de función hasta siguiente decorator @router.
start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# evitar doble parche
if "AgentLoop(paths=AgentPaths.default" in block and "AGENTLOOP_PLAN_ENDPOINT" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: brain_router.py ya tenía fix del endpoint /v1/agent/plan (no se duplicó).")
    raise SystemExit(0)

# reemplazar el return legacy por lógica preferente AgentLoop con fallback
# buscamos una línea tipo: return {"ok": True, "plan": load_plan(room_id)}
pat_return = re.compile(r'^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"plan"\s*:\s*load_plan\(room_id\)\s*\}\s*$', re.M)
mr = pat_return.search(block)
if not mr:
    raise SystemExit("ERROR: No encontré el return legacy esperado en agent_get_plan (return {'ok': True, 'plan': load_plan(room_id)}).")

indent = re.match(r'^(\s*)', mr.group(0)).group(1)

replacement = f"""{indent}# AGENTLOOP_PLAN_ENDPOINT: preferir plan persistido de AgentLoop; fallback a legacy
{indent}try:
{indent}    loop = AgentLoop(paths=AgentPaths.default(room_id=room_id))
{indent}    plan = loop.load_plan() or {{}}
{indent}    # si no hay steps ni mission_id, caer al legacy
{indent}    if not plan.get("mission_id") and not (plan.get("steps") or []):
{indent}        plan = load_plan(room_id) or {{}}
{indent}except Exception:
{indent}    plan = load_plan(room_id) or {{}}
{indent}return {{"ok": True, "plan": plan}}"""

block2 = block[:mr.start()] + replacement + block[mr.end():]
s = s[:start] + block2 + s[end:]

p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: GET /v1/agent/plan ahora sirve plan de AgentLoop (fallback legacy).")
