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

# localizar handler GET /v1/agent/mission
m = re.search(r'@router\.get\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:\s*\n', s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro @router.get('/v1/agent/mission') en brain_router.py")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# evitar doble parche
if "AGENTLOOP_MISSION_ENDPOINT" in block and "AgentLoop(paths=AgentPaths.default" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: brain_router.py ya tenía fix del endpoint /v1/agent/mission (no se duplicó).")
    raise SystemExit(0)

# buscamos return legacy típico: return {"ok": True, "mission": load_mission(room_id)}
pat_return = re.compile(r'^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"mission"\s*:\s*load_mission\(room_id\)\s*\}\s*$', re.M)
mr = pat_return.search(block)
if not mr:
    raise SystemExit("ERROR: No encontré el return legacy esperado en agent_get_mission (return {'ok': True, 'mission': load_mission(room_id)}).")

indent = re.match(r'^(\s*)', mr.group(0)).group(1)

replacement = f"""{indent}# AGENTLOOP_MISSION_ENDPOINT: preferir misión persistida de AgentLoop; fallback a legacy
{indent}try:
{indent}    loop = AgentLoop(paths=AgentPaths.default(room_id=room_id))
{indent}    mission = loop.load_mission() or {{}}
{indent}    # si no hay mission_id, caer al legacy
{indent}    if not mission.get("mission_id"):
{indent}        mission = load_mission(room_id) or {{}}
{indent}except Exception:
{indent}    mission = load_mission(room_id) or {{}}
{indent}return {{"ok": True, "mission": mission}}"""

block2 = block[:mr.start()] + replacement + block[mr.end():]
s = s[:start] + block2 + s[end:]

p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: GET /v1/agent/mission ahora sirve mission de AgentLoop (fallback legacy).")
